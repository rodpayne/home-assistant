#==================================================================================================
#  python_scripts/person_sensor_update.py 
#==================================================================================================
#
#    Input: 
#            - state changes of a device tracker, triggers automation "Person Sensor Update" 
#              which calls this script 
#              Attributes:
#              - account_name: <personName>
#            - automation.ha_just_started: 
#              on for a few minutes so that "Just Arrived" and "Just Left" don't get set at startup 
#    Output: 
#            - updated "sensor.<personName>_status" with <personName>'s location and status:
#              Attributes:
#              - all attributes from last triggered device tracker
#              - state: "Just Arrived", "Home", "Just Left", "Away", or "Extended Away"
#              - person_name: <personName>
#              - entity_id: entity_id of the device tracker that triggered the automation
#              - reported_state: the state reported by device tracker = "Home", "Away", or <zone>
#              - friendly_name: something like "Rod (i.e. Rod's watch) is at Drew's"
#            - call rest_command service to update HomeSeer: 'homeseer_<personName>_<state>'
#
#==================================================================================================

#--------------------------------------------------------------------------------------------------
# Get Data from the Automation Trigger
#--------------------------------------------------------------------------------------------------

triggeredEntity = data.get('entity_id')
triggeredStateObject = hass.states.get(triggeredEntity)
triggeredStatus = triggeredStateObject.state
triggeredAttributesObject = triggeredStateObject.attributes.copy()
if 'friendly_name' in triggeredAttributesObject:
  triggeredFriendlyName = triggeredAttributesObject['friendly_name']
else:
  triggeredFriendlyName = ''
  logger.debug("friendly_name attribute is missing")

if triggeredStatus.lower() == 'home':
  triggeredStatusHomeAway = 'Home'
  triggeredStatus = 'Home'
elif triggeredStatus == 'on':
  triggeredStatusHomeAway = 'Home'
else: 
  triggeredStatusHomeAway = 'Away'
  if triggeredStatus == 'not_home':
    triggeredStatus = 'Away'

logger.debug("===== triggered entity = {2} ({0}) ; triggered state = {1}".format(triggeredEntity,triggeredStatus,triggeredFriendlyName))

#--------------------------------------------------------------------------------------------------
# Is triggeredEntity like "sensor.<name>_status" ?  
#--------------------------------------------------------------------------------------------------
# - this is triggered by one of the following automations rather than a state change:
#   "Mark person as Home" after a few minutes with "Just Arrived" --> "Home"
#   "Mark person as Away" after a few minutes with "Just Left" --> "Away"
#   "Mark person as Extended Away" after 24 hours with "Away" --> "Extended Away"
#--------------------------------------------------------------------------------------------------
if (triggeredEntity.find('sensor.') == 0) and (triggeredEntity.find('_status') > 0):
  personNameEnd = triggeredEntity.find('_',7)
  personName = triggeredEntity[7:personNameEnd]
  
  sensorName = "sensor." + personName + "_status"
  
  oldStateObject = hass.states.get(sensorName)
  oldStatus = oldStateObject.state.lower()
  oldAttributesObject = oldStateObject.attributes.copy()
  
  newStatus = data.get('state_change')

  logger.info("setting sensor name = {0}; old state = {3}; new state = {1}; from entity_id = {2}".format(sensorName,newStatus,triggeredEntity,oldStatus))
  
  rest_command = 'homeseer_' + personName.lower() + '_' + newStatus.lower().replace(" ", "_")
  try:
    hass.services.call('rest_command', rest_command)
  except:
    logger.debug("rest_command {0} not defined".format(rest_command))

  hass.states.set(sensorName, newStatus, oldAttributesObject)

