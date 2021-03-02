"""
The person_location integration.

This integration supplies a service to reverse geocode the location
using Open Street Map (Nominatim) or Google Maps or MapQuest and
calculate the distance from home (miles and minutes) using 
WazeRouteCalculator.  
"""

import json
import logging
import string
import threading
import time
import traceback
from datetime import datetime, timedelta, timezone
from functools import partial

import WazeRouteCalculator
from homeassistant.components.device_tracker.const import (
    ATTR_SOURCE_TYPE,
    SOURCE_TYPE_GPS,
)
from homeassistant.components.device_tracker.const import (
    DOMAIN as DEVICE_TRACKER_DOMAIN,
)
from homeassistant.components.mobile_app.const import ATTR_VERTICAL_ACCURACY
from homeassistant.const import (
    ATTR_ATTRIBUTION,
    ATTR_GPS_ACCURACY,
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
    CONF_ENTITY_ID,
    CONF_FRIENDLY_NAME_TEMPLATE,
)
from homeassistant.exceptions import ServiceNotFound
from homeassistant.helpers.event import track_point_in_time
from homeassistant.util.location import distance
from requests import get

from .const import (
    API_STATE_OBJECT,
    ATTR_ALTITUDE,
    ATTR_BREAD_CRUMBS,
    ATTR_DRIVING_MILES,
    ATTR_DRIVING_MINUTES,
    ATTR_GEOCODED,
    ATTR_METERS_FROM_HOME,
    ATTR_MILES_FROM_HOME,
    CONF_CREATE_SENSORS,
    CONF_GOOGLE_API_KEY,
    CONF_HOURS_EXTENDED_AWAY,
    CONF_LANGUAGE,
    CONF_MAPQUEST_API_KEY,
    CONF_MINUTES_JUST_ARRIVED,
    CONF_MINUTES_JUST_LEFT,
    CONF_OSM_API_KEY,
    CONF_REGION,
    DATA_ASYNC_SETUP_ENTRY,
    DATA_CONFIG_ENTRY,
    DATA_CONFIGURATION,
    DATA_UNDO_UPDATE_LISTENER,
    DEFAULT_API_KEY_NOT_SET,
    DOMAIN,
    METERS_PER_KM,
    METERS_PER_MILE,
    MIN_DISTANCE_TRAVELLED_TO_GEOCODE,
    PERSON_LOCATION_ENTITY,
    PERSON_LOCATION_INTEGRATION,
    THROTTLE_INTERVAL,
    VERSION,
    WAZE_MIN_METERS_FROM_HOME,
)

_LOGGER = logging.getLogger(__name__)


