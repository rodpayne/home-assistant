# ==================================================================================================
#  python_scripts/person_location_update.py
# ==================================================================================================
#
#    Input:
#            - state changes of a device tracker, triggers automation "Person Sensor Update"
#              which calls this script
#              Attributes:
#              - account_name: <personName>
#            - automation.ha_just_started:
#              on for a few minutes so that "Just Arrived" and "Just Left" don't get set at startup
#    Output:
#            - updated "sensor.<personName>_location" with <personName>'s location and status:
#              Attributes:
#              - selected attributes from last triggered device tracker
#              - state: "Just Arrived", "Home", "Just Left", "Away", or "Extended Away"
#              - person_name: <personName>
#              - source: entity_id of the device tracker that triggered the automation
#              - reported_state: the state reported by device tracker = "Home", "Away", or <zone>
#              - friendly_name: something like "Rod (i.e. Rod's watch) is at Drew's"
#              - icon: the icon that correspondes with the current zone
#            - call rest_command service to update HomeSeer: 'homeseer_<personName>_<state>'
#
# ==================================================================================================


def call_rest_command_service(personName, newState):
    """ (Optionally) send HomeSeer a notification of the state change. """
    rest_command = ""
    rest_command = (
        "homeseer_" + personName.lower() + "_" + newState.lower().replace(" ", "_")
    )
    try:
        hass.services.call("rest_command", rest_command)
    except Exception as e:
        logger.debug("rest_command %s exception %s", rest_command, str(e))


# --------------------------------------------------------------------------------------------------
# Get Data from the Automation Trigger
# --------------------------------------------------------------------------------------------------

triggerName = data.get("entity_id")
triggerStateObject = hass.states.get(triggerName)
triggerState = triggerStateObject.state
triggerAttributesObject = triggerStateObject.attributes.copy()
if "friendly_name" in triggerAttributesObject:
    triggerFriendlyName = triggerAttributesObject["friendly_name"]
else:
    triggerFriendlyName = ""
    logger.debug("friendly_name attribute is missing")

if triggerState.lower() == "home":
    triggerStateHomeAway = "Home"
    triggerState = "Home"
elif triggerState == "on":
    triggerStateHomeAway = "Home"
else:
    triggerStateHomeAway = "Away"
    if triggerState == "not_home":
        triggerState = "Away"

if "person_name" in triggerAttributesObject:
    personName = triggerAttributesObject["person_name"]
elif "account_name" in triggerAttributesObject:
    personName = triggerAttributesObject["account_name"]
elif "owner_fullname" in triggerAttributesObject:
    personName = triggerAttributesObject["owner_fullname"].split()[0].lower()
else:
    personName = triggerName.split(".")[1].split("_")[0].lower()
    logger.warning(
        'The account_name (or person_name) attribute is missing in %s, trying "%s"',
        triggerName,
        personName,
    )

targetName = "sensor." + personName.lower() + "_location"

# At this point, we know the following from the device tracker or sensor:

# personName = associated person.
# targetName = our output person location sensor.
# triggerAttributesObject = the attributes.
# triggerFriendlyName = the friendly name.
# triggerName = the entity_id.
# triggerState = "Home", "Away", or the name of a zone supplied by the device tracker.
# triggerStateHomeAway = the generic state, either "Home" or "Away".

logger.debug(
    "===== triggered entity = %s (%s); target = %s; triggerState = %s; triggerStateHomeAway = %s; personName = %s",
    triggerFriendlyName,
    triggerName,
    targetName,
    triggerState,
    triggerStateHomeAway,
    personName,
)

# --------------------------------------------------------------------------------------------------
# Is triggerName like "sensor.<name>_location" (one of our output sensors)?
# --------------------------------------------------------------------------------------------------
# - this is triggered by one of the following automations rather than a state change:
#   "Mark person as Home" after a few minutes with "Just Arrived" --> "Home"
#   "Mark person as Away" after a few minutes with "Just Left" --> "Away"
#   "Mark person as Extended Away" after 24 hours with "Away" --> "Extended Away"
# --------------------------------------------------------------------------------------------------
if triggerName == targetName:
    change_state_to = data.get("change_state_to")
    if change_state_to != "None":
        logger.debug("setting %s: change_state_to = %s", triggerName, change_state_to)

        call_rest_command_service(personName, change_state_to)
        hass.states.set(triggerName, change_state_to, triggerAttributesObject)