#--------------------------------------------------------------------------------------------------
# Is triggeredEntity like "device_tracker.apple_watch" ?
# Is triggeredEntity like "binary_sensor.rods_iphone_wireless" ?
# Is triggeredEntity like "sensor.ford_focus_location" ?
#--------------------------------------------------------------------------------------------------
# - assumption is that the last device to change zone state is an indicator of where a person is,
#   because devices left at home should not change zones
#--------------------------------------------------------------------------------------------------
elif (triggeredEntity.find('device_tracker.') == 0) or (triggeredEntity.find('binary_sensor.') == 0) or (triggeredEntity.find('sensor.') == 0):
  triggeredFrom = data.get('from_state')
  triggeredTo = data.get('to_state')
  
  if 'person_name' in triggeredAttributesObject:
    personName = triggeredAttributesObject['person_name']
  else:
    if 'account_name' in triggeredAttributesObject:
      personName = triggeredAttributesObject['account_name']
    else:
      if 'owner_fullname' in triggeredAttributesObject:
        personName = triggeredAttributesObject['owner_fullname'].split()[0].lower()
      else:
        personName = 'unknown'
        logger.debug("account_name (or person_name) attribute is missing") 
  if 'source_type' in triggeredAttributesObject:
      sourceType = triggeredAttributesObject['source_type'] 
  else:
      sourceType = 'other'

  sensorName = "sensor." + personName + "_status"

  # get the current state of the output sensor and decide if new values should be saved:
  saveThisUpdate = False

  oldStateObject = hass.states.get(sensorName)

  if triggeredTo == 'NotSet':
    logger.debug("skipping because triggeredTo = {0}".format(triggeredFrom))
  elif oldStateObject == None:                                            # first time?
    saveThisUpdate = True
    logger.debug("entity {0} does not yet exist (normal at startup)".format(sensorName))
    oldStatus = 'none'
  else:
    oldStatus = oldStateObject.state.lower()
    oldAttributesObject = oldStateObject.attributes.copy()
    if oldStatus == 'unknown':
      saveThisUpdate = True
      logger.debug("accepting the first update")
    elif sourceType == 'gps':                                               # gps device?  
      if triggeredTo != triggeredFrom:                                      # did it change zones?
        saveThisUpdate = True                                                 # gps changing zones is assumed to be new, correct info
      else:
        if not('entity_id' in oldAttributesObject) or not('reported_state' in oldAttributesObject) or oldAttributesObject['entity_id'] == triggeredEntity:           # same entity as we are following?
          saveThisUpdate = True                                           # same tracker as we are following (or this it the first one)
        elif triggeredStatus == oldAttributesObject['reported_state']:    # same status as the one we are following?
          if 'gps_accuracy' in triggeredAttributesObject and 'gps_accuracy' in oldAttributesObject:
            if triggeredAttributesObject['gps_accuracy'] < oldAttributesObject['gps_accuracy']:     # better choice?
              saveThisUpdate = True
              logger.debug("gps_accuracy is better")
    else:                                                                 # source = router or ping
      if triggeredTo != triggeredFrom:                                      # did it change state?
          if triggeredStatusHomeAway == 'Home':                                 # reporting Home
            if oldStatus != 'home':                                       # no additional information if already Home
              saveThisUpdate = True
          else:                                                                 # reporting Away
            if oldStatus == 'home':                                       # no additional information if already Away
              saveThisUpdate = True

  if saveThisUpdate == True:
    logger.debug("account_name/personName = {0}; triggeredFrom = {1}; triggeredTo = {2}; source_type = {3}".format(personName,triggeredFrom,triggeredTo,sourceType))
    newStatus = triggeredStatusHomeAway
    newAttributesObject = triggeredAttributesObject
    newAttributesObject['entity_id'] = triggeredEntity
    newAttributesObject['reported_state'] = triggeredStatus
    newAttributesObject['person_name'] = string.capwords(personName) 
    newAttributesObject['update_time'] = str(datetime.datetime.now())

    if triggeredStatus == 'Away' or triggeredStatus.lower() == 'on':
      newAttributesObject['friendly_name'] = "{0} (i.e. {1}) is {2}".format(string.capwords(personName),triggeredFriendlyName,triggeredStatus) 
    else:
      newAttributesObject['friendly_name'] = "{0} (i.e. {1}) is at {2}".format(string.capwords(personName),triggeredFriendlyName,triggeredStatus) 

    zoneStateObject = hass.states.get('zone.' + triggeredStatus)
    if zoneStateObject != None:
      zoneAttributesObject = zoneStateObject.attributes.copy()
      newAttributesObject['icon'] = zoneAttributesObject['icon']
    else:
      newAttributesObject['icon'] = 'mdi:help-circle'
    ha_just_startedObject = hass.states.get('automation.ha_just_started')
    ha_just_started = ha_just_startedObject.state
    if ha_just_started == 'on':
      logger.debug("ha_just_started = {0}".format(ha_just_started))

# Set up something like https://philhawthorne.com/making-home-assistants-presence-detection-not-so-binary/  

    if triggeredStatusHomeAway == 'Home':
      if oldStatus == 'none' or ha_just_started == 'on' or oldStatus == 'just left':
        newStatus = 'Home'
        try:
          hass.services.call('rest_command', 'homeseer_' + personName.lower() + '_home')
        except:
          logger.debug("rest_command homeseer_{0}_home not defined".format(personName.lower()))
      elif oldStatus == 'home':
        newStatus = 'Home'
      elif oldStatus == 'just arrived': 
        newStatus = 'Just Arrived'
      else:
        newStatus = 'Just Arrived'
        try:
          hass.services.call('rest_command', 'homeseer_' + personName.lower() + '_just_arrived')
        except:
          logger.debug("rest_command homeseer_{0}_just_arrived not defined".format(personName.lower()))
#        if personName.lower() == 'rod':
#          hass.services.call('notify', 'ios_rods_iphone_app', {"message": "Welcome Home " + string.capwords(personName),"data": {"push": {"sound": "US-EN-Morgan-Freeman-Welcome-Home.wav"}}})
#          hass.services.call('media_player', 'alexa', {"entity_id": "media_player.kitchen", "message": string.capwords(personName) + ", Welcome Home!"})
#        hass.services.call('mqtt', 'publish', { "topic": "homeassistant/kitchen_tts", "payload": string.capwords(personName) + ", Welcome Home!" })
    else:
      if oldStatus == 'none' or ha_just_started == 'on':
        newStatus = 'Away'
        try:
          hass.services.call('rest_command', 'homeseer_' + personName.lower() + '_away')
        except:
          logger.debug("rest_command homeseer_{0}_away not defined".format(personName.lower()))
      elif oldStatus == 'just left':
        newStatus = 'Just Left'
      elif oldStatus == 'home' or oldStatus == 'just arrived':
        newStatus = 'Just Left'
        try:
          hass.services.call('rest_command', 'homeseer_' + personName.lower() + '_just_left')
        except:
          logger.debug("rest_command homeseer_{0}_just_left not defined".format(personName.lower()))
      else:
        newStatus = 'Away'
        try:
          hass.services.call('rest_command', 'homeseer_' + personName.lower() + '_away')
        except:
          logger.debug("rest_command homeseer_{0}_away not defined".format(personName.lower()))
    
    logger.info("setting sensor name = {0}; oldStatus = {3}; newStatus = {1}; friendly_name = {2}; icon = {4}".format(sensorName,newStatus,newAttributesObject['friendly_name'],oldStatus,newAttributesObject['icon']))

    hass.states.set(sensorName, newStatus, newAttributesObject)