def setup(hass, config):
    """Setup is called by Home Assistant to load our integration."""

    _LOGGER.debug("[setup] === Start ===")

    pli = PERSON_LOCATION_INTEGRATION(API_STATE_OBJECT, hass, config)
    integration_lock = threading.Lock()

    target_lock = threading.Lock()

    def call_rest_command_service(personName, newState):
        """(Optionally) notify HomeSeer of the state change."""

        rest_command = ""
        rest_command = (
            "homeseer_" + personName.lower() + "_" + newState.lower().replace(" ", "_")
        )
        try:
            hass.services.call("rest_command", rest_command)
        except ServiceNotFound as e:
            _LOGGER.debug(
                "call_rest_command_service Exception %s = %s",
                type(e).__name__,
                str(e),
            )

    def handle_delayed_state_change(
        now, *, entity_id=None, from_state=None, to_state=None, minutes=3
    ):
        """Handle the delayed state change."""

        _LOGGER.debug(
            "[handle_delayed_state_change]"
            + " (%s) === Start === from_state = %s; to_state = %s"
            % (entity_id, from_state, to_state)
        )

        with target_lock:
            """Lock while updating the target(entity_id)."""
            _LOGGER.debug("[handle_delayed_state_change]" + " target_lock obtained")
            target = PERSON_LOCATION_ENTITY(entity_id, hass)

            elapsed_timespan = datetime.now(timezone.utc) - target.last_changed
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
                target.state = to_state

                if to_state == "Home":
                    target.attributes[
                        ATTR_BREAD_CRUMBS
                    ] = to_state  # Reset bread_crumbs
                elif to_state == "Away":
                    change_state_later(
                        target.entity_id,
                        "Away",
                        "Extended Away",
                        (pli.configuration[CONF_HOURS_EXTENDED_AWAY] * 60),
                    )
                    pass
                elif to_state == "Extended Away":
                    pass

                call_rest_command_service(target.personName, to_state)
                target.set_state()
        _LOGGER.debug(
            "[handle_delayed_state_change]" + " (%s) === Return ===" % (entity_id)
        )

    def change_state_later(entity_id, from_state, to_state, minutes=3):
        """Set timer to handle the delayed state change."""

        _LOGGER.debug("[change_state_later]" + " (%s) === Start ===" % (entity_id))
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
        _LOGGER.debug("[change_state_later]" + " (%s) === Return ===" % (entity_id))

    def handle_process_trigger(call):
        """
        Handle changes of triggered device trackers and sensors.

        Input:
            - Parameters for the call:
                entity_id
                from_state
                to_state
            - Automation.ha_just_started:
                on for a few minutes so that "Just Arrived" and "Just Left" don't get set at startup
        Output (if update is accepted):
            - Updated "sensor.<personName>_location" with <personName>'s location and status:
                Attributes:
                - selected attributes from the triggered device tracker
                - state: "Just Arrived", "Home", "Just Left", "Away", or "Extended Away"
                - person_name: <personName>
                - source: entity_id of the device tracker that triggered the automation
                - reported_state: the state reported by device tracker = "Home", "Away", or <zone>
                - friendly_name: something like "Rod (i.e. Rod's watch) is at Drew's"
                - icon: the icon that correspondes with the current zone
            - Call rest_command service to update HomeSeer: 'homeseer_<personName>_<state>'
        Assumptions:
            - The last device to change zone state is an indicator of where a person is,
                because devices left at home should not change zones.
        """

        entity_id = call.data.get(CONF_ENTITY_ID, "NONE")
        triggerFrom = call.data.get("from_state", "NONE")
        triggerTo = call.data.get("to_state", "NONE")

        if entity_id == "NONE":
            {
                _LOGGER.warning(
                    "%s is required in call of %s.process_trigger service."
                    % (CONF_ENTITY_ID, DOMAIN)
                )
                # return False
            }

        trigger = PERSON_LOCATION_ENTITY(entity_id, hass)

        _LOGGER.debug(
            "[handle_process_trigger]"
            + " (%s) === Start === from_state = %s; to_state = %s",
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

            # ---------------------------------------------------------
            # Get the current state of the target person location
            # sensor and decide if it should be updated with values
            # from the triggered device tracker:
            saveThisUpdate = False
            # ---------------------------------------------------------

            if ATTR_SOURCE_TYPE in trigger.attributes:
                triggerSourceType = trigger.attributes[ATTR_SOURCE_TYPE]
            else:
                triggerSourceType = "other"

            with target_lock:
                """Lock while updating the target(trigger.targetName)."""
                _LOGGER.debug("[handle_process_trigger]" + " target_lock obtained")
                target = PERSON_LOCATION_ENTITY(trigger.targetName, hass)

                target.entity_sensor_info["trigger_count"] += 1

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
                    elif triggerSourceType == SOURCE_TYPE_GPS:  # gps device?
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
                            ):  # same entity as we are following, if any?
                                saveThisUpdate = True
                                _LOGGER.debug(
                                    "[handle_process_trigger]"
                                    + " Decision: continue following %s",
                                    trigger.entity_id,
                                )
                            elif (
                                trigger.state == target.attributes["reported_state"]
                            ):  # same status as the one we are following?
                                if ATTR_VERTICAL_ACCURACY in trigger.attributes:
                                    if (
                                        not (
                                            ATTR_VERTICAL_ACCURACY in target.attributes
                                        )
                                    ) or (
                                        trigger.attributes[ATTR_VERTICAL_ACCURACY] > 0
                                        and target.attributes[ATTR_VERTICAL_ACCURACY]
                                        == 0
                                    ):  # better choice based on accuracy?
                                        saveThisUpdate = True
                                        _LOGGER.debug(
                                            "[handle_process_trigger]"
                                            + " Decision: vertical_accuracy is better than %s",
                                            target.attributes["source"],
                                        )
                                if (
                                    ATTR_GPS_ACCURACY in trigger.attributes
                                    and ATTR_GPS_ACCURACY in target.attributes
                                    and trigger.attributes[ATTR_GPS_ACCURACY]
                                    < target.attributes[ATTR_GPS_ACCURACY]
                                ):  # better choice based on accuracy?
                                    saveThisUpdate = True
                                    _LOGGER.debug(
                                        "[handle_process_trigger]"
                                        + " Decision: gps_accuracy is better than %s",
                                        target.attributes["source"],
                                    )
                    else:  # source = router or ping
                        if triggerTo != triggerFrom:  # did tracker change state?
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

                # -----------------------------------------------------

                if saveThisUpdate == False:
                    _LOGGER.debug(
                        "[handle_process_trigger]" + " Decision: ignore update from %s",
                        trigger.entity_id,
                    )
                else:
                    # Carry over selected attributes from trigger to target:

                    if ATTR_SOURCE_TYPE in trigger.attributes:
                        target.attributes[ATTR_SOURCE_TYPE] = trigger.attributes[
                            ATTR_SOURCE_TYPE
                        ]
                    else:
                        if ATTR_SOURCE_TYPE in target.attributes:
                            target.attributes.pop(ATTR_SOURCE_TYPE)

                    if (
                        ATTR_LATITUDE in trigger.attributes
                        and ATTR_LONGITUDE in trigger.attributes
                    ):
                        target.attributes[ATTR_LATITUDE] = trigger.attributes[
                            ATTR_LATITUDE
                        ]
                        target.attributes[ATTR_LONGITUDE] = trigger.attributes[
                            ATTR_LONGITUDE
                        ]
                    else:
                        if ATTR_LATITUDE in target.attributes:
                            target.attributes.pop(ATTR_LATITUDE)
                        if ATTR_LONGITUDE in target.attributes:
                            target.attributes.pop(ATTR_LONGITUDE)

                    if ATTR_GPS_ACCURACY in trigger.attributes:
                        target.attributes[ATTR_GPS_ACCURACY] = trigger.attributes[
                            ATTR_GPS_ACCURACY
                        ]
                    else:
                        if ATTR_GPS_ACCURACY in target.attributes:
                            target.attributes.pop(ATTR_GPS_ACCURACY)

                    if ATTR_ALTITUDE in trigger.attributes:
                        target.attributes[ATTR_ALTITUDE] = round(
                            trigger.attributes[ATTR_ALTITUDE]
                        )
                    else:
                        if ATTR_ALTITUDE in target.attributes:
                            target.attributes.pop(ATTR_ALTITUDE)

                    if ATTR_VERTICAL_ACCURACY in trigger.attributes:
                        target.attributes[ATTR_VERTICAL_ACCURACY] = trigger.attributes[
                            ATTR_VERTICAL_ACCURACY
                        ]
                    else:
                        if ATTR_VERTICAL_ACCURACY in target.attributes:
                            target.attributes.pop(ATTR_VERTICAL_ACCURACY)

                    target.attributes["source"] = trigger.entity_id
                    target.attributes["reported_state"] = trigger.state
                    target.attributes["person_name"] = string.capwords(
                        trigger.personName
                    )
                    target.attributes["update_time"] = str(datetime.now())

                    # Format new friendly_name and the template to be updated by geocoding:

                    if trigger.state == "Away" or trigger.state.lower() == "on":
                        friendly_name = f"{string.capwords(trigger.personName)} ({trigger.friendlyName}) is {trigger.state}"
                        template = f"{string.capwords(trigger.personName)} ({trigger.friendlyName}) is in <locality>"
                    else:
                        friendly_name = f"{string.capwords(trigger.personName)} ({trigger.friendlyName}) is at {trigger.state}"
                        template = friendly_name
                    target.attributes["friendly_name"] = friendly_name

                    # Determine the zone and the icon to be used based on the zone:

                    if "zone" in trigger.attributes:
                        reportedZone = trigger.attributes["zone"]
                    else:
                        reportedZone = (
                            trigger.state.lower().replace(" ", "_").replace("'", "_")
                        )
                    zoneEntityID = "zone." + reportedZone
                    zoneStateObject = hass.states.get(zoneEntityID)
                    if zoneStateObject != None:
                        zoneAttributesObject = zoneStateObject.attributes.copy()
                        icon = zoneAttributesObject["icon"]
                    else:
                        icon = "mdi:help-circle"
                        if reportedZone != "home":  # (zone.home may not be defined)
                            reportedZone = (
                                trigger.stateHomeAway.lower()
                            )  # clean up the odd "zones"
                            template = f"{string.capwords(trigger.personName)} ({trigger.friendlyName}) is in <locality>"

                    target.attributes["icon"] = icon
                    target.attributes["zone"] = reportedZone
                    _LOGGER.debug(
                        "[handle_process_trigger]" + " zone = %s; icon = %s",
                        reportedZone,
                        target.attributes["icon"],
                    )

                    ha_just_startedObject = hass.states.get(
                        "automation.ha_just_started"
                    )
                    ha_just_started = ha_just_startedObject.state
                    if ha_just_started == "on":
                        _LOGGER.debug(
                            "[handle_process_trigger]" + " ha_just_started = %s",
                            ha_just_started,
                        )

                    if reportedZone == "home":
                        target.attributes[ATTR_LATITUDE] = pli.attributes[
                            "home_latitude"
                        ]
                        target.attributes[ATTR_LONGITUDE] = pli.attributes[
                            "home_longitude"
                        ]

                    # Set up something like https://philhawthorne.com/making-home-assistants-presence-detection-not-so-binary/
                    # If Home Assistant just started, just go with Home or Away as the initial state.

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
                                pli.configuration[CONF_MINUTES_JUST_ARRIVED],
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
                                (pli.configuration[CONF_HOURS_EXTENDED_AWAY] * 60),
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
                                pli.configuration[CONF_MINUTES_JUST_LEFT],
                            )
                            call_rest_command_service(
                                trigger.personName, newTargetState
                            )
                        else:
                            newTargetState = "Away"
                            call_rest_command_service(
                                trigger.personName, newTargetState
                            )

                    if ha_just_started == "on":
                        target.attributes[ATTR_BREAD_CRUMBS] = newTargetState

                    target.state = newTargetState
                    target.attributes["version"] = f"{DOMAIN} {VERSION}"

                    target.set_state()

                    # Call service to "reverse geocode" the location.
                    # For devices at Home, this will only be done initially or on arrival.

                    if (newTargetState == "Home" and oldTargetState == "just left") or (
                        newTargetState == "Just Arrived" and oldTargetState == "away"
                    ):
                        force_update = True
                    else:
                        force_update = False
                    if (
                        newTargetState != "Home"
                        or ha_just_started == "on"
                        or force_update == True
                    ):
                        service_data = {
                            "entity_id": target.entity_id,
                            "friendly_name_template": template,
                            "force_update": force_update,
                        }
                        hass.services.call(
                            DOMAIN, "reverse_geocode", service_data, False
                        )

                _LOGGER.debug("[handle_process_trigger]" + " target_lock release...")
        _LOGGER.debug(
            "[handle_process_trigger]" + " (%s) === Return ===",
            trigger.entity_id,
        )

    def handle_reverse_geocode(call):
        """
        Handle the reverse_geocode service.

        Input:
          - Parameters for the call:
              entity_id
              friendly_name_template (optional)
              force_update (optional)
          - Attributes of entity_id:
            - attributes supplied by another process:
              - latitude
              - longitude
              - update_time (optional)
        Output:
          - determine <locality> for friendly_name
          - record full location from Google_Maps, MapQuest, and/or Open_Street_Map
          - calculate other location-based statistics, such as distance_from_home
          - create/update additional sensors if requested
        """

        entity_id = call.data.get(CONF_ENTITY_ID, "NONE")
        template = call.data.get(CONF_FRIENDLY_NAME_TEMPLATE, "NONE")
        force_update = call.data.get("force_update", False)

        if entity_id == "NONE":
            {
                _LOGGER.warning(
                    "%s is required in call of %s.reverse_geocode service."
                    % (CONF_ENTITY_ID, DOMAIN)
                )
                # return False
            }

        _LOGGER.debug(
            "[handle_reverse_geocode]"
            + " (%s) === Start === %s = %s; %s = %s"
            % (
                entity_id,
                CONF_FRIENDLY_NAME_TEMPLATE,
                template,
                "force_update",
                force_update,
            )
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

                    # Record the integration attributes in the API_STATE_OBJECT:

                    pli.attributes["api_last_updated"] = currentApiTime

                    pli.attributes["api_calls_requested"] += 1

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

                    # Handle the service call, updating the target(entity_id):

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

                        if "location_latitude" in target.entity_sensor_info:
                            old_latitude = target.entity_sensor_info[
                                "location_latitude"
                            ]
                        else:
                            old_latitude = "None"
                        if "location_longitude" in target.entity_sensor_info:
                            old_longitude = target.entity_sensor_info[
                                "location_longitude"
                            ]
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

                            if (
                                pli.attributes["home_latitude"] != "None"
                                and pli.attributes["home_longitude"] != "None"
                            ):
                                old_distance_from_home = round(
                                    distance(
                                        float(old_latitude),
                                        float(old_longitude),
                                        float(pli.attributes["home_latitude"]),
                                        float(pli.attributes["home_longitude"]),
                                    ),
                                    3,
                                )
                            else:
                                old_distance_from_home = 0

                            _LOGGER.debug(
                                "[handle_reverse_geocode]"
                                + " ("
                                + entity_id
                                + ") distance_traveled = "
                                + str(distance_traveled)
                            )
                        else:
                            distance_traveled = 0
                            old_distance_from_home = 0

                        if new_latitude == "None" or new_longitude == "None":
                            _LOGGER.debug(
                                "[handle_reverse_geocode]"
                                + " ("
                                + entity_id
                                + ") Skipping geocoding because coordinates are missing"
                            )
                        elif (
                            distance_traveled < MIN_DISTANCE_TRAVELLED_TO_GEOCODE
                            and old_latitude != "None"
                            and old_longitude != "None"
                            and force_update == False
                        ):
                            _LOGGER.debug(
                                "[handle_reverse_geocode]"
                                + " ("
                                + entity_id
                                + ") Skipping geocoding because distance_traveled < "
                                + str(MIN_DISTANCE_TRAVELLED_TO_GEOCODE)
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

                            if "location_update_time" in target.entity_sensor_info:
                                old_update_time = datetime.strptime(
                                    target.entity_sensor_info["location_update_time"],
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
                            target.attributes[ATTR_METERS_FROM_HOME] = round(
                                distance_from_home, 1
                            )
                            target.attributes[ATTR_MILES_FROM_HOME] = round(
                                distance_from_home / METERS_PER_MILE, 1
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

                            if (
                                pli.configuration[CONF_OSM_API_KEY]
                                != DEFAULT_API_KEY_NOT_SET
                            ):
                                """Call the Open Street Map (Nominatim) API if CONF_OSM_API_KEY is configured"""
                                if (
                                    pli.configuration[CONF_OSM_API_KEY]
                                    == DEFAULT_API_KEY_NOT_SET
                                ):
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
                                        + pli.configuration[CONF_OSM_API_KEY]
                                    )

                                osm_decoded = {}
                                osm_response = get(osm_url)
                                osm_json_input = osm_response.text
                                osm_decoded = json.loads(osm_json_input)

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
                                    osm_attribution = '"' + osm_decoded["licence"] + '"'
                                    attribution += osm_attribution + "; "
                                else:
                                    osm_attribution = ""

                                if (
                                    ATTR_GEOCODED
                                    in pli.configuration[CONF_CREATE_SENSORS]
                                ):
                                    target.make_template_sensor(
                                        "Open_Street_Map",
                                        [
                                            ATTR_LATITUDE,
                                            ATTR_LONGITUDE,
                                            ATTR_SOURCE_TYPE,
                                            ATTR_GPS_ACCURACY,
                                            "icon",
                                            {"locality": locality},
                                            {ATTR_ATTRIBUTION: osm_attribution},
                                        ],
                                    )

                            if (
                                pli.configuration[CONF_GOOGLE_API_KEY]
                                != DEFAULT_API_KEY_NOT_SET
                            ):
                                """Call the Google Maps Reverse Geocoding API if CONF_GOOGLE_API_KEY is configured"""
                                """https://developers.google.com/maps/documentation/geocoding/overview?hl=en_US#ReverseGeocoding"""
                                google_url = (
                                    "https://maps.googleapis.com/maps/api/geocode/json?language="
                                    + pli.configuration[CONF_LANGUAGE]
                                    + "&region="
                                    + pli.configuration[CONF_REGION]
                                    + "&latlng="
                                    + str(new_latitude)
                                    + ","
                                    + str(new_longitude)
                                    + "&key="
                                    + pli.configuration[CONF_GOOGLE_API_KEY]
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
                                            if "locality" in component["types"]:
                                                locality = component["long_name"]
                                                _LOGGER.debug(
                                                    "[handle_reverse_geocode]"
                                                    + " ("
                                                    + entity_id
                                                    + ") Google locality = "
                                                    + locality
                                                )
                                        google_attribution = '"powered by Google"'
                                        attribution += google_attribution + "; "

                                        if (
                                            ATTR_GEOCODED
                                            in pli.configuration[CONF_CREATE_SENSORS]
                                        ):
                                            target.make_template_sensor(
                                                "Google_Maps",
                                                [
                                                    ATTR_LATITUDE,
                                                    ATTR_LONGITUDE,
                                                    ATTR_SOURCE_TYPE,
                                                    ATTR_GPS_ACCURACY,
                                                    "icon",
                                                    {"locality": locality},
                                                    {
                                                        ATTR_ATTRIBUTION: google_attribution
                                                    },
                                                ],
                                            )

                            if (
                                pli.configuration[CONF_MAPQUEST_API_KEY]
                                != DEFAULT_API_KEY_NOT_SET
                            ):
                                """Call the Mapquest Reverse Geocoding API if CONF_MAPQUEST_API_KEY is configured"""
                                """https://developer.mapquest.com/documentation/geocoding-api/reverse/get/"""
                                mapquest_url = (
                                    "https://www.mapquestapi.com/geocoding/v1/reverse"
                                    + "?location="
                                    + str(new_latitude)
                                    + ","
                                    + str(new_longitude)
                                    + "&thumbMaps=false"
                                    + "&key="
                                    + pli.configuration[CONF_MAPQUEST_API_KEY]
                                )
                                mapquest_decoded = {}
                                mapquest_response = get(mapquest_url)
                                mapquest_json_input = mapquest_response.text
                                _LOGGER.debug(
                                    "("
                                    + entity_id
                                    + ") response - "
                                    + mapquest_json_input
                                )
                                mapquest_decoded = json.loads(mapquest_json_input)

                                mapquest_statuscode = mapquest_decoded["info"][
                                    "statuscode"
                                ]
                                if mapquest_statuscode != 0:
                                    _LOGGER.debug(
                                        "[handle_reverse_geocode]"
                                        + " ("
                                        + entity_id
                                        + ") mapquest_statuscode = "
                                        + str(mapquest_statuscode)
                                        + " messages = "
                                        + mapquest_decoded["info"]["messages"]
                                    )
                                else:
                                    if (
                                        "results" in mapquest_decoded
                                        and "locations"
                                        in mapquest_decoded["results"][0]
                                    ):
                                        mapquest_location = mapquest_decoded["results"][
                                            0
                                        ]["locations"][0]

                                        formatted_address = ""
                                        if "street" in mapquest_location:
                                            formatted_address += (
                                                mapquest_location["street"] + ", "
                                            )
                                        if "adminArea5" in mapquest_location:  # city
                                            locality = mapquest_location["adminArea5"]
                                            formatted_address += locality + ", "
                                        elif (
                                            "adminArea4" in mapquest_location
                                            and "adminArea4Type" in mapquest_location
                                        ):  # county
                                            locality = (
                                                mapquest_location["adminArea4"]
                                                + " "
                                                + mapquest_location["adminArea4Type"]
                                            )
                                            formatted_address += locality + ", "
                                        if "adminArea3" in mapquest_location:  # state
                                            formatted_address += (
                                                mapquest_location["adminArea3"] + " "
                                            )
                                        if "postalCode" in mapquest_location:  # zip
                                            formatted_address += (
                                                mapquest_location["postalCode"] + " "
                                            )
                                        if (
                                            "adminArea1" in mapquest_location
                                            and mapquest_location["adminArea1"] != "US"
                                        ):  # country
                                            formatted_address += mapquest_location[
                                                "adminArea1"
                                            ]

                                        _LOGGER.debug(
                                            "[handle_reverse_geocode]"
                                            + " ("
                                            + entity_id
                                            + ") mapquest formatted_address = "
                                            + formatted_address
                                        )
                                        target.attributes[
                                            "MapQuest"
                                        ] = formatted_address

                                        _LOGGER.debug(
                                            "[handle_reverse_geocode]"
                                            + " ("
                                            + entity_id
                                            + ") mapquest locality = "
                                            + locality
                                        )

                                        mapquest_attribution = (
                                            '"'
                                            + mapquest_decoded["info"]["copyright"][
                                                "text"
                                            ]
                                            + '"'
                                        )
                                        attribution += mapquest_attribution + "; "

                                        if (
                                            ATTR_GEOCODED
                                            in pli.configuration[CONF_CREATE_SENSORS]
                                        ):
                                            target.make_template_sensor(
                                                "MapQuest",
                                                [
                                                    ATTR_LATITUDE,
                                                    ATTR_LONGITUDE,
                                                    ATTR_SOURCE_TYPE,
                                                    ATTR_GPS_ACCURACY,
                                                    "icon",
                                                    {"locality": locality},
                                                    {
                                                        ATTR_ATTRIBUTION: mapquest_attribution
                                                    },
                                                ],
                                            )

                            if template != "NONE":
                                target.attributes["friendly_name"] = template.replace(
                                    "<locality>", locality
                                )
                            target.entity_sensor_info["geocode_count"] += 1
                            target.entity_sensor_info[
                                "location_latitude"
                            ] = new_latitude
                            target.entity_sensor_info[
                                "location_longitude"
                            ] = new_longitude
                            target.entity_sensor_info["location_update_time"] = str(
                                new_update_time
                            )
                            if "reported_state" in target.attributes:
                                if target.attributes["reported_state"] != "Away":
                                    newBreadCrumb = target.attributes["reported_state"]
                                else:
                                    newBreadCrumb = locality
                            else:
                                newBreadCrumb = locality
                            if ATTR_BREAD_CRUMBS in target.attributes:
                                oldBreadCrumbs = target.attributes[ATTR_BREAD_CRUMBS]
                                if not oldBreadCrumbs.endswith(newBreadCrumb):
                                    target.attributes[ATTR_BREAD_CRUMBS] = (
                                        oldBreadCrumbs + "> " + newBreadCrumb
                                    )
                            else:
                                target.attributes[ATTR_BREAD_CRUMBS] = newBreadCrumb

                            # Call WazeRouteCalculator if not at Home:
                            if pli.configuration["use_waze"] == False:
                                pass
                            elif (
                                target.attributes[ATTR_METERS_FROM_HOME]
                                < WAZE_MIN_METERS_FROM_HOME
                            ):
                                target.attributes[ATTR_DRIVING_MILES] = "0"
                                target.attributes[ATTR_DRIVING_MINUTES] = "0"
                            else:
                                try:
                                    """
                                    Figure it out from:
                                    https://github.com/home-assistant/core/blob/dev/homeassistant/components/waze_travel_time/sensor.py
                                    https://github.com/kovacsbalu/WazeRouteCalculator
                                    """
                                    _LOGGER.debug(
                                        "[handle_reverse_geocode]"
                                        + " (("
                                        + entity_id
                                        + ") Waze calculation"
                                    )

                                    from_location = (
                                        str(new_latitude) + "," + str(new_longitude)
                                    )
                                    to_location = (
                                        str(pli.attributes["home_latitude"])
                                        + ","
                                        + str(pli.attributes["home_longitude"])
                                    )
                                    route = WazeRouteCalculator.WazeRouteCalculator(
                                        from_location,
                                        to_location,
                                        pli.configuration["waze_region"],
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
                                        target.attributes[ATTR_DRIVING_MILES] = str(
                                            round(routeDistance, 0)
                                        )
                                    elif routeDistance >= 10:
                                        target.attributes[ATTR_DRIVING_MILES] = str(
                                            round(routeDistance, 1)
                                        )
                                    else:
                                        target.attributes[ATTR_DRIVING_MILES] = str(
                                            round(routeDistance, 2)
                                        )
                                    _LOGGER.debug(
                                        "[handle_reverse_geocode]"
                                        + " ("
                                        + entity_id
                                        + ") Waze routeTime "
                                        + str(routeTime)
                                    )  # minutes
                                    target.attributes[ATTR_DRIVING_MINUTES] = str(
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
                                        + ") Waze Exception "
                                        + type(e).__name__
                                        + ": "
                                        + str(e)
                                    )
                                    _LOGGER.debug(traceback.format_exc())
                                    pli.attributes["waze_error_count"] += 1
                                    target.attributes.pop(ATTR_DRIVING_MILES)
                                    target.attributes.pop(ATTR_DRIVING_MINUTES)

                        target.attributes[ATTR_ATTRIBUTION] = attribution

                        target.set_state()

                        target.make_template_sensors()

                        _LOGGER.debug(
                            "[handle_reverse_geocode]" + " target_lock release..."
                        )
            except Exception as e:
                _LOGGER.error(
                    "[handle_reverse_geocode]"
                    + " (%s) Exception %s: %s" % (entity_id, type(e).__name__, str(e))
                )
                _LOGGER.debug(traceback.format_exc())
                pli.attributes["api_error_count"] += 1

            pli.set_state()
            _LOGGER.debug("[handle_reverse_geocode]" + " integration_lock release...")
        _LOGGER.debug("[handle_reverse_geocode] (%s) === Return ===", entity_id)

    def handle_geocode_api_on(call):
        """Turn on the geocode service."""

        _LOGGER.debug("[geocode_api_on] === Start===")
        with integration_lock:
            """Lock while updating the pli(API_STATE_OBJECT)."""
            _LOGGER.debug("[handle_geocode_api_on]" + " integration_lock obtained")

            _LOGGER.debug("Setting " + API_STATE_OBJECT + " on")
            pli.state = "on"
            pli.attributes["icon"] = "mdi:api"
            pli.set_state()
            _LOGGER.debug("[geocode_api_on]" + " integration_lock release...")
        _LOGGER.debug("[geocode_api_on] === Return ===")

    def handle_geocode_api_off(call):
        """Turn off the geocode service. """

        _LOGGER.debug("[geocode_api_off] === Start ===")
        with integration_lock:
            """Lock while updating the pli(API_STATE_OBJECT)."""
            _LOGGER.debug("[handle_geocode_api_off]" + " integration_lock obtained")

            _LOGGER.debug("Setting " + API_STATE_OBJECT + " off")
            pli.state = "off"
            pli.attributes["icon"] = "mdi:api-off"
            pli.set_state()
            _LOGGER.debug("[handle_geocode_api_off]" + " integration_lock release...")
        _LOGGER.debug("[geocode_api_off] === Return ===")

    async def async_setup_entry(hass, entry):
        """Process config_flow configuration and options."""

        _LOGGER.debug(
            "[async_setup_entry] === Start === -data: %s -options: %s",
            entry.data,
            entry.options,
        )

        pli.configuration.update(entry.data)
        pli.configuration.update(entry.options)

        hass.data[DOMAIN][DATA_CONFIGURATION] = pli.configuration

        _LOGGER.debug("[async_setup_entry] === Return ===")
        return True

    hass.data[DOMAIN][DATA_ASYNC_SETUP_ENTRY] = async_setup_entry

    hass.services.register(DOMAIN, "reverse_geocode", handle_reverse_geocode)
    hass.services.register(DOMAIN, "geocode_api_on", handle_geocode_api_on)
    hass.services.register(DOMAIN, "geocode_api_off", handle_geocode_api_off)
    hass.services.register(DOMAIN, "process_trigger", handle_process_trigger)

    pli.set_state()

    _LOGGER.debug("[setup] === Return ===")
    # Return boolean to indicate that setup was successful.
    return True


# ------------------------------------------------------------------


async def async_setup_entry(hass, entry):
    """Accept conf_flow configuration."""

    hass.data[DOMAIN][DATA_CONFIG_ENTRY] = entry

    if DATA_UNDO_UPDATE_LISTENER not in hass.data[DOMAIN]:
        hass.data[DOMAIN][DATA_UNDO_UPDATE_LISTENER] = entry.add_update_listener(
            async_options_update_listener
        )

    return await hass.data[DOMAIN][DATA_ASYNC_SETUP_ENTRY](hass, entry)


async def async_options_update_listener(hass, entry):
    """Accept conf_flow options."""

    return await hass.data[DOMAIN][DATA_ASYNC_SETUP_ENTRY](hass, entry)


async def async_unload_entry(hass, entry):
    """Unload a config entry."""

    _LOGGER.debug("===== async_unload_entry")
    if DATA_UNDO_UPDATE_LISTENER in hass.data[DOMAIN]:
        hass.data[DOMAIN][DATA_UNDO_UPDATE_LISTENER]()

    hass.data[DOMAIN].pop(DATA_UNDO_UPDATE_LISTENER)
    hass.data[DOMAIN].pop(DATA_CONFIG_ENTRY)

    return True
