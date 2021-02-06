"""service_calls.py"""
import json
import logging
import requests
import time
import traceback
import voluptuous as vol
import homeassistant.helpers.config_validation as cv
from requests import get

from homeassistant.const import (
    ATTR_ATTRIBUTION, 
    ATTR_LATITUDE, 
    ATTR_LONGITUDE,
    CONF_ENTITY_ID, 
    CONF_FRIENDLY_NAME_TEMPLATE, 
)
from integrationhelper.const import CC_STARTUP_VERSION
from .const import (
    API_STATE_OBJECT,
    CONFIG_SCHEMA,
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
    THROTTLE_INTERVAL,
    VERSION,
)

from datetime import datetime, timedelta
from homeassistant.util.location import distance

_LOGGER = logging.getLogger(__name__)

from homeassistant.core import HomeAssistant


def setup_import(hass, config):
    _LOGGER.debug("Start " + DOMAIN + ".service_calls.setup_import")
    hass.states.set('sensor.person_location_setup_import','on')

    def setup_test():
        _LOGGER.debug("Start " + DOMAIN + ".service_calls.setup_test")
        hass.states.set('sensor.person_location_setup_test','on')


def handle_reverse_geocode(call):
    """ Handle the reverse_geocode service. """
    entity_id = call.data.get(CONF_ENTITY_ID, 'NONE')
    template = call.data.get(CONF_FRIENDLY_NAME_TEMPLATE, 'NONE')
                            
    _LOGGER.debug('(' + entity_id + ') Start ' + DOMAIN + '.reverse_geocode')
    _LOGGER.debug('(' + entity_id + ') ' + CONF_FRIENDLY_NAME_TEMPLATE + ' = ' + template)

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
                
            if (apiStatus != 'on'):
                skippedApiCalls += 1
                apiAttributesObject['skipped_api_calls'] = skippedApiCalls
                hass.states.set(API_STATE_OBJECT, apiStatus, apiAttributesObject)
                _LOGGER.debug("(" + entity_id + ") skipped_api_calls = " + str(skippedApiCalls))
            else:
                """Throttle (or possibly pause) the API calls so that we don't exceed policy."""
                wait_time = (lastApiTime - currentApiTime + THROTTLE_INTERVAL).total_seconds()
                if (wait_time > 0):
                    _LOGGER.debug("(" + entity_id + ") wait_time = " + str(wait_time))
                    time.sleep(wait_time)
                    currentApiTime = datetime.now()
                
                """Record the component attributes in the API_STATE_OBJECT."""
            
                apiAttributesObject['last_api_time'] = currentApiTime
            
                apiAttributesObject['attempted_api_calls'] = attemptedApiCalls + 1

                counter_attribute = f"{entity_id} calls"
                if counter_attribute in apiAttributesObject:
                    new_count = apiAttributesObject[counter_attribute] + 1
                else:
                    new_count = 1
                apiAttributesObject[counter_attribute] = new_count
                _LOGGER.debug("(" + entity_id + ") " + counter_attribute + " = " + str(new_count))

                _LOGGER.debug("(" + entity_id + ") Setting " + API_STATE_OBJECT)
                hass.states.set(API_STATE_OBJECT, apiStatus, apiAttributesObject)
                            
                """Handle the service call, updating the targetStateObject."""
                targetStateObject = hass.states.get(entity_id)
                if targetStateObject != None:
                    targetStatus = targetStateObject.state
                    targetAttributesObject = targetStateObject.attributes.copy()

                    attribution = ''
                    if 'latitude' in targetAttributesObject:
                        new_latitude = targetAttributesObject['latitude']
                    else:
                        new_latitude = 'None'
                    if 'longitude' in targetAttributesObject:
                        new_longitude = targetAttributesObject['longitude']
                    else:
                        new_longitude = 'None'
                       
                    if 'location_latitude' in targetAttributesObject:
                        old_latitude = targetAttributesObject['location_latitude']
                    else:
                        old_latitude = 'None'
                    if 'location_longitude' in targetAttributesObject:
                        old_longitude = targetAttributesObject['location_longitude']
                    else:
                        old_longitude = 'None'
                           
                    if (new_latitude != 'None' and new_longitude != 'None' and old_latitude != 'None' and old_longitude != 'None'):
                        distance_traveled = round(distance(float(new_latitude), float(new_longitude), float(old_latitude), float(old_longitude)),3)
                        _LOGGER.debug("(" + entity_id + ") distance_traveled = " + str(distance_traveled))
                    else:
                        distance_traveled = 0
                        
                    if new_latitude == 'None' or new_longitude == 'None':
                        _LOGGER.debug("(" + entity_id + ") Skipping geocoding because coordinates are missing")
                    elif distance_traveled < 10 and old_latitude != 'None' and old_longitude != 'None':
                        _LOGGER.debug("(" + entity_id + ") Skipping geocoding because distance_traveled < 10")
                    else:

                        if 'update_time' in targetAttributesObject:
                            new_update_time = datetime.strptime(targetAttributesObject['update_time'],'%Y-%m-%d %H:%M:%S.%f')
                            _LOGGER.debug("(" + entity_id + ") new_update_time = " + str(new_update_time))
                        else:
                            new_update_time = currentApiTime
                            
                        if 'location_update_time' in targetAttributesObject:
                            old_update_time = datetime.strptime(targetAttributesObject['location_update_time'],'%Y-%m-%d %H:%M:%S.%f')
                            _LOGGER.debug("(" + entity_id + ") old_update_time = " + str(old_update_time))
                        else:
                            old_update_time = new_update_time
    
                        elapsed_time = new_update_time - old_update_time
                        _LOGGER.debug("(" + entity_id + ") elapsed_time = " + str(elapsed_time))
                        elapsed_seconds = elapsed_time.total_seconds()
                        _LOGGER.debug("(" + entity_id + ") elapsed_seconds = " + str(elapsed_seconds))
                            
                        if elapsed_seconds > 0:
                            speed_during_interval = distance_traveled / elapsed_seconds
                            _LOGGER.debug("(" + entity_id + ") speed_during_interval = " + str(speed_during_interval) + " meters/sec")
                        else:
                            speed_during_interval = 0
                            
                        old_distance_from_home = 0
                        if 'meters_from_home' in targetAttributesObject:
                            old_distance_from_home = float(targetAttributesObject['meters_from_home'])
                            
                        if 'reported_state' in targetAttributesObject and targetAttributesObject['reported_state'].lower() == 'home':
                            distance_from_home = 0          # clamp it down since "Home" is not a single point
                        elif (new_latitude != 'None' and new_longitude != 'None' and home_latitude != 'None' and home_longitude != 'None'):
                            distance_from_home = round(distance(float(new_latitude), float(new_longitude), float(home_latitude), float(home_longitude)),3)
                        else:
                            distance_from_home = 0          # could only happen if we don't have coordinates
                        _LOGGER.debug("(" + entity_id + ") meters_from_home = " + str(distance_from_home))
                        targetAttributesObject['meters_from_home'] = str(round(distance_from_home,1))
                        targetAttributesObject['miles_from_home'] = str(round(distance_from_home / METERS_PER_MILE,1))

                        if speed_during_interval <= 0.5:
                            direction = 'stationary'
                        elif old_distance_from_home > distance_from_home:
                            direction = 'toward home'
                        elif old_distance_from_home < distance_from_home:
                            direction = 'away from home'
                        else:
                            direction = 'stationary'
                        _LOGGER.debug("(" + entity_id + ") direction = " + direction)
                        targetAttributesObject['direction'] = direction

                        if configured_osm_api_key != CONF_API_KEY_NOT_SET:
                            """Call the Open Street Map (Nominatim) API if osm_api_key is configured"""
                            if configured_osm_api_key == CONF_API_KEY_NOT_SET:
                                osm_url = 'https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=' + str(new_latitude) + "&lon=" + str(new_longitude) + "&addressdetails=1&namedetails=1&zoom=18&limit=1"
                            else:
                                osm_url = 'https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=' + str(new_latitude) + "&lon=" + str(new_longitude) + "&addressdetails=1&namedetails=1&zoom=18&limit=1&email=" + configured_osm_api_key

                            osm_decoded = {}
                            osm_response = get(osm_url)
                            osm_json_input = osm_response.text
                            osm_decoded = json.loads(osm_json_input)
                            decoded = osm_decoded
                            
                            if 'city' in osm_decoded['address']:
                                locality = osm_decoded['address']['city']
                            elif 'town' in osm_decoded['address']:
                                locality = osm_decoded['address']['town']
                            elif 'villiage' in osm_decoded['address']:
                                locality = osm_decoded['address']['village']
                            elif 'municipality' in osm_decoded['address']:
                                locality = osm_decoded['address']['municipality']
                            elif 'county' in osm_decoded['address']:
                                locality = osm_decoded['address']['county']
                            elif 'state' in osm_decoded['address']:
                                locality = osm_decoded['address']['state']
                            elif 'country' in osm_decoded['address']:
                                locality = osm_decoded['address']['country']
                            else:
                                locality = '?'
                            _LOGGER.debug("(" + entity_id + ") locality = " + locality)
                            
                            if 'display_name' in osm_decoded:
                                display_name = osm_decoded['display_name']
                            else: 
                                display_name = locality
                            _LOGGER.debug("(" + entity_id + ") display_name = " + display_name)

                            targetAttributesObject['friendly_name'] = template.replace('<locality>',locality)
                            targetAttributesObject['OSM_location'] = display_name.replace(', ',' ')

                            if 'licence' in osm_decoded:
                                attribution += '"' + osm_decoded['licence'] + '"; '

                        if configured_google_api_key != CONF_API_KEY_NOT_SET:
                            """Call the Google Maps Reverse Geocoding API if google_api_key is configured"""
                            """https://developers.google.com/maps/documentation/geocoding/overview?hl=en_US#ReverseGeocoding"""
                            if configured_google_api_key == CONF_API_KEY_NOT_SET:
                                google_url = 'https://maps.google.com/maps/api/geocode/json?language=en&region=US&latlng=' + str(new_latitude) + ',' + str(new_longitude)
                            else:
                                google_url = 'https://maps.googleapis.com/maps/api/geocode/json?language=en&region=US&latlng=' + str(new_latitude) + ',' + str(new_longitude) + "&key=" + configured_google_api_key
                            google_decoded = {}
                #            _LOGGER.debug( "(" + entity_id + ") url - " + google_url)
                            google_response = get(google_url)
                            google_json_input = google_response.text
                #            _LOGGER.debug( "(" + entity_id + ") response - " + google_json_input)
                            google_decoded = json.loads(google_json_input)
                                
                            google_status = google_decoded['status']
                            if google_status != 'OK':
                                _LOGGER.debug( '(' + entity_id + ') google_status = ' + google_status)
                            else:
                                if 'results' in google_decoded:
                                    for result in google_decoded['results']:
                                        location_type = 'none'
                                        if 'geometry' in result:
                                            if 'location_type' in result['geometry']:
                                                location_type = result['geometry']['location_type']
                                        if 'formatted_address' in result:
                                            formatted_address = result['formatted_address']
                                        else:
                                            formatted_address = 'none'
                                        _LOGGER.debug( '(' + entity_id + ') location_type = ' + location_type + '; formatted_address = ' + formatted_address)
                                    if 'formatted_address' in google_decoded['results'][0]:
                                        formatted_address = google_decoded['results'][0]['formatted_address']
                                        _LOGGER.debug( "(" + entity_id + ") formatted_address = " + formatted_address)
                                        targetAttributesObject['google_location'] = formatted_address
                                    for component in google_decoded['results'][0]['address_components']:
                                        _LOGGER.debug( '(' + entity_id + ') address_components ' + str(component['types']) + " = " + component["long_name"])
                                        if 'locality' in component['types']:
                                            locality = component['long_name']
                                            _LOGGER.debug('(' + entity_id + ') locality = ' + locality)
                                            targetAttributesObject['friendly_name'] = template.replace('<locality>',locality)
                                    attribution += '"powered by Google"; '

                        targetAttributesObject['location_latitude'] = new_latitude
                        targetAttributesObject['location_longitude'] = new_longitude
                        targetAttributesObject['location_update_time'] = str(new_update_time)

                        """WazeRouteCalculator"""
                        if distance_from_home == 0:
                            routeTime = 0
                            routeDistance = 0
                            targetAttributesObject['driving_miles'] = '0'
                            targetAttributesObject['driving_minutes'] = '0'
                        else:
                            _LOGGER.debug('(' + entity_id + ') Waze calculation' )
                            import WazeRouteCalculator
                            from_address = str(new_latitude) + ',' + str(new_longitude)
                            to_address = str(home_latitude) + ',' + str(home_longitude)
                            region = 'US'
                            try:
                                route = WazeRouteCalculator.WazeRouteCalculator(from_address, to_address, region, avoid_toll_roads=True)
                                routeTime, routeDistance = route.calc_route_info()
                                _LOGGER.debug("(" + entity_id + ") Waze routeDistance " + str(routeDistance) )  # km
                                routeDistance = routeDistance * METERS_PER_KM / METERS_PER_MILE                          # miles
                                if routeDistance >= 100:
                                    targetAttributesObject['driving_miles'] = str(round(routeDistance,0))
                                elif routeDistance >= 10:
                                    targetAttributesObject['driving_miles'] = str(round(routeDistance,1))
                                else:
                                    targetAttributesObject['driving_miles'] = str(round(routeDistance,2))
                                _LOGGER.debug("(" + entity_id + ") Waze routeTime " + str(routeTime) )          # minutes
                                targetAttributesObject['driving_minutes'] = str(round(routeTime,1))
                                attribution += '"Data by Waze App. https://waze.com"; ' 
                            except Exception as e:
                                _LOGGER.error("(" + entity_id + ") Waze Exception - " + str(e))
                                _LOGGER.debug(traceback.format_exc())
                                wazeErrorCount = apiAttributesObject['waze_error_count'] + 1
                                apiAttributesObject['waze_error_count'] = wazeErrorCount
                                hass.states.set(API_STATE_OBJECT, apiStatus, apiAttributesObject)
                                targetAttributesObject.pop('driving_miles')
                                targetAttributesObject.pop('driving_minutes')

                    targetAttributesObject['attribution'] = attribution

                    _LOGGER.debug("(" + entity_id + ") Setting " + entity_id)
                    hass.states.set(entity_id,targetStatus,targetAttributesObject)
        except Exception as e:
            _LOGGER.error("(" + entity_id + ") Exception - " + str(e))
            _LOGGER.debug(traceback.format_exc())
            apiErrorCount = apiAttributesObject['api_error_count'] + 1
            apiAttributesObject['api_error_count'] = apiErrorCount
            hass.states.set(API_STATE_OBJECT, apiStatus, apiAttributesObject)
    _LOGGER.debug("(" + entity_id + ") Finish " + DOMAIN + ".reverse_geocode")

def handle_geocode_api_on(call):
    """ Handle the geocode_api_on service. """
    _LOGGER.debug("Start " + DOMAIN + ".geocode_api_on")
    apiStateObject = hass.states.get(API_STATE_OBJECT)
    if apiStateObject != None:
        apiAttributesObject = apiStateObject.attributes.copy()
        _LOGGER.debug("Setting " + API_STATE_OBJECT + " on")
        hass.states.set(API_STATE_OBJECT, 'on', apiAttributesObject)
    _LOGGER.debug("Finish " + DOMAIN + ".geocode_api_on")

def handle_geocode_api_off(call):
    """ Handle the geocode_api_off service. """
    _LOGGER.debug("Start " + DOMAIN + ".geocode_api_off")
    apiStateObject = hass.states.get(API_STATE_OBJECT)
    if apiStateObject != None:
        apiAttributesObject = apiStateObject.attributes.copy()
        _LOGGER.debug("Setting " + API_STATE_OBJECT + " off")
        hass.states.set(API_STATE_OBJECT, 'off', apiAttributesObject)
    _LOGGER.debug("Finish " + DOMAIN + ".geocode_api_off")