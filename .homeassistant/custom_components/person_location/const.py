"""Constants and Classes for person_location integration."""

import logging

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
from homeassistant.components.waze_travel_time.sensor import REGIONS as WAZE_REGIONS

# Our info
DOMAIN = "person_location"
INTEGRATION_NAME = "Person Location"
ISSUE_URL = "https://github.com/rodpayne/home-assistant/issues"
VERSION = "2021.02.20"

# Fixed Parameters
MIN_DISTANCE_TRAVELLED = 5
THROTTLE_INTERVAL = timedelta(
    seconds=1
)  # See https://operations.osmfoundation.org/policies/nominatim/ regarding throttling.
WAZE_MIN_METERS_FROM_HOME = 500

# Constants
API_STATE_OBJECT = DOMAIN + "." + DOMAIN + "_api"
METERS_PER_KM = 1000
METERS_PER_MILE = 1609.34

# Attribute names:
ATTR_BREAD_CRUMBS = "bread_crumbs"

# Configuration Parameters
CONF_LANGUAGE = "language"
DEFAULT_LANGUAGE = "en"

CONF_HOURS_EXTENDED_AWAY = "extended_away"
DEFAULT_HOURS_EXTENDED_AWAY = 48

CONF_MINUTES_JUST_ARRIVED = "just_arrived"
DEFAULT_MINUTES_JUST_ARRIVED = 3

CONF_MINUTES_JUST_LEFT = "just_left"
DEFAULT_MINUTES_JUST_LEFT = 3

CONF_OUTPUT_PLATFORM = "platform"
DEFAULT_OUTPUT_PLATFORM = "sensor"

CONF_REGION = "region"
DEFAULT_REGION = "US"

CONF_GOOGLE_API_KEY = "google_api_key"
CONF_MAPQUEST_API_KEY = "mapquest_api_key"
CONF_OSM_API_KEY = "osm_api_key"
DEFAULT_API_KEY_NOT_SET = "no key"

CONF_CREATE_SENSORS = "create_sensors"
VALID_CREATE_SENSORS = [
    "altitude",
    ATTR_BREAD_CRUMBS,
    "direction",
    "driving_miles",
    "driving_minutes",
    "geocoded",
    "latitude",
    "longitude",
    "meters_from_home",
    "miles_from_home",
]
CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(CONF_CREATE_SENSORS, default=[]): vol.All(
                    cv.ensure_list, [cv.string]
                ),
                vol.Optional(
                    CONF_HOURS_EXTENDED_AWAY, default=DEFAULT_HOURS_EXTENDED_AWAY
                ): cv.string,
                vol.Optional(
                    CONF_MINUTES_JUST_ARRIVED, default=DEFAULT_MINUTES_JUST_ARRIVED
                ): cv.string,
                vol.Optional(
                    CONF_MINUTES_JUST_LEFT, default=DEFAULT_MINUTES_JUST_LEFT
                ): cv.string,
                vol.Optional(CONF_LANGUAGE, default=DEFAULT_LANGUAGE): cv.string,
                vol.Optional(
                    CONF_OUTPUT_PLATFORM, default=DEFAULT_OUTPUT_PLATFORM
                ): cv.string,
                vol.Optional(CONF_REGION, default=DEFAULT_REGION): cv.string,
                vol.Optional(
                    CONF_MAPQUEST_API_KEY, default=DEFAULT_API_KEY_NOT_SET
                ): cv.string,
                vol.Optional(
                    CONF_OSM_API_KEY, default=DEFAULT_API_KEY_NOT_SET
                ): cv.string,
                vol.Optional(
                    CONF_GOOGLE_API_KEY, default=DEFAULT_API_KEY_NOT_SET
                ): cv.string,
            }
        ),
    },
    #    extra=vol.ALLOW_EXTRA,
)

_LOGGER = logging.getLogger(__name__)


