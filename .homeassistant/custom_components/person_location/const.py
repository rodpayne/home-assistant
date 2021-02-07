""" Constants """
import logging
import threading
import voluptuous as vol
from datetime import timedelta
import homeassistant.helpers.config_validation as cv
from integrationhelper.const import CC_STARTUP_VERSION

from homeassistant.const import (
    ATTR_ATTRIBUTION,
    ATTR_FRIENDLY_NAME,
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
)

# Our info
DOMAIN = "person_location"
INTEGRATION_NAME = "Person Location"
ISSUE_URL = "https://github.com/rodpayne/home-assistant/issues"
VERSION = "2021.02.06"

# Constants
API_STATE_OBJECT = DOMAIN + "." + DOMAIN + "_api"
METERS_PER_KM = 1000
METERS_PER_MILE = 1609.34
THROTTLE_INTERVAL = timedelta(
    seconds=1
)  # See https://operations.osmfoundation.org/policies/nominatim/ regarding throttling.

# Configuration
CONF_LANGUAGE = "language"
DEFAULT_LANGUAGE = "en"

CONF_REGION = "region"
DEFAULT_REGION = "US"

CONF_OSM_API_KEY = "osm_api_key"
CONF_GOOGLE_API_KEY = "google_api_key"
CONF_API_KEY_NOT_SET = "no key"

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(CONF_LANGUAGE, default=DEFAULT_LANGUAGE): cv.string,
                vol.Optional(CONF_REGION, default=DEFAULT_REGION): cv.string,
                vol.Optional(CONF_OSM_API_KEY, default=CONF_API_KEY_NOT_SET): cv.string,
                vol.Optional(
                    CONF_GOOGLE_API_KEY, default=CONF_API_KEY_NOT_SET
                ): cv.string,
            }
        ),
    },
    extra=vol.ALLOW_EXTRA,
)

from datetime import (
    datetime,
    timedelta,
)

_LOGGER = logging.getLogger(__name__)


class PERSON_LOCATION_INTEGRATION:
    def __init__(self, name, _hass, _config):
        """ Initialize the integration instance """
        # log startup message
        _LOGGER.info(
            CC_STARTUP_VERSION.format(
                name=DOMAIN, version=VERSION, issue_link=ISSUE_URL
            )
        )

        self.name = name
        self.hass = _hass
        self.config = _config
        self.state = "on"
        self.attributes = {}
        home_zone = "zone.home"
        self.attributes[ATTR_FRIENDLY_NAME] = f"{INTEGRATION_NAME} Service"
        self.attributes["home_latitude"] = str(
            self.hass.states.get(home_zone).attributes.get(ATTR_LATITUDE)
        )
        self.attributes["home_longitude"] = str(
            self.hass.states.get(home_zone).attributes.get(ATTR_LONGITUDE)
        )
        self.attributes["last_api_time"] = datetime.now()
        self.attributes["api_error_count"] = 0
        self.attributes["attempted_api_calls"] = 0
        self.attributes["skipped_api_calls"] = 0
        self.attributes["throttled_api_calls"] = 0
        self.attributes["waze_error_count"] = 0
        self.attributes[
            ATTR_ATTRIBUTION
        ] = f"System information for the {INTEGRATION_NAME} integration ({DOMAIN}), version {VERSION}."

        self.configured_osm_api_key = self.config[DOMAIN].get(
            CONF_OSM_API_KEY, CONF_API_KEY_NOT_SET
        )
        self.configured_google_api_key = self.config[DOMAIN].get(
            CONF_GOOGLE_API_KEY, CONF_API_KEY_NOT_SET
        )
        self.configured_language = self.config[DOMAIN].get(
            CONF_LANGUAGE, DEFAULT_LANGUAGE
        )
        self.configured_region = self.config[DOMAIN].get(CONF_REGION, DEFAULT_REGION)

    def set_state(self):
        _LOGGER.debug(
            "(%s.set_state()) - %s - %s", self.name, self.state, self.attributes
        )
        self.hass.states.set(self.name, self.state, self.attributes.copy())


class PERSON_LOCATION_ENTITY:
    def __init__(self, name, _hass):
        """ Initialize the entity instance """

        self.name = name
        self.hass = _hass
        self.lock = threading.Lock()

        targetStateObject = self.hass.states.get(self.name)
        if targetStateObject != None:
            self.state = targetStateObject.state
            self.attributes = targetStateObject.attributes.copy()
        else:
            self.state = "Unknown"
            self.attrubutes = {}

    def set_state(self):
        _LOGGER.debug(
            "(%s.set_state()) - %s - %s", self.name, self.state, self.attributes
        )
        self.hass.states.set(self.name, self.state, self.attributes.copy())
