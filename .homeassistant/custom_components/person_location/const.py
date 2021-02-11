""" Constants """
import logging
import threading
from datetime import datetime, timedelta

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.const import (
    ATTR_ATTRIBUTION,
    ATTR_FRIENDLY_NAME,
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
)
from integrationhelper.const import CC_STARTUP_VERSION

# Our info
DOMAIN = "person_location"
INTEGRATION_NAME = "Person Location"
ISSUE_URL = "https://github.com/rodpayne/home-assistant/issues"
VERSION = "2021.02.10"

# Fixed Parameters
MIN_DISTANCE_TRAVELLED = 5
THROTTLE_INTERVAL = timedelta(
    seconds=1
)  # See https://operations.osmfoundation.org/policies/nominatim/ regarding throttling.

# Constants
API_STATE_OBJECT = DOMAIN + "." + DOMAIN + "_api"
METERS_PER_KM = 1000
METERS_PER_MILE = 1609.34

# Configuration Parameters
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
        self.attributes["api_last_updated"] = datetime.now()
        self.attributes["api_error_count"] = 0
        self.attributes["api_calls_attempted"] = 0
        self.attributes["api_calls_skipped"] = 0
        self.attributes["api_calls_throttled"] = 0
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
            "(%s.set_state) - %s - %s", self.name, self.state, self.attributes
        )
        self.hass.states.set(self.name, self.state, self.attributes.copy())


class PERSON_LOCATION_ENTITY:
    def __init__(self, name, _hass):
        """ Initialize the entity instance """

        self.name = name
        self.hass = _hass

        targetStateObject = self.hass.states.get(self.name)
        if targetStateObject != None:
            self.firstTime = False
            self.state = targetStateObject.state
            self.attributes = targetStateObject.attributes.copy()
        else:
            self.firstTime = True
            self.state = "Unknown"
            self.attributes = {}

        if "friendly_name" in self.attributes:
            self.friendlyName = self.attributes["friendly_name"]
        else:
            self.friendlyName = ""
            _LOGGER.debug("friendly_name attribute is missing")

        if self.state.lower() == "home" or self.state.lower() == "on":
            self.stateHomeAway = "Home"
            self.state = "Home"
        else:
            self.stateHomeAway = "Away"
            if self.state == "not_home":
                self.state = "Away"

        if "person_name" in self.attributes:
            self.personName = self.attributes["person_name"]
        elif "account_name" in self.attributes:
            self.personName = self.attributes["account_name"]
        elif "owner_fullname" in self.attributes:
            self.personName = self.attributes["owner_fullname"].split()[0].lower()
        else:
            self.personName = self.name.split(".")[1].split("_")[0].lower()
            if self.firstTime == False:
                _LOGGER.warning(
                    'The account_name (or person_name) attribute is missing in %s, trying "%s"',
                    self.name,
                    self.personName,
                )

        self.targetName = "sensor." + self.personName.lower() + "_location"

    def set_state(self):
        _LOGGER.debug(
            "(%s.set_state) - %s - %s", self.name, self.state, self.attributes
        )
        self.hass.states.set(self.name, self.state, self.attributes.copy())
