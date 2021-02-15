"""
This integration supplies a service to reverse geocode the location 
and calculate the distance from home (miles and minutes) using 
WazeRouteCalculator.  

For meaningful results, the device trackers will need to include latitude 
and longitude attributes, as in Mobile App, iCloud, and iCloud3 device 
trackers.  These location features will be skipped for updates triggered 
by device trackers that do not know the location coordinates.  

The location can optionally be reverse geocoded by Open Street Map (Nominatim)
and/or Google Maps Geocoding.

For details, refer to the docs in https://github.com/rodpayne/home-assistant.
"""
import json
import logging
import string
import threading
import time
import traceback
from datetime import datetime, timedelta, timezone
from functools import partial

import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.event import (
    track_point_in_time,
)
import requests
import voluptuous as vol
from homeassistant.components.device_tracker.const import (
    ATTR_SOURCE_TYPE,
    SOURCE_TYPE_GPS,
)
from homeassistant.const import (
    ATTR_ATTRIBUTION,
    ATTR_GPS_ACCURACY,
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
    CONF_ENTITY_ID,
    CONF_FRIENDLY_NAME_TEMPLATE,
)
from homeassistant.util.location import distance
from requests import get

from .const import (
    API_STATE_OBJECT,
    CONF_API_KEY_NOT_SET,
    CONF_GOOGLE_API_KEY,
    CONF_LANGUAGE,
    CONF_OSM_API_KEY,
    CONF_REGION,
    DEFAULT_LANGUAGE,
    DEFAULT_REGION,
    DOMAIN,
    INTEGRATION_NAME,
    ISSUE_URL,
    METERS_PER_KM,
    METERS_PER_MILE,
    MIN_DISTANCE_TRAVELLED,
    PERSON_LOCATION_ENTITY,
    PERSON_LOCATION_INTEGRATION,
    THROTTLE_INTERVAL,
    VERSION,
)

_LOGGER = logging.getLogger(__name__)


