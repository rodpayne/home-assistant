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
import requests
import threading
import time
import traceback
import voluptuous as vol
import homeassistant.helpers.config_validation as cv
from requests import get

from homeassistant.const import (
    ATTR_ATTRIBUTION, 
    ATTR_FRIENDLY_NAME,
    ATTR_GPS_ACCURACY,
    ATTR_LATITUDE, 
    ATTR_LONGITUDE,
    CONF_ENTITY_ID, 
    CONF_FRIENDLY_NAME_TEMPLATE, 
)
from homeassistant.components.device_tracker.const import (
    ATTR_SOURCE_TYPE,
    SOURCE_TYPE_GPS,
)
from integrationhelper.const import CC_STARTUP_VERSION
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
    THROTTLE_INTERVAL,
    VERSION,
)

from datetime import datetime, timedelta
from homeassistant.util.location import distance

_LOGGER = logging.getLogger(__name__)

class PERSON_LOCATION_INTEGRATION:
    def __init__(self, name, _hass, _config):
        """ Initialize the integration instance """
        # log startup message
        _LOGGER.info(CC_STARTUP_VERSION.format(name=DOMAIN, version=VERSION, issue_link=ISSUE_URL))
        
        self.name = name
        self.hass = _hass
        self.config = _config
        self.state = 'on'
        self.attributes = {}
        home_zone = 'zone.home'
        self.attributes[ATTR_FRIENDLY_NAME] = f"{INTEGRATION_NAME} Service"
        self.attributes['home_latitude'] = str(self.hass.states.get(home_zone).attributes.get(ATTR_LATITUDE))
        self.attributes['home_longitude'] = str(self.hass.states.get(home_zone).attributes.get(ATTR_LONGITUDE))
        self.attributes['last_api_time'] = datetime.now()      
        self.attributes['api_error_count'] = 0
        self.attributes['attempted_api_calls'] = 0
        self.attributes['skipped_api_calls'] = 0
        self.attributes['waze_error_count'] = 0
        self.attributes[ATTR_ATTRIBUTION] = f"System information for the {INTEGRATION_NAME} integration ({DOMAIN}), version {VERSION}."
        
        self.configured_osm_api_key = self.config[DOMAIN].get(CONF_OSM_API_KEY,CONF_API_KEY_NOT_SET)
        self.configured_google_api_key = self.config[DOMAIN].get(CONF_GOOGLE_API_KEY,CONF_API_KEY_NOT_SET)
        self.configured_language = self.config[DOMAIN].get(CONF_LANGUAGE,DEFAULT_LANGUAGE)
        self.configured_region = self.config[DOMAIN].get(CONF_REGION,DEFAULT_REGION)
    
    def set_state(self):
        _LOGGER.debug("(%s.set_state()) - %s - %s", self.name, self.state, self.attributes)
    #    _LOGGER.debug(self.attributes)
        self.hass.states.set(self.name, self.state, self.attributes.copy())