class PERSON_LOCATION_INTEGRATION:
    """Class to represent the integration itself."""

    def __init__(self, entity_id, _hass, _config):
        """Initialize the integration instance."""

        # log startup message
        _LOGGER.info(
            CC_STARTUP_VERSION.format(
                name=DOMAIN, version=VERSION, issue_link=ISSUE_URL
            )
        )

        self.entity_id = entity_id
        self.hass = _hass
        self.config = _config
        self.state = "on"
        self.attributes = {}
        self.attributes["icon"] = "mdi:api"

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

        self.configured_google_api_key = self.config[DOMAIN].get(
            CONF_GOOGLE_API_KEY, DEFAULT_API_KEY_NOT_SET
        )
        self.configured_language = self.config[DOMAIN].get(
            CONF_LANGUAGE, DEFAULT_LANGUAGE
        )
        self.configured_minutes_extended_away = (
            self.config[DOMAIN].get(
                CONF_HOURS_EXTENDED_AWAY, DEFAULT_HOURS_EXTENDED_AWAY
            )
            * 60
        )
        self.configured_minutes_just_arrived = self.config[DOMAIN].get(
            CONF_MINUTES_JUST_ARRIVED, DEFAULT_MINUTES_JUST_ARRIVED
        )
        self.configured_minutes_just_left = self.config[DOMAIN].get(
            CONF_MINUTES_JUST_LEFT, DEFAULT_MINUTES_JUST_LEFT
        )
        self.configured_output_platform = self.config[DOMAIN].get(
            CONF_OUTPUT_PLATFORM, DEFAULT_OUTPUT_PLATFORM
        )
        self.configured_mapquest_api_key = self.config[DOMAIN].get(
            CONF_MAPQUEST_API_KEY, DEFAULT_API_KEY_NOT_SET
        )
        self.configured_osm_api_key = self.config[DOMAIN].get(
            CONF_OSM_API_KEY, DEFAULT_API_KEY_NOT_SET
        )
        # TODO: may need to split these up later (Google vs Waze):
        self.configured_google_region = self.config[DOMAIN].get(
            CONF_REGION, DEFAULT_REGION
        )
        self.configured_waze_region = self.config[DOMAIN].get(
            CONF_REGION, DEFAULT_REGION
        )
        if self.configured_waze_region in WAZE_REGIONS:
            self.use_waze = True
        else:
            self.use_waze = False
            _LOGGER.warning("Configured Waze region is not valid")
        self.create_sensors = [
            x.strip()
            for x in self.config[DOMAIN].get(CONF_CREATE_SENSORS, []).split(",")
        ]
        for sensor_name in self.create_sensors:
            if sensor_name not in VALID_CREATE_SENSORS:
                _LOGGER.error(
                    "Configured %s: %s is not valid",
                    CONF_CREATE_SENSORS,
                    sensor_name,
                )
        # TODO: self.create_sensors.pop(sensor_name)?

        self.hass.data[DOMAIN] = {
            "configured_create_sensors": self.create_sensors,
            "configured_output_platform": self.configured_output_platform,
            "sensor_info": {},
        }

    def set_state(self):
        _LOGGER.debug(
            "(%s.set_state) -state: %s -attributes: %s -data: %s",
            self.entity_id,
            self.state,
            self.attributes,
            self.hass.data[DOMAIN],
        )
        self.hass.states.set(self.entity_id, self.state, self.attributes)


