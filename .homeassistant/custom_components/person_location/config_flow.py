"""Add config flow for Person Location."""

import logging
import re

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import PersonLocation_aiohttp_Client
from .const import (
    CONF_CREATE_SENSORS,
    CONF_GOOGLE_API_KEY,
    CONF_HOURS_EXTENDED_AWAY,
    CONF_LANGUAGE,
    CONF_MAPQUEST_API_KEY,
    CONF_MINUTES_JUST_ARRIVED,
    CONF_MINUTES_JUST_LEFT,
    CONF_OSM_API_KEY,
    CONF_OUTPUT_PLATFORM,
    CONF_REGION,
    DATA_CONFIGURATION,
    DEFAULT_API_KEY_NOT_SET,
    DEFAULT_HOURS_EXTENDED_AWAY,
    DEFAULT_LANGUAGE,
    DEFAULT_MINUTES_JUST_ARRIVED,
    DEFAULT_MINUTES_JUST_LEFT,
    DEFAULT_OUTPUT_PLATFORM,
    DEFAULT_REGION,
    DOMAIN,
    VALID_CREATE_SENSORS,
    VALID_OUTPUT_PLATFORM,
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

    # ------------------------------------------------------------------

    async def async_step_user(self, user_input=None):
        """Handle a flow initiated by the user."""

        self._load_previous_integration_config_data()

        # if self._async_current_entries():
        #     return self.async_abort(reason="already_configured")
        # TODO: Allow update of previous entry.

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
        user_input[CONF_GOOGLE_API_KEY] = self.integration_config_data.get(
            CONF_GOOGLE_API_KEY, DEFAULT_API_KEY_NOT_SET
        )
        user_input[CONF_LANGUAGE] = self.integration_config_data.get(
            CONF_LANGUAGE, DEFAULT_LANGUAGE
        )
        user_input[CONF_MAPQUEST_API_KEY] = self.integration_config_data.get(
            CONF_MAPQUEST_API_KEY, DEFAULT_API_KEY_NOT_SET
        )
        user_input[CONF_OSM_API_KEY] = self.integration_config_data.get(
            CONF_OSM_API_KEY, DEFAULT_API_KEY_NOT_SET
        )
        user_input[CONF_REGION] = self.integration_config_data.get(
            CONF_REGION, DEFAULT_REGION
        )

        return await self._show_config_geocode_form(user_input)

    def _load_previous_integration_config_data(self):

        try:
            self.integration_config_data
        except AttributeError:
            if DOMAIN in self.hass.data:
                self.integration_config_data = self.hass.data[DOMAIN][
                    DATA_CONFIGURATION
                ]
                _LOGGER.debug(
                    "_load_previous_integration_config_data config = %s",
                    self.integration_config_data,
                )
            else:
                self.integration_config_data = {}

    async def _show_config_geocode_form(
        self, user_input
    ):  # pylint: disable=unused-argument
        """Show the configuration form for reverse geocoding."""

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_LANGUAGE, default=user_input[CONF_LANGUAGE]): str,
                    vol.Optional(CONF_REGION, default=user_input[CONF_REGION]): str,
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

    # ------------------------------------------------------------------

    async def async_step_sensors(self, user_input=None):
        """Step to collect which sensors to create."""

        self._errors = {}

        if user_input is not None:
            _LOGGER.debug("user_input = %s", user_input)
            valid = True
            if user_input[CONF_CREATE_SENSORS] == "":
                create_sensors = []
            else:
                if type(user_input[CONF_CREATE_SENSORS] == str):
                    create_sensors = [
                        x.strip() for x in user_input[CONF_CREATE_SENSORS].split(",")
                    ]
                else:
                    create_sensors = user_input[CONF_CREATE_SENSORS]
                for sensor_name in create_sensors:
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
                self._user_input[CONF_CREATE_SENSORS] = create_sensors

                location_name = self.hass.config.location_name

                our_current_entry_configured = False
                our_currently_configured_entries = self._async_current_entries()
                if our_currently_configured_entries:
                    for our_current_entry in our_currently_configured_entries:
                        if our_current_entry.title == location_name:
                            our_current_entry_configured = True
                            break
                if our_current_entry_configured:
                    _LOGGER.debug("previous entry.data = %s", our_current_entry.data)
                    changed = self.hass.config_entries.async_update_entry(
                        our_current_entry, data=self._user_input
                    )
                    if changed:
                        # TODO: Figure out how to exit the flow gracefully:
                        return self.async_abort(reason="normal exit")
                    else:
                        self._errors["base"] = "nothing was changed"
                        return await self.async_step_user()
                else:
                    return self.async_create_entry(
                        title=location_name, data=self._user_input
                    )

            return await self._show_config_sensors_form(user_input)

        user_input = {}
        user_input[CONF_CREATE_SENSORS] = self.integration_config_data.get(
            CONF_CREATE_SENSORS, ""
        )
        user_input[CONF_OUTPUT_PLATFORM] = self.integration_config_data.get(
            CONF_OUTPUT_PLATFORM, DEFAULT_OUTPUT_PLATFORM
        )

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
                    vol.Optional(
                        CONF_OUTPUT_PLATFORM, default=user_input[CONF_OUTPUT_PLATFORM]
                    ): vol.In(VALID_OUTPUT_PLATFORM),
                }
            ),
            errors=self._errors,
        )

    # ------------------------------------------------------------------

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
            client = PersonLocation_aiohttp_Client(session)
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
            _LOGGER.debug(
                "google_api_key test exception %s: %s", type(e).__name__, str(e)
            )
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
            client = PersonLocation_aiohttp_Client(session)
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
            _LOGGER.debug(
                "mapquest_api_key test exception %s: %s", type(e).__name__, str(e)
            )
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
            _LOGGER.debug("osm_api_key test exception %s: %s", type(e).__name__, str(e))

        self._errors[CONF_OSM_API_KEY] = "invalid_email"
        return False

    # ------------------------------------------------------------------

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
        """Handle the option flow."""
        if user_input is not None:
            self.options.update(user_input)
            return await self._update_options()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_HOURS_EXTENDED_AWAY,
                        default=self.options.get(
                            CONF_HOURS_EXTENDED_AWAY, DEFAULT_HOURS_EXTENDED_AWAY
                        ),
                    ): int,
                    vol.Optional(
                        CONF_MINUTES_JUST_ARRIVED,
                        default=self.options.get(
                            CONF_MINUTES_JUST_ARRIVED, DEFAULT_MINUTES_JUST_ARRIVED
                        ),
                    ): int,
                    vol.Optional(
                        CONF_MINUTES_JUST_LEFT,
                        default=self.options.get(
                            CONF_MINUTES_JUST_LEFT, DEFAULT_MINUTES_JUST_LEFT
                        ),
                    ): int,
                    # TODO: allow the setup flow to be triggered?
                    #    vol.Optional("review_update_configuration", default=False): bool,
                }
            ),
        )

    async def _update_options(self):
        """Update config entry options."""

        _LOGGER.debug("===== _update_options options = %s", self.options)
        location_name = self.hass.config.location_name
        return self.async_create_entry(title=location_name, data=self.options)