# --------------------------------------------------------------------------------------------------
# Is triggerName like "device_tracker.apple_watch" ?
# Is triggerName like "binary_sensor.rods_iphone_wireless" ?
# Is triggerName like "sensor.ford_focus_location" ?
# --------------------------------------------------------------------------------------------------
# - assumption is that the last device to change zone state is an indicator of where a person is,
#   because devices left at home should not change zones.
# --------------------------------------------------------------------------------------------------
# elif (
#    (triggerName.find("device_tracker.") == 0)
#    or (triggerName.find("binary_sensor.") == 0)
#    or (triggerName.find("sensor.") == 0)
# ):
else:
    # Get more from the triggered device tracker or sensor.
    triggerFrom = data.get("from_state")
    triggerTo = data.get("to_state")

    if "source_type" in triggerAttributesObject:
        triggerSourceType = triggerAttributesObject["source_type"]
    else:
        triggerSourceType = "other"

    logger.debug(
        "triggerFrom = %s; triggerTo = %s; source_type = %s",
        triggerFrom,
        triggerTo,
        triggerSourceType,
    )

    # -----------------------------------------------------------------------------
    # Get the current state of the target person location sensor and
    # decide if it should be updated with values from the triggered device tracker.
    saveThisUpdate = False
    # -----------------------------------------------------------------------------

    targetStateObject = hass.states.get(targetName)

    if triggerTo == "NotSet":
        logger.debug("Skipping update because triggerTo = %s", triggerTo)
    elif targetStateObject == None:  # first time?
        saveThisUpdate = True
        logger.debug("Target %s does not yet exist (normal at startup)", targetName)
        oldTargetState = "none"
        targetAttributesObject = {}
    else:
        oldTargetState = targetStateObject.state.lower()
        targetAttributesObject = targetStateObject.attributes.copy()
        if oldTargetState == "unknown":
            saveThisUpdate = True
            logger.debug("Accepting the first update of %s", targetName)
        elif triggerSourceType == "gps":  # gps device?
            if triggerTo != triggerFrom:  # did it change zones?
                saveThisUpdate = (
                    True  # gps changing zones is assumed to be new, correct info
                )
            else:
                if (
                    not ("source" in targetAttributesObject)
                    or not ("reported_state" in targetAttributesObject)
                    or targetAttributesObject["source"] == triggerName
                ):  # same entity as we are following?
                    saveThisUpdate = True  # same tracker as we are following (or this is the first one)
                elif (
                    triggerState == targetAttributesObject["reported_state"]
                ):  # same status as the one we are following?
                    if "vertical_accuracy" in triggerAttributesObject:
                        if (not ("vertical_accuracy" in targetAttributesObject)) or (
                            triggerAttributesObject["vertical_accuracy"] > 0
                            and targetAttributesObject["vertical_accuracy"] == 0
                        ):  # better choice based on accuracy?
                            saveThisUpdate = True
                            logger.debug(
                                "The vertical_accuracy is better than %s",
                                targetAttributesObject["source"],
                            )
                    if (
                        "gps_accuracy" in triggerAttributesObject
                        and "gps_accuracy" in targetAttributesObject
                        and triggerAttributesObject["gps_accuracy"]
                        < targetAttributesObject["gps_accuracy"]
                    ):  # better choice based on accuracy?
                        saveThisUpdate = True
                        logger.debug(
                            "The gps_accuracy is better than %s",
                            targetAttributesObject["source"],
                        )
        else:  # source = router or ping
            if triggerTo != triggerFrom:  # did it change state?
                if triggerStateHomeAway == "Home":  # reporting Home
                    if (
                        oldTargetState != "home"
                    ):  # no additional information if already Home
                        saveThisUpdate = True
                else:  # reporting Away
                    if (
                        oldTargetState == "home"
                    ):  # no additional information if already Away
                        saveThisUpdate = True

    # -----------------------------------------------------------------------------

    if saveThisUpdate == True:

        # Be selective about attributes carried in the target sensor:

        if "source_type" in triggerAttributesObject:
            targetAttributesObject["source_type"] = triggerAttributesObject[
                "source_type"
            ]
        else:
            if "source_type" in targetAttributesObject:
                targetAttributesObject.pop("source_type")

        if (
            "latitude" in triggerAttributesObject
            and "longitude" in triggerAttributesObject
        ):
            targetAttributesObject["latitude"] = triggerAttributesObject["latitude"]
            targetAttributesObject["longitude"] = triggerAttributesObject["longitude"]
        else:
            if "latitude" in targetAttributesObject:
                targetAttributesObject.pop("latitude")
            if "longitude" in targetAttributesObject:
                targetAttributesObject.pop("longitude")

        if "gps_accuracy" in triggerAttributesObject:
            targetAttributesObject["gps_accuracy"] = triggerAttributesObject[
                "gps_accuracy"
            ]
        else:
            if "gps_accuracy" in targetAttributesObject:
                targetAttributesObject.pop("gps_accuracy")

        if "altitude" in triggerAttributesObject:
            targetAttributesObject["altitude"] = round(
                triggerAttributesObject["altitude"], 0
            )
        else:
            if "altitude" in targetAttributesObject:
                targetAttributesObject.pop("altitude")

        if "vertical_accuracy" in triggerAttributesObject:
            targetAttributesObject["vertical_accuracy"] = triggerAttributesObject[
                "vertical_accuracy"
            ]
        else:
            if "vertical_accuracy" in targetAttributesObject:
                targetAttributesObject.pop("vertical_accuracy")

        targetAttributesObject["source"] = triggerName
        targetAttributesObject["reported_state"] = triggerState
        targetAttributesObject["person_name"] = string.capwords(personName)
        targetAttributesObject["update_time"] = str(datetime.datetime.now())

        # Format new friendly_name and the template to be updated by geocoding.

        if (
            triggerState == "Away"
            or triggerState == "Stationary"
            or triggerState.lower() == "on"
        ):
            friendly_name = f"{string.capwords(personName)} ({triggerFriendlyName}) is {triggerState}"
            template = f"{string.capwords(personName)} ({triggerFriendlyName}) is in <locality>"
        else:
            friendly_name = f"{string.capwords(personName)} ({triggerFriendlyName}) is at {triggerState}"
            template = friendly_name
        targetAttributesObject["friendly_name"] = friendly_name

        # Determine the icon to be used, based on the zone.

        if "zone" in triggerAttributesObject:
            zoneEntityID = "zone." + triggerAttributesObject["zone"]
        else:
            zoneEntityID = "zone." + triggerState.lower().replace(" ", "_").replace(
                "'", "_"
            )
        zoneStateObject = hass.states.get(zoneEntityID)
        if zoneStateObject != None:
            zoneAttributesObject = zoneStateObject.attributes.copy()
            targetAttributesObject["icon"] = zoneAttributesObject["icon"]
        else:
            targetAttributesObject["icon"] = "mdi:help-circle"
        logger.debug(
            "zone = %s; icon = %s", zoneEntityID, targetAttributesObject["icon"]
        )

        # Set up something like https://philhawthorne.com/making-home-assistants-presence-detection-not-so-binary/
        # If Home Assistant just started, just go with Home or Away as the initial state.

        ha_just_startedObject = hass.states.get("automation.ha_just_started")
        ha_just_started = ha_just_startedObject.state
        if ha_just_started == "on":
            logger.debug("ha_just_started = %s", ha_just_started)

        if triggerStateHomeAway == "Home":
            if (
                oldTargetState == "none"
                or ha_just_started == "on"
                or oldTargetState == "just left"
            ):
                newTargetState = "Home"
                call_rest_command_service(personName, newTargetState)
            elif oldTargetState == "home":
                newTargetState = "Home"
            elif oldTargetState == "just arrived":
                newTargetState = "Just Arrived"
            else:
                newTargetState = "Just Arrived"
                call_rest_command_service(personName, newTargetState)
        else:
            if oldTargetState == "none" or ha_just_started == "on":
                newTargetState = "Away"
                call_rest_command_service(personName, newTargetState)
            elif oldTargetState == "just left":
                newTargetState = "Just Left"
            elif oldTargetState == "home" or oldTargetState == "just arrived":
                newTargetState = "Just Left"
                call_rest_command_service(personName, newTargetState)
            else:
                newTargetState = "Away"
                call_rest_command_service(personName, newTargetState)

        logger.debug(
            "setting sensor name = %s; oldTargetState = %s; newTargetState = %s",
            targetName,
            oldTargetState,
            newTargetState,
        )

        hass.states.set(targetName, newTargetState, targetAttributesObject)
        logger.debug(targetAttributesObject)

        # --------------------------------------------------------------------------------------------------
        # Call service to "reverse geocode" the location:
        # - determine <locality> for friendly_name
        # - record full location in OSM_location
        # - calculate other location-based statistics, such as distance_from_home
        # For devices at Home, this will only be done initially or on arrival (newTargetState = 'Just Arrived')
        # --------------------------------------------------------------------------------------------------
        if newTargetState != "Home" or ha_just_started == "on":
            try:
                service_data = {
                    "entity_id": targetName,
                    "friendly_name_template": template,
                }
                hass.services.call(
                    "person_location", "reverse_geocode", service_data, True
                )
                logger.debug("person_location reverse_geocode service call completed")
            except Exception as e:
                logger.debug(
                    "person_location reverse_geocode service call exception: %s", str(e)
                )
