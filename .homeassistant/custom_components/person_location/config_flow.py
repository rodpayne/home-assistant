"""Adds config flow for Person Location."""

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession
import json
import logging
import re
import voluptuous as vol
from requests import get

from .api import PersonLocationApiClient
from .const import (
    CONF_GOOGLE_API_KEY,
    CONF_MAPQUEST_API_KEY,
    CONF_OSM_API_KEY,
    CONF_CREATE_SENSORS,
    DEFAULT_API_KEY_NOT_SET,
    DOMAIN,
    VALID_CREATE_SENSORS,
)

# Platforms
BINARY_SENSOR = "binary_sensor"
SENSOR = "sensor"
SWITCH = "switch"
PLATFORMS = [BINARY_SENSOR, SENSOR, SWITCH]

_LOGGER = logging.getLogger(__name__)


class PersonLocationFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Person Location."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    def __init__(self):
        """Initialize."""
        self._errors = {}
        self._user_input = {}

    async def async_step_user(self, user_input=None):
        """Handle a flow initiated by the user."""

        self._errors = {}

        if self._async_current_entries():
            return self.async_abort(reason="already_configured")

        if user_input is not None:
            valid1 = await self._test_google_api_key(user_input[CONF_GOOGLE_API_KEY])
            valid2 = await self._test_mapquest_api_key(
                user_input[CONF_MAPQUEST_API_KEY]
            )
            valid3 = await self._test_osm_api_key(user_input[CONF_OSM_API_KEY])
            if valid1 and valid2 and valid3:
                self._user_input.update(user_input)
                return await self.async_step_sensors()

            return await self._show_config_geocode_form(user_input)

        user_input = {}
        user_input[CONF_GOOGLE_API_KEY] = DEFAULT_API_KEY_NOT_SET
        user_input[CONF_MAPQUEST_API_KEY] = DEFAULT_API_KEY_NOT_SET
        user_input[CONF_OSM_API_KEY] = DEFAULT_API_KEY_NOT_SET

        return await self._show_config_geocode_form(user_input)

    async def _show_config_geocode_form(
        self, user_input
    ):  # pylint: disable=unused-argument
        """Show the configuration form for reverse geocoding."""
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_GOOGLE_API_KEY, default=user_input[CONF_GOOGLE_API_KEY]
                    ): str,
                    vol.Optional(
                        CONF_MAPQUEST_API_KEY,
                        default=user_input[CONF_MAPQUEST_API_KEY],
                    ): str,
                    vol.Optional(
                        CONF_OSM_API_KEY, default=user_input[CONF_OSM_API_KEY]
                    ): str,
                }
            ),
            errors=self._errors,
        )

    async def async_step_sensors(self, user_input=None):
        """Step to collect which sensors to create."""

        self._errors = {}

        if self._async_current_entries():
            return self.async_abort(reason="already_configured")

        if user_input is not None:
            _LOGGER.debug("user_input = %s", user_input)
            valid = True
            if user_input[CONF_CREATE_SENSORS] == "":
                self.create_sensors = []
            else:
                self.create_sensors = [
                    x.strip() for x in user_input[CONF_CREATE_SENSORS].split(",")
                ]
                for sensor_name in self.create_sensors:
                    if sensor_name not in VALID_CREATE_SENSORS:
                        _LOGGER.debug(
                            "Configured %s: %s is not valid",
                            CONF_CREATE_SENSORS,
                            sensor_name,
                        )
                        self._errors[CONF_CREATE_SENSORS] = "sensor_invalid"
                        valid = False
            if valid:
                self._user_input.update(user_input)
                location_name = self.hass.config.location_name
                return self.async_create_entry(
                    title=location_name, data=self._user_input
                )

            return await self._show_config_sensors_form(user_input)

        user_input = {}
        user_input[CONF_CREATE_SENSORS] = ""

        return await self._show_config_sensors_form(user_input)

    async def _show_config_sensors_form(
        self, user_input
    ):  # pylint: disable=unused-argument
        """Show the configuration form for sensors."""
        return self.async_show_form(
            step_id="sensors",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_CREATE_SENSORS, default=user_input[CONF_CREATE_SENSORS]
                    ): str,
                }
            ),
            errors=self._errors,
        )

    async def _test_google_api_key(self, google_api_key):
        """Return true if api_key is valid."""
        try:
            if google_api_key == DEFAULT_API_KEY_NOT_SET:
                return True
            latitude = self.hass.config.latitude
            longitude = self.hass.config.longitude
            google_url = (
                "https://maps.googleapis.com/maps/api/geocode/json?language="
                + "en"
                + "&region="
                + "us"
                + "&latlng="
                + str(latitude)
                + ","
                + str(longitude)
                + "&key="
                + google_api_key
            )
            session = async_create_clientsession(self.hass)
            client = PersonLocationApiClient(session)
            google_decoded = await client.async_get_data("get", google_url)
            if "error" in google_decoded:
                _LOGGER.debug("google_api_key test error = %s", google_decoded["error"])
            else:
                if "status" in google_decoded:
                    google_status = google_decoded["status"]
                    _LOGGER.debug("google_api_key test status = %s", google_status)
                    if google_status == "OK":
                        return True
        except Exception as e:  # pylint: disable=broad-except
            _LOGGER.debug("google_api_key test exception = %s", str(e))
        self._errors[CONF_GOOGLE_API_KEY] = "invalid_key"
        return False

    async def _test_mapquest_api_key(self, mapquest_api_key):
        """Return true if api_key is valid."""
        try:
            if mapquest_api_key == DEFAULT_API_KEY_NOT_SET:
                return True
            latitude = self.hass.config.latitude
            longitude = self.hass.config.longitude
            mapquest_url = (
                "https://www.mapquestapi.com/geocoding/v1/reverse"
                + "?location="
                + str(latitude)
                + ","
                + str(longitude)
                + "&thumbMaps=false"
                + "&key="
                + mapquest_api_key
            )

            session = async_create_clientsession(self.hass)
            client = PersonLocationApiClient(session)
            mapquest_decoded = await client.async_get_data("get", mapquest_url)
            if "error" in mapquest_decoded:
                _LOGGER.debug(
                    "mapquest_api_key test error = %s", mapquest_decoded["error"]
                )
            else:
                mapquest_statuscode = mapquest_decoded["info"]["statuscode"]
                _LOGGER.debug(
                    "mapquest_api_key test statuscode = %s", str(mapquest_statuscode)
                )
                if mapquest_statuscode == 0:
                    return True
        except Exception as e:  # pylint: disable=broad-except
            _LOGGER.debug("mapquest_api_key test exception = %s", str(e))
        self._errors[CONF_MAPQUEST_API_KEY] = "invalid_key"
        return False

    async def _test_osm_api_key(self, osm_api_key):
        """Return true if api_key is valid."""
        try:
            if osm_api_key == DEFAULT_API_KEY_NOT_SET:
                return True
            regex = "^[a-z0-9]+[\._]?[a-z0-9]+[@]\w+[.]\w{2,3}$"
            valid = re.search(regex, osm_api_key)
            _LOGGER.debug("osm_api_key test valid = %s", valid)
            if valid:
                return True
        except Exception as e:  # pylint: disable=broad-except
            _LOGGER.debug("osm_api_key test exception = %s", str(e))
        self._errors[CONF_OSM_API_KEY] = "invalid_email"
        return False

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return PersonLocationOptionsFlowHandler(config_entry)


class PersonLocationOptionsFlowHandler(config_entries.OptionsFlow):
    """Person Location config flow options handler."""

    def __init__(self, config_entry):
        """Initialize HACS options flow."""
        self.config_entry = config_entry
        self.options = dict(config_entry.options)

    async def async_step_init(self, user_input=None):  # pylint: disable=unused-argument
        """Manage the options."""
        return await self.async_step_user()

    async def async_step_user(self, user_input=None):
        """Handle a flow initiated by the user."""
        if user_input is not None:
            self.options.update(user_input)
            return await self._update_options()

        return self.async_show_form(
            step_id="geocode",
            data_schema=vol.Schema(
                {
                    vol.Required(x, default=self.options.get(x, True)): bool
                    for x in sorted(PLATFORMS)
                }
            ),
        )

    async def _update_options(self):
        """Update config entry options."""
        return self.async_create_entry(
            title=self.config_entry.data.get(CONF_GOOGLE_API_KEY), data=self.options
        )
