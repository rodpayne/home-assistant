
DOMAIN = "person_sensor_update"

CONF_API_KEY = 'api_key'
CONF_API_KEY_NOT_SET = 'no key'

ATTR_ENTITY_ID = "entity_id"
ATTR_TEMPLATE = "template"

API_STATE_OBJECT = DOMAIN + "." + DOMAIN + "_api"


import logging, json, requests
from datetime import datetime, timedelta
from requests import get
from homeassistant.util.location import distance
import traceback

"""See https://operations.osmfoundation.org/policies/nominatim/."""
THROTTLE_INTERVAL = timedelta(seconds=1)

_LOGGER = logging.getLogger(__name__)

METERS_PER_MILE = 3030.064

def setup(hass, config):
    """Set up is called when Home Assistant is loading our component."""
    API_KEY = config[DOMAIN].get(CONF_API_KEY,CONF_API_KEY_NOT_SET)
    
    def handle_reverse_geocode(call):
        entity_id = call.data.get(ATTR_ENTITY_ID, "NONE")
        template = call.data.get(ATTR_TEMPLATE, "NONE")
                                
        _LOGGER.debug("(" + entity_id + ") Start " + DOMAIN + ".reverse_geocode")

        """Get component attributes from the API_STATE_OBJECT."""
        apiStateObject = hass.states.get(API_STATE_OBJECT)
        if apiStateObject != None:
            apiStatus = apiStateObject.state.lower()
            currentApiTime = datetime.now()
            apiAttributesObject = apiStateObject.attributes.copy()
            try:
                if 'skipped_api_calls' in apiAttributesObject:
                    skippedApiCalls = apiAttributesObject['skipped_api_calls']
                else:
                    skippedApiCalls = 0
                if 'last_api_time' in apiAttributesObject:
                    lastApiTime = apiAttributesObject['last_api_time']
                else:
                    lastApiTime = currentApiTime - THROTTLE_INTERVAL
                if 'attempted_api_calls' in apiAttributesObject:
                    attemptedApiCalls = apiAttributesObject['attempted_api_calls']
                else:
                    attemptedApiCalls = 0
                home_latitude = apiAttributesObject['home_latitude']
                home_longitude = apiAttributesObject['home_longitude']
                
                """Throttle (or possibly pause) the API calls so that we don't exceed policy."""
                if (apiStatus != "on") or (currentApiTime < (lastApiTime + THROTTLE_INTERVAL)):
                    skippedApiCalls += 1
                    apiAttributesObject['skipped_api_calls'] = skippedApiCalls
                    hass.states.set(API_STATE_OBJECT, apiStatus, apiAttributesObject)
                    _LOGGER.debug("(" + entity_id + ") skipped_api_calls = " + str(skippedApiCalls))
                else:
                    apiAttributesObject['last_api_time'] = currentApiTime
            
                    """Record the component attributes in the API_STATE_OBJECT."""
                    apiAttributesObject['last_entity_id'] = entity_id
                    _LOGGER.debug("(" + entity_id + ") entity_id = " + entity_id)
                        
                    apiAttributesObject['last_template'] = template
                    _LOGGER.debug("(" + entity_id + ") template = " + template)

                    apiAttributesObject['attempted_api_calls'] = attemptedApiCalls + 1

                    _LOGGER.debug("(" + entity_id + ") Setting " + API_STATE_OBJECT)
                    hass.states.set(API_STATE_OBJECT, apiStatus, apiAttributesObject)
                            
                    """Handle the service call, updating the targetStateObject."""
                    targetStateObject = hass.states.get(entity_id)
                    if targetStateObject != None:
                        targetStatus = targetStateObject.state
                        targetAttributesObject = targetStateObject.attributes.copy()

                        if 'latitude' in targetAttributesObject:
                            new_latitude = targetAttributesObject['latitude']
                        else:
                            new_latitude = 'None'
                        if 'longitude' in targetAttributesObject:
                            new_longitude = targetAttributesObject['longitude']
                        else:
                            new_longitude = 'None'
                        
                        if 'previous_latitude' in targetAttributesObject:
                            old_latitude = targetAttributesObject['previous_latitude']
                        else:
                            old_latitude = 'None'
                        if 'previous_longitude' in targetAttributesObject:
                            old_longitude = targetAttributesObject['previous_longitude']
                        else:
                            old_longitude = 'None'
                            
                        if (new_latitude != 'None' and new_longitude != 'None' and old_latitude != 'None' and old_longitude != 'None'):
                            distance_traveled = round(distance(float(new_latitude), float(new_longitude), float(old_latitude), float(old_longitude)),3)
                            _LOGGER.debug("(" + entity_id + ") distance_traveled = " + str(distance_traveled))
                        else:
                            distance_traveled = 0
                        
                        if new_latitude == 'None' or new_longitude == 'None':
                            _LOGGER.info("(" + entity_id + ") Skipping geocoding because coordinates are missing")
                        elif distance_traveled < 10 and old_latitude != 'None' and old_longitude != 'None':
                            _LOGGER.info("(" + entity_id + ") Skipping geocoding because distance < 10")
                        else:

                            if 'update_time' in targetAttributesObject:
                                new_update_time = datetime.strptime(targetAttributesObject['update_time'],'%Y-%m-%d %H:%M:%S.%f')
                                _LOGGER.debug("(" + entity_id + ") new_update_time = " + str(new_update_time))
                            else:
                                new_update_time = currentApiTime
                            
                            if 'previous_update_time' in targetAttributesObject:
                                old_update_time = datetime.strptime(targetAttributesObject['previous_update_time'],'%Y-%m-%d %H:%M:%S.%f')
                                _LOGGER.debug("(" + entity_id + ") old_update_time = " + str(old_update_time))
                            else:
                                old_update_time = new_update_time
    
                            elapsed_time = new_update_time - old_update_time
                            _LOGGER.debug("(" + entity_id + ") elapsed_time = " + str(elapsed_time))
                            
                            old_distance_from_home = 0
                            if 'distance_from_home' in targetAttributesObject:
                                old_distance_from_home = float(targetAttributesObject['distance_from_home'])
                            
                            if 'reported_state' in targetAttributesObject and targetAttributesObject['reported_state'].lower() == 'home':
                                distance_from_home = 0          # clamp it down since "Home" is not a single point
                            elif (new_latitude != 'None' and new_longitude != 'None' and home_latitude != 'None' and home_longitude != 'None'):
                                distance_from_home = round(distance(float(new_latitude), float(new_longitude), float(home_latitude), float(home_longitude)),3)
                            else:
                                distance_from_home = 0          # could only happen if we don't have coordinates
                            _LOGGER.debug("(" + entity_id + ") distance_from_home = " + str(distance_from_home))
                            targetAttributesObject['distance_from_home'] = str(round(distance_from_home,1))
                            targetAttributesObject['miles_from_home'] = str(round(distance_from_home / METERS_PER_MILE,1))

                            if distance_traveled <= 20:
                                direction = "stationary"
                            elif old_distance_from_home > distance_from_home:
                                direction = "toward home"
                            elif old_distance_from_home < distance_from_home:
                                direction = "away from home"
                            else:
                                direction = "stationary"
                            _LOGGER.debug("(" + entity_id + ") direction = " + direction)
                            targetAttributesObject['direction'] = direction

                            """Call the Open Street Map (Nominatim) API"""
                            if API_KEY == CONF_API_KEY_NOT_SET:
                                osm_url = "https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=" + str(new_latitude) + "&lon=" + str(new_longitude) + "&addressdetails=1&namedetails=1&zoom=18&limit=1"
                            else:
                                osm_url = "https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=" + str(new_latitude) + "&lon=" + str(new_longitude) + "&addressdetails=1&namedetails=1&zoom=18&limit=1&email=" + API_KEY

                            osm_decoded = {}
                            _LOGGER.debug( "(" + entity_id + ") url - " + osm_url)
                            osm_response = get(osm_url)
                            osm_json_input = osm_response.text
                            _LOGGER.debug( "(" + entity_id + ") response - " + osm_json_input)
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
                            else:
                                locality = "?"
                            _LOGGER.info("(" + entity_id + ") locality = " + locality)
                            
                            if "display_name" in osm_decoded:
                                display_name = osm_decoded["display_name"]
                            else: 
                                display_name = locality
                            _LOGGER.info("(" + entity_id + ") display_name = " + display_name)

                            targetAttributesObject['previous_latitude'] = new_latitude
                            targetAttributesObject['previous_longitude'] = new_longitude
                            targetAttributesObject['previous_update_time'] = str(new_update_time)

                            targetAttributesObject['friendly_name'] = template.replace("<locality>",locality)
                            targetAttributesObject['OSM_location'] = display_name

                            if "licence" in osm_decoded:
                                targetAttributesObject['attribution'] = osm_decoded["licence"] 


        #                    """Try the WazeRouteCalculator"""
        #                    if distance_from_home == 0:
        #                        routeTime = 0
        #                        routeDistance = 0
        #                    else:
        #                        import WazeRouteCalculator
        #                        from_address = "lat=" + str(new_latitude) + " lng=" + str(new_longitude)
        #                        to_address = "lat=" + str(home_latitude) + " lng=" + str(home_longitude)
        #                        region = "US"
        #                        route = WazeRouteCalculator.WazeRouteCalculator(from_address, to_address, region)
        #                        routeTime, routeDistance = route.calc_route_info()
        #                    _LOGGER.debug("(" + entity_id + ") Waze routeTime " + str(routeTime) )
        #                    targetAttributesObject['driving_time'] = str(round(routeTime,2))
        #                    _LOGGER.debug("(" + entity_id + ") Waze routeDistance " + str(routeDistance) )
        #                    targetAttributesObject['driving_distance'] = str(round(routeDistance,2))


                        _LOGGER.debug("(" + entity_id + ") Setting " + entity_id)
                        hass.states.set(entity_id,targetStatus,targetAttributesObject)
            except Exception as e:
                _LOGGER.error("(" + entity_id + ") Exception - " + str(e))
                _LOGGER.debug(traceback.format_exc())
                if 'api_error_count' in apiAttributesObject:
                    apiErrorCount = apiAttributesObject['api_error_count']
                else:
                    apiErrorCount = 0
                apiAttributesObject['api_error_count'] = apiErrorCount + 1
                hass.states.set(API_STATE_OBJECT, apiStatus, apiAttributesObject)
        _LOGGER.debug("(" + entity_id + ") Finish " + DOMAIN + ".reverse_geocode")

    def handle_geocode_api_on(call):
        _LOGGER.debug("Start " + DOMAIN + ".geocode_api_on")
        apiStateObject = hass.states.get(API_STATE_OBJECT)
        if apiStateObject != None:
            apiAttributesObject = apiStateObject.attributes.copy()
            _LOGGER.info("Setting " + API_STATE_OBJECT + " on")
            hass.states.set(API_STATE_OBJECT, "on", apiAttributesObject)
        _LOGGER.debug("Finish " + DOMAIN + ".geocode_api_on")

    def handle_geocode_api_off(call):
        _LOGGER.debug("Start " + DOMAIN + ".geocode_api_off")
        apiStateObject = hass.states.get(API_STATE_OBJECT)
        if apiStateObject != None:
            apiAttributesObject = apiStateObject.attributes.copy()
            _LOGGER.info("Setting " + API_STATE_OBJECT + " off")
            hass.states.set(API_STATE_OBJECT, "off", apiAttributesObject)
        _LOGGER.debug("Finish " + DOMAIN + ".geocode_api_off")

    hass.services.register(DOMAIN, "reverse_geocode", handle_reverse_geocode)
    hass.services.register(DOMAIN, "geocode_api_on", handle_geocode_api_on)
    hass.services.register(DOMAIN, "geocode_api_off", handle_geocode_api_off)

    home_latitude = 'None'
    home_longitude = 'None'
    home_zone = 'zone.home'
    home_latitude = str(hass.states.get(home_zone).attributes.get('latitude'))
    home_longitude = str(hass.states.get(home_zone).attributes.get('longitude'))
        
#    homeStateObject = hass.states.get(home_zone)
#    if homeStateObject != None:
#        homeAttributesObject = homeStateObject.attributes.copy()
#        if 'latitude' in homeAttributesObject:
#            home_latitude = homeAttributesObject['latitude']
#        if 'longitude' in homeAttributesObject:
#            home_longitude = homeAttributesObject['longitude']

    apiAttributesObject = {}
    apiAttributesObject['friendly_name'] = "Person Sensor Update API"
    apiAttributesObject['home_latitude'] = home_latitude
    apiAttributesObject['home_longitude'] = home_longitude
    hass.states.set(API_STATE_OBJECT, "on", apiAttributesObject)

    # Return boolean to indicate that initialization was successfully.
    return True