class PERSON_LOCATION_ENTITY:
    """Class to represent device trackers and our person location sensors."""

    def __init__(self, entity_id, _hass):
        """Initialize the entity instance."""

        self.entity_id = entity_id
        self.hass = _hass

        targetStateObject = self.hass.states.get(self.entity_id)
        if targetStateObject != None:
            self.firstTime = False
            if (targetStateObject.state == "stationary") or (
                targetStateObject.state == "not_home"
            ):
                self.state = "Away"
            else:
                self.state = targetStateObject.state
            self.last_changed = targetStateObject.last_changed
            self.attributes = targetStateObject.attributes.copy()
        else:
            self.firstTime = True
            self.state = "Unknown"
            self.last_changed = datetime.now()
            self.attributes = {}

        if self.entity_id in self.hass.data[DOMAIN]["sensor_info"]:
            self.sensor_info = self.hass.data[DOMAIN]["sensor_info"][
                self.entity_id
            ].copy()
        else:
            self.sensor_info = {}

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
            self.personName = self.entity_id.split(".")[1].split("_")[0].lower()
            if self.firstTime == False:
                _LOGGER.debug(
                    'The account_name (or person_name) attribute is missing in %s, trying "%s"',
                    self.entity_id,
                    self.personName,
                )
        # It is tempting to make the output a device_tracker instead of a sensor,
        # so that it can be input into the Person built-in integration,
        # but if you do, be very careful not to trigger a loop.

        configured_output_platform = self.hass.data[DOMAIN][
            "configured_output_platform"
        ]
        self.targetName = (
            configured_output_platform + "." + self.personName.lower() + "_location"
        )

    def make_template_sensor(self, attributeName, supplementalAttributeArray):
        """Make an additional sensor that will be used instead of making a template sensor."""

        if type(attributeName) is str:
            if attributeName in self.attributes:
                templateSuffix = attributeName
                templateState = self.attributes[attributeName]
            else:
                return
        elif type(attributeName) is dict:
            templateSuffix = keys(attributeName)[0]
            templateState = attributeName[templateSuffix]

        templateAttributes = {}
        for supplementalAttribute in supplementalAttributeArray:
            if type(supplementalAttribute) is str:
                if supplementalAttribute in self.attributes:
                    templateAttributes[supplementalAttribute] = self.attributes[
                        supplementalAttribute
                    ]
            elif type(supplementalAttribute) is dict:
                for supplementalAttributeKey in supplementalAttribute:
                    templateAttributes[
                        supplementalAttributeKey
                    ] = supplementalAttribute[supplementalAttributeKey]
            else:
                _LOGGER.debug(
                    "supplementalAttribute %s %s",
                    supplementalAttribute,
                    type(supplementalAttribute),
                )

        self.hass.states.set(
            "sensor." + self.personName.lower() + "_location_" + templateSuffix.lower(),
            templateState,
            templateAttributes,
        )

    def set_state(self):
        """Save changed target sensor information as a unit."""

        _LOGGER.debug(
            "(%s.set_state) -state: %s -attributes: %s -sensor_info: %s",
            self.entity_id,
            self.state,
            self.attributes,
            self.sensor_info,
        )
        self.hass.states.set(self.entity_id, self.state, self.attributes)
        self.hass.data[DOMAIN]["sensor_info"][self.entity_id] = self.sensor_info

    def make_template_sensors(self):
        """Make the additional sensors if they are requested."""

        configured_create_sensors = self.hass.data[DOMAIN]["configured_create_sensors"]
        for attributeName in configured_create_sensors:
            if (
                attributeName == "altitude"
                and "altitude" in self.attributes
                and self.attributes["altitude"] != 0
                and "vertical_accuracy" in self.attributes
                and self.attributes["vertical_accuracy"] != 0
            ):
                self.make_template_sensor(
                    "altitude",
                    ["vertical_accuracy", "icon", {"unit_of_measurement": "m"}],
                )

            elif attributeName == ATTR_BREAD_CRUMBS:
                self.make_template_sensor(ATTR_BREAD_CRUMBS, ["icon"])

            elif attributeName == "direction":
                self.make_template_sensor("direction", ["icon"])

            elif attributeName == "driving_miles":
                self.make_template_sensor(
                    "driving_miles",
                    [
                        "driving_minutes",
                        "meters_from_home",
                        "miles_from_home",
                        {"unit_of_measurement": "mi"},
                        "icon",
                    ],
                )

            elif attributeName == "driving_minutes":
                self.make_template_sensor(
                    "driving_minutes",
                    [
                        "driving_miles",
                        "meters_from_home",
                        "miles_from_home",
                        {"unit_of_measurement": "min"},
                        "icon",
                    ],
                )

            elif attributeName == "geocoded":
                pass

            elif attributeName == "latitude":
                self.make_template_sensor("latitude", ["gps_accuracy", "icon"])

            elif attributeName == "longitude":
                self.make_template_sensor("longitude", ["gps_accuracy", "icon"])

            elif attributeName == "meters_from_home":
                self.make_template_sensor(
                    "meters_from_home",
                    [
                        "miles_from_home",
                        "driving_miles",
                        "driving_minutes",
                        "icon",
                        {"unit_of_measurement": "m"},
                    ],
                )

            elif attributeName == "miles_from_home":
                self.make_template_sensor(
                    "miles_from_home",
                    [
                        "meters_from_home",
                        "driving_miles",
                        "driving_minutes",
                        {"unit_of_measurement": "mi"},
                        "icon",
                    ],
                )

            else:
                self.make_template_sensor(attributeName, ["icon"])
