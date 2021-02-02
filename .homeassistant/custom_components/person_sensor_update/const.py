""" Constants """
import voluptuous as vol
from datetime import timedelta
import homeassistant.helpers.config_validation as cv

DOMAIN ='person_sensor_update'
INTEGRATION_NAME = 'Person Sensor Update'
ISSUE_URL = 'https://github.com/rodpayne/home-assistant/issues'
VERSION = '2021.02.01'

# Constants
API_STATE_OBJECT = DOMAIN + '.' + DOMAIN + '_api'
METERS_PER_KM = 1000
METERS_PER_MILE = 1609.34
THROTTLE_INTERVAL = timedelta(seconds=1.5) # See https://operations.osmfoundation.org/policies/nominatim/ regarding throttling.


# Configuration
CONF_LANGUAGE = 'language'
DEFAULT_LANGUAGE = 'en'

CONF_REGION = 'region'
DEFAULT_REGION = 'US'

CONF_OSM_API_KEY = 'osm_api_key'
CONF_GOOGLE_API_KEY = 'google_api_key'
CONF_API_KEY_NOT_SET = 'no key'

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(CONF_LANGUAGE, default=DEFAULT_LANGUAGE): cv.string,
                vol.Optional(CONF_REGION, default=DEFAULT_REGION): cv.string,
                vol.Optional(CONF_OSM_API_KEY, default=CONF_API_KEY_NOT_SET): cv.string,
                vol.Optional(CONF_GOOGLE_API_KEY, default=CONF_API_KEY_NOT_SET): cv.string,
            }
        ),
    },
    extra=vol.ALLOW_EXTRA,
)