def setup(hass, config):
    """Setup is called when Home Assistant is loading our component."""

    pli = PERSON_LOCATION_INTEGRATION(API_STATE_OBJECT, hass, config)
    integration_lock = threading.Lock()

    target_lock = threading.Lock()
    trigger_lock = threading.Lock()

    def call_rest_command_service(personName, newState):
        """ (Optionally) send HomeSeer a notification of the state change. """
        rest_command = ""
        rest_command = (
            "homeseer_" + personName.lower() + "_" + newState.lower().replace(" ", "_")
        )
        try:
            hass.services.call("rest_command", rest_command)
        except Exception as e:
            _LOGGER.debug(
                "call_rest_command_service" + " %s exception - %s", rest_command, str(e)
            )

    def handle_delayed_state_change(
        now, *, entity_id=None, from_state=None, to_state=None, minutes=3
    ):
        """ Handle the delayed state change. """

        _LOGGER.debug(
            "[handle_delayed_state_change]"
            + " (%s) === Start: from_state = %s; to_state = %s"
            % (entity_id, from_state, to_state)
        )

        with target_lock:
            """Lock while updating the target(entity_id)."""
            _LOGGER.debug("[handle_delayed_state_change]" + " target_lock obtained")
            target = PERSON_LOCATION_ENTITY(entity_id, hass)

            elapsed_timespan = datetime.now(timezone.utc) - target.last_changed
            #    _LOGGER.debug("elapsed_timespan = %s" % (elapsed_timespan))
            elapsed_minutes = (
                elapsed_timespan.total_seconds() + 1
            ) / 60  # fudge factor of one second

            if target.state != from_state:
                _LOGGER.debug(
                    "[handle_delayed_state_change]"
                    + " Skipping update: state %s is no longer %s"
                    % (target.state, from_state)
                )
            elif elapsed_minutes < minutes:
                _LOGGER.debug(
                    "[handle_delayed_state_change]"
                    + " Skipping update: state change minutes ago %s less than %s"
                    % (elapsed_minutes, minutes)
                )
            else:
                if to_state == "Home":
                    target.attributes["bread_crumbs"] = to_state  # Reset bread_crumbs
                elif to_state == "Away":
                    change_state_later(
                        target.entity_id,
                        "Away",
                        "Extended Away",
                        pli.configured_minutes_extended_away,
                    )
                    pass
                elif to_state == "Extended Away":
                    pass

                target.state = to_state

                call_rest_command_service(target.personName, to_state)
                target.set_state()
        _LOGGER.debug(
            "[handle_delayed_state_change]" + " (%s) === Finish." % (entity_id)
        )

    def change_state_later(entity_id, from_state, to_state, minutes=3):
        """ Set timer to handle the delayed state change. """
        point_in_time = datetime.now() + timedelta(minutes=minutes)
        remove = track_point_in_time(
            hass,
            partial(
                handle_delayed_state_change,
                entity_id=entity_id,
                from_state=from_state,
                to_state=to_state,
                minutes=minutes,
            ),
            point_in_time=point_in_time,
        )
        if remove:
            _LOGGER.debug(
                "[change_state_later]"
                + " (%s) handle_delayed_state_change(, %s, %s, %d) has been scheduled"
                % (entity_id, from_state, to_state, minutes)
            )

    def handle_process_trigger(call):
        """ Handle the process_trigger service. """

        # --------------------------------------------------------------------------------------------------
        #   Input:
        #       - State changes of a device tracker.  Parameters for the call:
        #           entity_id
        #           from_state
        #           to_state
        #       - Automation.ha_just_started:
        #           on for a few minutes so that "Just Arrived" and "Just Left" don't get set at startup
        #   Output (if update is accepted):
        #       - Updated "sensor.<personName>_location" with <personName>'s location and status:
        #           Attributes:
        #           - selected attributes from the triggered device tracker
        #           - state: "Just Arrived", "Home", "Just Left", "Away", or "Extended Away"
        #           - person_name: <personName>
        #           - source: entity_id of the device tracker that triggered the automation
        #           - reported_state: the state reported by device tracker = "Home", "Away", or <zone>
        #           - friendly_name: something like "Rod (i.e. Rod's watch) is at Drew's"
        #           - icon: the icon that correspondes with the current zone
        #       - Call rest_command service to update HomeSeer: 'homeseer_<personName>_<state>'
        #   Assumptions:
        #       - The last device to change zone state is an indicator of where a person is,
        #           because devices left at home should not change zones.
        # --------------------------------------------------------------------------------------------------

        entity_id = call.data.get(CONF_ENTITY_ID, "NONE")
        triggerFrom = call.data.get("from_state", "NONE")
        triggerTo = call.data.get("to_state", "NONE")

        trigger = PERSON_LOCATION_ENTITY(entity_id, hass)

        _LOGGER.debug(
            "[handle_process_trigger]"
            + " (%s) ===== Start: from_state = %s; to_state = %s",
            trigger.entity_id,
            triggerFrom,
            triggerTo,
        )

        if trigger.entity_id == trigger.targetName:
            _LOGGER.debug(
                "[handle_process_trigger]"
                + " Decision: skipping update because trigger (%s) = target (%s)",
                trigger.entity_id,
                trigger.targetName,
            )
        else:

            # -----------------------------------------------------------------------------
            # Get the current state of the target person location sensor and
            # decide if it should be updated with values from the triggered device tracker.
            saveThisUpdate = False
            # -----------------------------------------------------------------------------

            if "source_type" in trigger.attributes:
                triggerSourceType = trigger.attributes["source_type"]
            else:
                triggerSourceType = "other"

            with target_lock:
                """Lock while updating the target(trigger.targetName)."""
                _LOGGER.debug("[handle_process_trigger]" + " target_lock obtained")
                target = PERSON_LOCATION_ENTITY(trigger.targetName, hass)

                if triggerTo == "NotSet":
                    _LOGGER.debug(
                        "[handle_process_trigger]"
                        + " Decision: skipping update because triggerTo = %s",
                        triggerTo,
                    )
                elif target.firstTime == True:
                    saveThisUpdate = True
                    _LOGGER.debug(
                        "[handle_process_trigger]"
                        + " Decision: target %s does not yet exist (normal at startup)",
                        target.entity_id,
                    )
                    oldTargetState = "none"
                else:
                    oldTargetState = target.state.lower()
                    if oldTargetState == "unknown":
                        saveThisUpdate = True
                        _LOGGER.debug(
                            "[handle_process_trigger]"
                            + " Decision: accepting the first update of %s",
                            target.entity_id,
                        )
                    elif triggerSourceType == "gps":  # gps device?
                        if triggerTo != triggerFrom:  # did it change zones?
                            saveThisUpdate = True  # gps changing zones is assumed to be new, correct info
                            _LOGGER.debug(
                                "[handle_process_trigger]"
                                + " Decision: %s has changed zones",
                                trigger.entity_id,
                            )
                        else:
                            if (
                                not ("source" in target.attributes)
                                or not ("reported_state" in target.attributes)
                                or target.attributes["source"] == trigger.entity_id
                            ):  # same entity as we are following?
                                saveThisUpdate = True  # same tracker as we are following (or this is the first one)
                                _LOGGER.debug(
                                    "[handle_process_trigger]"
                                    + " Decision: continue following %s",
                                    trigger.entity_id,
                                )
                            elif (
                                trigger.state == target.attributes["reported_state"]
                            ):  # same status as the one we are following?
                                if "vertical_accuracy" in trigger.attributes:
                                    if (
                                        not ("vertical_accuracy" in target.attributes)
                                    ) or (
                                        trigger.attributes["vertical_accuracy"] > 0
                                        and target.attributes["vertical_accuracy"] == 0
                                    ):  # better choice based on accuracy?
                                        saveThisUpdate = True
                                        _LOGGER.debug(
                                            "[handle_process_trigger]"
                                            + " Decision: vertical_accuracy is better than %s",
                                            target.attributes["source"],
                                        )
                                if (
                                    "gps_accuracy" in trigger.attributes
                                    and "gps_accuracy" in target.attributes
                                    and trigger.attributes["gps_accuracy"]
                                    < target.attributes["gps_accuracy"]
                                ):  # better choice based on accuracy?
                                    saveThisUpdate = True
                                    _LOGGER.debug(
                                        "[handle_process_trigger]"
                                        + " Decision: gps_accuracy is better than %s",
                                        target.attributes["source"],
                                    )
                    else:  # source = router or ping
                        if triggerTo != triggerFrom:  # did it change state?
                            if trigger.stateHomeAway == "Home":  # reporting Home
                                if (
                                    oldTargetState != "home"
                                ):  # no additional information if already Home
                                    saveThisUpdate = True
                                    _LOGGER.debug(
                                        "[handle_process_trigger]"
                                        + " Decision: %s has changed state",
                                        trigger.entity_id,
                                    )
                            else:  # reporting Away
                                if (
                                    oldTargetState == "home"
                                ):  # no additional information if already Away
                                    saveThisUpdate = True
                                    _LOGGER.debug(
                                        "[handle_process_trigger]"
                                        + " Decision: %s has changed state",
                                        trigger.entity_id,
                                    )

                # -----------------------------------------------------------------------------

                if saveThisUpdate == False:
                    _LOGGER.debug(
                        "[handle_process_trigger]" + " Decision: ignore update from %s",
                        trigger.entity_id,
                    )
                else:
                    # Be selective about attributes carried in the target sensor:

                    if "source_type" in trigger.attributes:
                        target.attributes["source_type"] = trigger.attributes[
                            "source_type"
                        ]
                    else:
                        if "source_type" in target.attributes:
                            target.attributes.pop("source_type")

                    if (
                        "latitude" in trigger.attributes
                        and "longitude" in trigger.attributes
                    ):
                        target.attributes["latitude"] = trigger.attributes["latitude"]
                        target.attributes["longitude"] = trigger.attributes["longitude"]
                    else:
                        if "latitude" in target.attributes:
                            target.attributes.pop("latitude")
                        if "longitude" in target.attributes:
                            target.attributes.pop("longitude")

                    if "gps_accuracy" in trigger.attributes:
                        target.attributes["gps_accuracy"] = trigger.attributes[
                            "gps_accuracy"
                        ]
                    else:
                        if "gps_accuracy" in target.attributes:
                            target.attributes.pop("gps_accuracy")

                    if "altitude" in trigger.attributes:
                        target.attributes["altitude"] = round(
                            trigger.attributes["altitude"], 0
                        )
                    else:
                        if "altitude" in target.attributes:
                            target.attributes.pop("altitude")

                    if "vertical_accuracy" in trigger.attributes:
                        target.attributes["vertical_accuracy"] = trigger.attributes[
                            "vertical_accuracy"
                        ]
                    else:
                        if "vertical_accuracy" in target.attributes:
                            target.attributes.pop("vertical_accuracy")

                    target.attributes["source"] = trigger.entity_id
                    target.attributes["reported_state"] = trigger.state
                    target.attributes["person_name"] = string.capwords(
                        trigger.personName
                    )
                    target.attributes["update_time"] = str(datetime.now())

                    # Format new friendly_name and the template to be updated by geocoding.

                    if trigger.state == "Away" or trigger.state.lower() == "on":
                        friendly_name = f"{string.capwords(trigger.personName)} ({trigger.friendlyName}) is {trigger.state}"
                        template = f"{string.capwords(trigger.personName)} ({trigger.friendlyName}) is in <locality>"
                    else:
                        friendly_name = f"{string.capwords(trigger.personName)} ({trigger.friendlyName}) is at {trigger.state}"
                        template = friendly_name
                    target.attributes["friendly_name"] = friendly_name

                    # Determine the icon to be used, based on the zone.

                    if "zone" in trigger.attributes:
                        zoneEntityID = "zone." + trigger.attributes["zone"]
                    else:
                        zoneEntityID = "zone." + trigger.state.lower().replace(
                            " ", "_"
                        ).replace("'", "_")
                    zoneStateObject = hass.states.get(zoneEntityID)
                    if zoneStateObject != None:
                        zoneAttributesObject = zoneStateObject.attributes.copy()
                        target.attributes["icon"] = zoneAttributesObject["icon"]
                    else:
                        target.attributes["icon"] = "mdi:help-circle"
                    _LOGGER.debug(
                        "[handle_process_trigger]" + " zone = %s; icon = %s",
                        zoneEntityID,
                        target.attributes["icon"],
                    )

                    # Set up something like https://philhawthorne.com/making-home-assistants-presence-detection-not-so-binary/
                    # If Home Assistant just started, just go with Home or Away as the initial state.

                    ha_just_startedObject = hass.states.get(
                        "automation.ha_just_started"
                    )
                    ha_just_started = ha_just_startedObject.state
                    if ha_just_started == "on":
                        _LOGGER.debug(
                            "[handle_process_trigger]" + " ha_just_started = %s",
                            ha_just_started,
                        )

                    if trigger.stateHomeAway == "Home":
                        if (
                            oldTargetState == "none"
                            or ha_just_started == "on"
                            or oldTargetState == "just left"
                        ):
                            newTargetState = "Home"
                            call_rest_command_service(
                                trigger.personName, newTargetState
                            )
                        elif oldTargetState == "home":
                            newTargetState = "Home"
                        elif oldTargetState == "just arrived":
                            newTargetState = "Just Arrived"
                        else:
                            newTargetState = "Just Arrived"
                            change_state_later(
                                target.entity_id,
                                newTargetState,
                                "Home",
                                pli.configured_minutes_just_arrived,
                            )
                            call_rest_command_service(
                                trigger.personName, newTargetState
                            )
                    else:
                        if oldTargetState == "none" or ha_just_started == "on":
                            newTargetState = "Away"
                            change_state_later(
                                target.entity_id,
                                "Away",
                                "Extended Away",
                                pli.configured_minutes_extended_away,
                            )
                            call_rest_command_service(
                                trigger.personName, newTargetState
                            )
                        elif oldTargetState == "just left":
                            newTargetState = "Just Left"
                        elif (
                            oldTargetState == "home" or oldTargetState == "just arrived"
                        ):
                            newTargetState = "Just Left"
                            change_state_later(
                                target.entity_id,
                                newTargetState,
                                "Away",
                                pli.configured_minutes_just_left,
                            )
                            #                    change_state_later(target.entity_id, "Away", "Extended Away", pli.configured_minutes_extended_away)
                            call_rest_command_service(
                                trigger.personName, newTargetState
                            )
                        else:
                            newTargetState = "Away"
                            call_rest_command_service(
                                trigger.personName, newTargetState
                            )

                    target.state = newTargetState

                    target.set_state()

                    # --------------------------------------------------------------------------------------------------
                    # Call service to "reverse geocode" the location:
                    # - determine <locality> for friendly_name
                    # - record full location in OSM_location
                    # - calculate other location-based statistics, such as distance_from_home
                    # For devices at Home, this will only be done initially or on arrival (newTargetState = 'Just Arrived')
                    # --------------------------------------------------------------------------------------------------
                    if newTargetState != "Home" or ha_just_started == "on":
                        service_data = {
                            "entity_id": target.entity_id,
                            "friendly_name_template": template,
                        }
                        hass.services.call(
                            "person_location", "reverse_geocode", service_data, False
                        )

                _LOGGER.debug("[handle_process_trigger]" + " target_lock release...")
        _LOGGER.debug(
            "[handle_process_trigger]" + " (%s) === Finish.",
            trigger.entity_id,
        )

    def handle_reverse_geocode(call):
        """ Handle the reverse_geocode service. """

        entity_id = call.data.get(CONF_ENTITY_ID, "NONE")
        template = call.data.get(CONF_FRIENDLY_NAME_TEMPLATE, "NONE")

        _LOGGER.debug(
            "[handle_reverse_geocode]"
            + " (%s) === Start: %s = %s"
            % (entity_id, CONF_FRIENDLY_NAME_TEMPLATE, template)
        )

        with integration_lock:
            """Lock while updating the pli(API_STATE_OBJECT)."""
            _LOGGER.debug("[handle_reverse_geocode]" + " integration_lock obtained")

            try:
                currentApiTime = datetime.now()

                if pli.state.lower() != "on":
                    """Allow API calls to be paused."""
                    pli.attributes["api_calls_skipped"] += 1
                    _LOGGER.debug(
                        "[handle_reverse_geocode]"
                        + " (%s) api_calls_skipped = %d"
                        % (entity_id, pli.attributes["api_calls_skipped"])
                    )
                else:
                    """Throttle the API calls so that we don't exceed policy."""
                    wait_time = (
                        pli.attributes["api_last_updated"]
                        - currentApiTime
                        + THROTTLE_INTERVAL
                    ).total_seconds()
                    if wait_time > 0:
                        pli.attributes["api_calls_throttled"] += 1
                        _LOGGER.debug(
                            "[handle_reverse_geocode]"
                            + " (%s) wait_time = %05.3f; api_calls_throttled = %d"
                            % (
                                entity_id,
                                wait_time,
                                pli.attributes["api_calls_throttled"],
                            )
                        )
                        time.sleep(wait_time)
                        currentApiTime = datetime.now()

                    """Record the integration attributes in the API_STATE_OBJECT."""

                    pli.attributes["api_last_updated"] = currentApiTime

                    pli.attributes["api_calls_attempted"] += 1

                    counter_attribute = f"{entity_id} calls"
                    if counter_attribute in pli.attributes:
                        new_count = pli.attributes[counter_attribute] + 1
                    else:
                        new_count = 1
                    pli.attributes[counter_attribute] = new_count
                    _LOGGER.debug(
                        "[handle_reverse_geocode]"
                        + " ("
                        + entity_id
                        + ") "
                        + counter_attribute
                        + " = "
                        + str(new_count)
                    )

                    """Handle the service call, updating the target(entity_id)."""
                    with target_lock:
                        """Lock while updating the target(entity_id)."""
                        _LOGGER.debug(
                            "[handle_reverse_geocode]" + " target_lock obtained"
                        )

                        target = PERSON_LOCATION_ENTITY(entity_id, hass)
                        attribution = ""

                        if ATTR_LATITUDE in target.attributes:
                            new_latitude = target.attributes[ATTR_LATITUDE]
                        else:
                            new_latitude = "None"
                        if ATTR_LONGITUDE in target.attributes:
                            new_longitude = target.attributes[ATTR_LONGITUDE]
                        else:
                            new_longitude = "None"

                        if "location_latitude" in target.attributes:
                            old_latitude = target.attributes["location_latitude"]
                        else:
                            old_latitude = "None"
                        if "location_longitude" in target.attributes:
                            old_longitude = target.attributes["location_longitude"]
                        else:
                            old_longitude = "None"

                        if (
                            new_latitude != "None"
                            and new_longitude != "None"
                            and old_latitude != "None"
                            and old_longitude != "None"
                        ):
                            distance_traveled = round(
                                distance(
                                    float(new_latitude),
                                    float(new_longitude),
                                    float(old_latitude),
                                    float(old_longitude),
                                ),
                                3,
                            )
                            _LOGGER.debug(
                                "[handle_reverse_geocode]"
                                + " ("
                                + entity_id
                                + ") distance_traveled = "
                                + str(distance_traveled)
                            )
                        else:
                            distance_traveled = 0

                        if new_latitude == "None" or new_longitude == "None":
                            _LOGGER.debug(
                                "[handle_reverse_geocode]"
                                + " ("
                                + entity_id
                                + ") Skipping geocoding because coordinates are missing"
                            )
                        elif (
                            distance_traveled < MIN_DISTANCE_TRAVELLED
                            and old_latitude != "None"
                            and old_longitude != "None"
                        ):
                            _LOGGER.debug(
                                "[handle_reverse_geocode]"
                                + " ("
                                + entity_id
                                + ") Skipping geocoding because distance_traveled < "
                                + str(MIN_DISTANCE_TRAVELLED)
                            )
                        else:
                            locality = "?"

                            if "update_time" in target.attributes:
                                new_update_time = datetime.strptime(
                                    target.attributes["update_time"],
                                    "%Y-%m-%d %H:%M:%S.%f",
                                )
                                _LOGGER.debug(
                                    "[handle_reverse_geocode]"
                                    + " ("
                                    + entity_id
                                    + ") new_update_time = "
                                    + str(new_update_time)
                                )
                            else:
                                new_update_time = currentApiTime

                            if "location_update_time" in target.attributes:
                                old_update_time = datetime.strptime(
                                    target.attributes["location_update_time"],
                                    "%Y-%m-%d %H:%M:%S.%f",
                                )
                                _LOGGER.debug(
                                    "[handle_reverse_geocode]"
                                    + " ("
                                    + entity_id
                                    + ") old_update_time = "
                                    + str(old_update_time)
                                )
                            else:
                                old_update_time = new_update_time

                            elapsed_time = new_update_time - old_update_time
                            _LOGGER.debug(
                                "[handle_reverse_geocode]"
                                + " ("
                                + entity_id
                                + ") elapsed_time = "
                                + str(elapsed_time)
                            )
                            elapsed_seconds = elapsed_time.total_seconds()
                            _LOGGER.debug(
                                "[handle_reverse_geocode]"
                                + " ("
                                + entity_id
                                + ") elapsed_seconds = "
                                + str(elapsed_seconds)
                            )

                            if elapsed_seconds > 0:
                                speed_during_interval = (
                                    distance_traveled / elapsed_seconds
                                )
                                _LOGGER.debug(
                                    "[handle_reverse_geocode]"
                                    + " ("
                                    + entity_id
                                    + ") speed_during_interval = "
                                    + str(speed_during_interval)
                                    + " meters/sec"
                                )
                            else:
                                speed_during_interval = 0

                            old_distance_from_home = 0
                            if "meters_from_home" in target.attributes:
                                old_distance_from_home = float(
                                    target.attributes["meters_from_home"]
                                )

                            if (
                                "reported_state" in target.attributes
                                and target.attributes["reported_state"].lower()
                                == "home"
                            ):
                                distance_from_home = 0  # clamp it down since "Home" is not a single point
                            elif (
                                new_latitude != "None"
                                and new_longitude != "None"
                                and pli.attributes["home_latitude"] != "None"
                                and pli.attributes["home_longitude"] != "None"
                            ):
                                distance_from_home = round(
                                    distance(
                                        float(new_latitude),
                                        float(new_longitude),
                                        float(pli.attributes["home_latitude"]),
                                        float(pli.attributes["home_longitude"]),
                                    ),
                                    3,
                                )
                            else:
                                distance_from_home = (
                                    0  # could only happen if we don't have coordinates
                                )
                            _LOGGER.debug(
                                "[handle_reverse_geocode]"
                                + " ("
                                + entity_id
                                + ") meters_from_home = "
                                + str(distance_from_home)
                            )
                            target.attributes["meters_from_home"] = str(
                                round(distance_from_home, 1)
                            )
                            target.attributes["miles_from_home"] = str(
                                round(distance_from_home / METERS_PER_MILE, 1)
                            )

                            if speed_during_interval <= 0.5:
                                direction = "stationary"
                            elif old_distance_from_home > distance_from_home:
                                direction = "toward home"
                            elif old_distance_from_home < distance_from_home:
                                direction = "away from home"
                            else:
                                direction = "stationary"
                            _LOGGER.debug(
                                "[handle_reverse_geocode]"
                                + " ("
                                + entity_id
                                + ") direction = "
                                + direction
                            )
                            target.attributes["direction"] = direction

                            if pli.configured_osm_api_key != CONF_API_KEY_NOT_SET:
                                """Call the Open Street Map (Nominatim) API if osm_api_key is configured"""
                                if pli.configured_osm_api_key == CONF_API_KEY_NOT_SET:
                                    osm_url = (
                                        "https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat="
                                        + str(new_latitude)
                                        + "&lon="
                                        + str(new_longitude)
                                        + "&addressdetails=1&namedetails=1&zoom=18&limit=1"
                                    )
                                else:
                                    osm_url = (
                                        "https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat="
                                        + str(new_latitude)
                                        + "&lon="
                                        + str(new_longitude)
                                        + "&addressdetails=1&namedetails=1&zoom=18&limit=1&email="
                                        + pli.configured_osm_api_key
                                    )

                                osm_decoded = {}
                                osm_response = get(osm_url)
                                osm_json_input = osm_response.text
                                osm_decoded = json.loads(osm_json_input)
                                decoded = osm_decoded

                                if "city" in osm_decoded["address"]:
                                    locality = osm_decoded["address"]["city"]
                                elif "town" in osm_decoded["address"]:
                                    locality = osm_decoded["address"]["town"]
                                elif "villiage" in osm_decoded["address"]:
                                    locality = osm_decoded["address"]["village"]
                                elif "municipality" in osm_decoded["address"]:
                                    locality = osm_decoded["address"]["municipality"]
                                elif "county" in osm_decoded["address"]:
                                    locality = osm_decoded["address"]["county"]
                                elif "state" in osm_decoded["address"]:
                                    locality = osm_decoded["address"]["state"]
                                elif "country" in osm_decoded["address"]:
                                    locality = osm_decoded["address"]["country"]
                                _LOGGER.debug(
                                    "[handle_reverse_geocode]"
                                    + " ("
                                    + entity_id
                                    + ") OSM locality = "
                                    + locality
                                )

                                if "display_name" in osm_decoded:
                                    display_name = osm_decoded["display_name"]
                                else:
                                    display_name = locality
                                _LOGGER.debug(
                                    "[handle_reverse_geocode]"
                                    + " ("
                                    + entity_id
                                    + ") OSM display_name = "
                                    + display_name
                                )

                                target.attributes[
                                    "Open_Street_Map"
                                ] = display_name.replace(", ", " ")

                                if "licence" in osm_decoded:
                                    attribution += '"' + osm_decoded["licence"] + '"; '

                            if pli.configured_google_api_key != CONF_API_KEY_NOT_SET:
                                """Call the Google Maps Reverse Geocoding API if google_api_key is configured"""
                                """https://developers.google.com/maps/documentation/geocoding/overview?hl=en_US#ReverseGeocoding"""
                                google_url = (
                                    "https://maps.googleapis.com/maps/api/geocode/json?language="
                                    + pli.configured_language
                                    + "&region="
                                    + pli.configured_region
                                    + "&latlng="
                                    + str(new_latitude)
                                    + ","
                                    + str(new_longitude)
                                    + "&key="
                                    + pli.configured_google_api_key
                                )
                                google_decoded = {}
                                #            _LOGGER.debug( "(" + entity_id + ") url - " + google_url)
                                google_response = get(google_url)
                                google_json_input = google_response.text
                                #            _LOGGER.debug( "(" + entity_id + ") response - " + google_json_input)
                                google_decoded = json.loads(google_json_input)

                                google_status = google_decoded["status"]
                                if google_status != "OK":
                                    _LOGGER.debug(
                                        "[handle_reverse_geocode]"
                                        + " ("
                                        + entity_id
                                        + ") google_status = "
                                        + google_status
                                    )
                                else:
                                    if "results" in google_decoded:
                                        #                    for result in google_decoded['results']:
                                        #                        location_type = 'none'
                                        #                        if 'geometry' in result:
                                        #                            if 'location_type' in result['geometry']:
                                        #                                location_type = result['geometry']['location_type']
                                        #                        if 'formatted_address' in result:
                                        #                            formatted_address = result['formatted_address']
                                        #                        else:
                                        #                            formatted_address = 'none'
                                        #                        _LOGGER.debug( '(' + entity_id + ') location_type = ' + location_type + '; formatted_address = ' + formatted_address)
                                        if (
                                            "formatted_address"
                                            in google_decoded["results"][0]
                                        ):
                                            formatted_address = google_decoded[
                                                "results"
                                            ][0]["formatted_address"]
                                            _LOGGER.debug(
                                                "[handle_reverse_geocode]"
                                                + " ("
                                                + entity_id
                                                + ") Google formatted_address = "
                                                + formatted_address
                                            )
                                            target.attributes[
                                                "Google_Maps"
                                            ] = formatted_address
                                        for component in google_decoded["results"][0][
                                            "address_components"
                                        ]:
                                            #                    _LOGGER.debug(
                                            #                        "("
                                            #                        + entity_id
                                            #                        + ") address_components "
                                            #                        + str(component["types"])
                                            #                        + " = "
                                            #                        + component["long_name"]
                                            #                    )
                                            if "locality" in component["types"]:
                                                locality = component["long_name"]
                                                _LOGGER.debug(
                                                    "[handle_reverse_geocode]"
                                                    + " ("
                                                    + entity_id
                                                    + ") Google locality = "
                                                    + locality
                                                )
                                        attribution += '"powered by Google"; '

                            target.attributes["friendly_name"] = template.replace(
                                "<locality>", locality
                            )
                            target.attributes["location_latitude"] = new_latitude
                            target.attributes["location_longitude"] = new_longitude
                            target.attributes["location_update_time"] = str(
                                new_update_time
                            )

                            if "reported_state" in target.attributes:
                                if target.attributes["reported_state"] != "Away":
                                    newBreadCrumb = target.attributes["reported_state"]
                                else:
                                    newBreadCrumb = locality
                            else:
                                newBreadCrumb = locality
                            if "bread_crumbs" in target.attributes:
                                oldBreadCrumbs = target.attributes["bread_crumbs"]
                                if not oldBreadCrumbs.endswith(newBreadCrumb):
                                    target.attributes["bread_crumbs"] = (
                                        oldBreadCrumbs + "> " + newBreadCrumb
                                    )
                            else:
                                target.attributes["bread_crumbs"] = newBreadCrumb

                            """WazeRouteCalculator is checked if not at Home."""
                            if distance_from_home <= 0:
                                routeTime = 0
                                routeDistance = 0
                                target.attributes["driving_miles"] = "0"
                                target.attributes["driving_minutes"] = "0"
                            else:
                                try:
                                    _LOGGER.debug(
                                        "[handle_reverse_geocode]"
                                        + " (("
                                        + entity_id
                                        + ") Waze calculation"
                                    )
                                    import WazeRouteCalculator

                                    from_address = (
                                        str(new_latitude) + "," + str(new_longitude)
                                    )
                                    to_address = (
                                        str(pli.attributes["home_latitude"])
                                        + ","
                                        + str(pli.attributes["home_longitude"])
                                    )
                                    route = WazeRouteCalculator.WazeRouteCalculator(
                                        from_address,
                                        to_address,
                                        pli.configured_region,
                                        avoid_toll_roads=True,
                                    )
                                    routeTime, routeDistance = route.calc_route_info()
                                    _LOGGER.debug(
                                        "[handle_reverse_geocode]"
                                        + " ("
                                        + entity_id
                                        + ") Waze routeDistance "
                                        + str(routeDistance)
                                    )  # km
                                    routeDistance = (
                                        routeDistance * METERS_PER_KM / METERS_PER_MILE
                                    )  # miles
                                    if routeDistance >= 100:
                                        target.attributes["driving_miles"] = str(
                                            round(routeDistance, 0)
                                        )
                                    elif routeDistance >= 10:
                                        target.attributes["driving_miles"] = str(
                                            round(routeDistance, 1)
                                        )
                                    else:
                                        target.attributes["driving_miles"] = str(
                                            round(routeDistance, 2)
                                        )
                                    _LOGGER.debug(
                                        "[handle_reverse_geocode]"
                                        + " ("
                                        + entity_id
                                        + ") Waze routeTime "
                                        + str(routeTime)
                                    )  # minutes
                                    target.attributes["driving_minutes"] = str(
                                        round(routeTime, 1)
                                    )
                                    attribution += (
                                        '"Data by Waze App. https://waze.com"; '
                                    )
                                except Exception as e:
                                    _LOGGER.error(
                                        "[handle_reverse_geocode]"
                                        + " ("
                                        + entity_id
                                        + ") Waze Exception - "
                                        + str(e)
                                    )
                                    _LOGGER.debug(traceback.format_exc())
                                    pli.attributes["waze_error_count"] += 1
                                    target.attributes.pop("driving_miles")
                                    target.attributes.pop("driving_minutes")

                        target.attributes[ATTR_ATTRIBUTION] = attribution

                        target.set_state()

                        _LOGGER.debug(
                            "[handle_reverse_geocode]" + " target_lock release..."
                        )
            except Exception as e:
                _LOGGER.error(
                    "[handle_reverse_geocode]"
                    + " (%s) Exception - %s" % (entity_id, str(e))
                )
                _LOGGER.debug(traceback.format_exc())
                pli.attributes["api_error_count"] += 1

            pli.set_state()
            _LOGGER.debug("[handle_reverse_geocode]" + " integration_lock release...")
        _LOGGER.debug("[handle_reverse_geocode] === Finish.")

    def handle_geocode_api_on(call):
        """ Handle the geocode_api_on service. """

        _LOGGER.debug("[geocode_api_on] === Start.")
        with integration_lock:
            """Lock while updating the pli(API_STATE_OBJECT)."""
            _LOGGER.debug("[handle_geocode_api_on]" + " integration_lock obtained")

            _LOGGER.debug("Setting " + API_STATE_OBJECT + " on")
            pli.state = "on"
            pli.attributes["icon"] = "mdi:api"
            pli.set_state()
            _LOGGER.debug("[geocode_api_on]" + " integration_lock release...")
        _LOGGER.debug("[geocode_api_on] === Finish.")

    def handle_geocode_api_off(call):
        """ Handle the geocode_api_off service. """

        _LOGGER.debug("[geocode_api_off] === Start.")
        with integration_lock:
            """Lock while updating the pli(API_STATE_OBJECT)."""
            _LOGGER.debug("[handle_geocode_api_off]" + " integration_lock obtained")

            _LOGGER.debug("Setting " + API_STATE_OBJECT + " off")
            pli.state = "off"
            pli.attributes["icon"] = "mdi:api-off"
            pli.set_state()
            _LOGGER.debug("[handle_geocode_api_off]" + " integration_lock release...")
        _LOGGER.debug("[geocode_api_off] === Finish.")

    hass.services.register(DOMAIN, "reverse_geocode", handle_reverse_geocode)
    hass.services.register(DOMAIN, "geocode_api_on", handle_geocode_api_on)
    hass.services.register(DOMAIN, "geocode_api_off", handle_geocode_api_off)
    #    hass.services.register(DOMAIN, "delayed_state_change", handle_delayed_state_change)
    hass.services.register(DOMAIN, "process_trigger", handle_process_trigger)

    pli.set_state()

    # Return boolean to indicate that setup was successful.
    return True