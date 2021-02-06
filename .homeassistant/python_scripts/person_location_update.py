#==================================================================================================
#  python_scripts/person_location_update.py 
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
# Is triggeredEntity like "sensor.<name>_location" ?  
#--------------------------------------------------------------------------------------------------
# - this is triggered by one of the following automations rather than a state change:
#   "Mark person as Home" after a few minutes with "Just Arrived" --> "Home"
#   "Mark person as Away" after a few minutes with "Just Left" --> "Away"
#   "Mark person as Extended Away" after 24 hours with "Away" --> "Extended Away"
#--------------------------------------------------------------------------------------------------
if (triggeredEntity.find('sensor.') == 0) and (triggeredEntity.find('_location') > 0):
  personNameEnd = triggeredEntity.find('_',7)
  personName = triggeredEntity[7:personNameEnd]
  
  sensorName = "sensor." + personName + "_location"
  
  oldStateObject = hass.states.get(sensorName)
  oldStatus = oldStateObject.state.lower()
  oldAttributesObject = oldStateObject.attributes.copy()
  
  newStatus = data.get('state_change')

  logger.debug("setting sensor name = {0}; old state = {3}; new state = {1}; from entity_id = {2}".format(sensorName,newStatus,triggeredEntity,oldStatus))
  
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
#   because devices left at home should not change zones.
#--------------------------------------------------------------------------------------------------
elif (triggeredEntity.find('device_tracker.') == 0) or (triggeredEntity.find('binary_sensor.') == 0) or (triggeredEntity.find('sensor.') == 0):
  triggeredFrom = data.get('from_state')
  triggeredTo = data.get('to_state')
  
  if 'person_name' in triggeredAttributesObject:
    personName = triggeredAttributesObject['person_name']
  elif 'account_name' in triggeredAttributesObject:
    personName = triggeredAttributesObject['account_name']
  elif 'owner_fullname' in triggeredAttributesObject:
    personName = triggeredAttributesObject['owner_fullname'].split()[0].lower()
  else:
    personName = triggeredEntity.split('.')[1].split('_')[0].lower()
    logger.warning('account_name (or person_name) attribute is missing, trying "{0}"'.format(person_name)) 
  if 'source_type' in triggeredAttributesObject:
      sourceType = triggeredAttributesObject['source_type'] 
  else:
      sourceType = 'other'

  sensorName = "sensor." + personName + "_location"
  logger.debug("sensor name = {0};".format(sensorName))


  # get the current state of the output sensor and decide if new values should be saved:
  saveThisUpdate = False

  oldStateObject = hass.states.get(sensorName)

  if triggeredTo == 'NotSet':
    logger.debug("skipping because triggeredTo = {0}".format(triggeredFrom))
  elif oldStateObject == None:                                            # first time?
    saveThisUpdate = True
    logger.debug("entity {0} does not yet exist (normal at startup)".format(sensorName))
    oldStatus = 'none'
    oldAttributesObject = {}
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
        if not('source' in oldAttributesObject) or not('reported_state' in oldAttributesObject) or oldAttributesObject['source'] == triggeredEntity:           # same entity as we are following?
          saveThisUpdate = True                                           # same tracker as we are following (or this it the first one)
        elif triggeredStatus == oldAttributesObject['reported_state']:    # same status as the one we are following?
          if not('vertical_accuracy' in oldAttributesObject) or ('vertical_accuracy' in triggeredAttributesObject and (triggeredAttributesObject['vertical_accuracy'] > 0 and oldAttributesObject['vertical_accuracy'] == 0)):     # better choice based on accuracy?
            saveThisUpdate = True
            logger.debug("vertical_accuracy is better")
          if 'gps_accuracy' in triggeredAttributesObject and 'gps_accuracy' in oldAttributesObject and triggeredAttributesObject['gps_accuracy'] < oldAttributesObject['gps_accuracy']:     # better choice based on accuracy?
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
#   Be selective about attributes carried in the sensor:
    newAttributesObject = oldAttributesObject
    if 'source_type' in triggeredAttributesObject:
      newAttributesObject['source_type'] = triggeredAttributesObject['source_type']
    else:
      if 'source_type' in newAttributesObject:
        newAttributesObject.pop('source_type')
    if 'latitude' in triggeredAttributesObject:
      newAttributesObject['latitude'] = triggeredAttributesObject['latitude']
    if 'longitude' in triggeredAttributesObject:
      newAttributesObject['longitude'] = triggeredAttributesObject['longitude']
    if 'gps_accuracy' in triggeredAttributesObject:
      newAttributesObject['gps_accuracy'] = triggeredAttributesObject['gps_accuracy']
    else:
      if 'gps_accuracy' in newAttributesObject:
        newAttributesObject.pop('gps_accuracy')
    if 'altitude' in triggeredAttributesObject:
      newAttributesObject['altitude'] = round(triggeredAttributesObject['altitude'],0)
    if 'vertical_accuracy' in triggeredAttributesObject:
      newAttributesObject['vertical_accuracy'] = triggeredAttributesObject['vertical_accuracy']
    else:
      if 'vertical_accuracy' in newAttributesObject:
        newAttributesObject.pop('vertical_accuracy')

    newAttributesObject['source'] = triggeredEntity
    newAttributesObject['reported_state'] = triggeredStatus
    newAttributesObject['person_name'] = string.capwords(personName) 
    newAttributesObject['update_time'] = str(datetime.datetime.now())

    if triggeredStatus == 'Away' or triggeredStatus == 'Stationary' or triggeredStatus.lower() == 'on':
      friendly_name = "{0} ({1}) is {2}".format(string.capwords(personName),triggeredFriendlyName,triggeredStatus) 
      template = "{0} ({1}) is in <locality>".format(string.capwords(personName),triggeredFriendlyName)
    else:
      friendly_name = "{0} ({1}) is at {2}".format(string.capwords(personName),triggeredFriendlyName,triggeredStatus) 
      template = friendly_name
    newAttributesObject['friendly_name'] = friendly_name

    if 'zone' in triggeredAttributesObject:
      zoneEntityID = 'zone.' + triggeredAttributesObject['zone']
    else:
      zoneEntityID = 'zone.' + triggeredStatus.lower().replace(' ','_').replace("'",'_')
    zoneStateObject = hass.states.get(zoneEntityID)
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
    
    logger.debug("setting sensor name = {0}; oldStatus = {1}; newStatus = {2}".format(sensorName,oldStatus,newStatus))

    hass.states.set(sensorName, newStatus, newAttributesObject)
    logger.debug(newAttributesObject)

#--------------------------------------------------------------------------------------------------
# Call service to "reverse geocode" the location:
# - determine <locality> for friendly_name
# - record full location in OSM_location
# - calculate other location-based statistics, such as distance_from_home
# For devices at Home, this will only be done initially or on arrival (newStatus = 'Just Arrived')
#--------------------------------------------------------------------------------------------------
    if newStatus != 'Home' or ha_just_started == 'on':
      try:
        service_data = {"entity_id": sensorName, "friendly_name_template": template}
        hass.services.call("person_location", "reverse_geocode", service_data, True)
        logger.debug("person_location reverse_geocode service call completed")
      except Exception as e:
        logger.debug("person_location reverse_geocode service call exception: {0}".format(str(e)))