def setup(hass, config):
    """Setup is called when Home Assistant is loading our component."""

    pli = PERSON_LOCATION_INTEGRATION(API_STATE_OBJECT,hass,config)
    integration_lock = threading.Lock()

    def handle_reverse_geocode(call):
        """ Handle the reverse_geocode service. """

        entity_id = call.data.get(CONF_ENTITY_ID, 'NONE')
        template = call.data.get(CONF_FRIENDLY_NAME_TEMPLATE, 'NONE')
                                
        _LOGGER.debug('(' + entity_id + ') Start ' + DOMAIN + '.reverse_geocode')
        _LOGGER.debug('(' + entity_id + ') ' + CONF_FRIENDLY_NAME_TEMPLATE + ' = ' + template)

        with integration_lock:
            """Lock while updating the pli(API_STATE_OBJECT)."""
            try:
                currentApiTime = datetime.now()
                
                if (pli.state.lower() != 'on'):
                    pli.attributes['skipped_api_calls'] += 1
                    _LOGGER.debug("(" + entity_id + ") skipped_api_calls = " + str(pli.attributes['skipped_api_calls']))
                else:
                    """Throttle (or possibly pause) the API calls so that we don't exceed policy."""
                    wait_time = (pli.attributes['last_api_time'] - currentApiTime + THROTTLE_INTERVAL).total_seconds()
                    if (wait_time > 0):
                        _LOGGER.debug("(" + entity_id + ") wait_time = " + str(wait_time))
                        time.sleep(wait_time)
                        currentApiTime = datetime.now()
                
                    """Record the component attributes in the API_STATE_OBJECT."""
            
                    pli.attributes['last_api_time'] = currentApiTime
            
                    pli.attributes['attempted_api_calls'] += 1

                    counter_attribute = f"{entity_id} calls"
                    if counter_attribute in pli.attributes:
                        new_count = pli.attributes[counter_attribute] + 1
                    else:
                        new_count = 1
                    pli.attributes[counter_attribute] = new_count
                    _LOGGER.debug("(" + entity_id + ") " + counter_attribute + " = " + str(new_count))

                    """Handle the service call, updating the targetStateObject."""
                    targetStateObject = hass.states.get(entity_id)
                    if targetStateObject != None:
                        targetStatus = targetStateObject.state
                        targetAttributesObject = targetStateObject.attributes.copy()

                        attribution = ''
                        if ATTR_LATITUDE in targetAttributesObject:
                            new_latitude = targetAttributesObject[ATTR_LATITUDE]
                        else:
                            new_latitude = 'None'
                        if ATTR_LONGITUDE in targetAttributesObject:
                            new_longitude = targetAttributesObject[ATTR_LONGITUDE]
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
                            elif (new_latitude != 'None' and new_longitude != 'None' and pli.attributes['home_latitude'] != 'None' and pli.attributes['home_longitude'] != 'None'):
                                distance_from_home = round(distance(float(new_latitude), float(new_longitude), float(pli.attributes['home_latitude']), float(pli.attributes['home_longitude'])),3)
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

                            if pli.configured_osm_api_key != CONF_API_KEY_NOT_SET:
                                """Call the Open Street Map (Nominatim) API if osm_api_key is configured"""
                                if pli.configured_osm_api_key == CONF_API_KEY_NOT_SET:
                                    osm_url = 'https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=' + str(new_latitude) + "&lon=" + str(new_longitude) + "&addressdetails=1&namedetails=1&zoom=18&limit=1"
                                else:
                                    osm_url = 'https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=' + str(new_latitude) + "&lon=" + str(new_longitude) + "&addressdetails=1&namedetails=1&zoom=18&limit=1&email=" + pli.configured_osm_api_key

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
                                targetAttributesObject['Open_Street_Map'] = display_name.replace(', ',' ')

                                if 'licence' in osm_decoded:
                                    attribution += '"' + osm_decoded['licence'] + '"; '

                            if pli.configured_google_api_key != CONF_API_KEY_NOT_SET:
                                """Call the Google Maps Reverse Geocoding API if google_api_key is configured"""
                                """https://developers.google.com/maps/documentation/geocoding/overview?hl=en_US#ReverseGeocoding"""
                                google_url = 'https://maps.googleapis.com/maps/api/geocode/json?language=' + pli.configured_language + '&region=' + pli.configured_region + '&latlng=' + str(new_latitude) + ',' + str(new_longitude) + "&key=" + pli.configured_google_api_key
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
                                        if 'formatted_address' in google_decoded['results'][0]:
                                            formatted_address = google_decoded['results'][0]['formatted_address']
                                            _LOGGER.debug( "(" + entity_id + ") formatted_address = " + formatted_address)
                                            targetAttributesObject['Google_Maps'] = formatted_address
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

                            """WazeRouteCalculator is checked if not at Home."""
                            if distance_from_home <= 0:
                                routeTime = 0
                                routeDistance = 0
                                targetAttributesObject['driving_miles'] = '0'
                                targetAttributesObject['driving_minutes'] = '0'
                            else:
                                try:
                                    _LOGGER.debug('(' + entity_id + ') Waze calculation' )
                                    import WazeRouteCalculator
                                    from_address = str(new_latitude) + ',' + str(new_longitude)
                                    to_address = str(pli.attributes['home_latitude']) + ',' + str(pli.attributes['home_longitude'])
                                    route = WazeRouteCalculator.WazeRouteCalculator(from_address, to_address, pli.configured_region, avoid_toll_roads=True)
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
                                    pli.attributes['waze_error_count'] += 1
                                    targetAttributesObject.pop('driving_miles')
                                    targetAttributesObject.pop('driving_minutes')

                        targetAttributesObject[ATTR_ATTRIBUTION] = attribution

                        _LOGGER.debug("(" + entity_id + ") Setting " + entity_id)
                        hass.states.set(entity_id,targetStatus,targetAttributesObject)
            except Exception as e:
                _LOGGER.error("(" + entity_id + ") Exception - " + str(e))
                _LOGGER.debug(traceback.format_exc())
                pli.attributes['api_error_count'] += 1
            pli.set_state()
            _LOGGER.debug("(" + entity_id + ") Finish " + DOMAIN + ".reverse_geocode")

    def handle_geocode_api_on(call):
        """ Handle the geocode_api_on service. """

        _LOGGER.debug("Start " + DOMAIN + ".geocode_api_on")
        with integration_lock:
            """Lock while updating the pli(API_STATE_OBJECT)."""
            _LOGGER.debug("Setting " + API_STATE_OBJECT + " on")
            pli.state = 'on'
            pli.set_state()
        _LOGGER.debug("Finish " + DOMAIN + ".geocode_api_on")

    def handle_geocode_api_off(call):
        """ Handle the geocode_api_off service. """

        _LOGGER.debug("Start " + DOMAIN + ".geocode_api_off")
        with integration_lock:
            """Lock while updating the pli(API_STATE_OBJECT)."""
            _LOGGER.debug("Setting " + API_STATE_OBJECT + " off")
            pli.state = 'off'
            pli.set_state()
        _LOGGER.debug("Finish " + DOMAIN + ".geocode_api_off")

    hass.services.register(DOMAIN, 'reverse_geocode', handle_reverse_geocode)
    hass.services.register(DOMAIN, 'geocode_api_on', handle_geocode_api_on)
    hass.services.register(DOMAIN, 'geocode_api_off', handle_geocode_api_off)

#    hass.states.set(pli.name, pli.state, pli.attributes)
    pli.set_state()

    # Return boolean to indicate that setup was successful.
    return True