"""Provide info to system health."""

# https://developers.home-assistant.io/blog/2020/11/09/system-health-and-templates

from homeassistant.components import system_health
from homeassistant.core import HomeAssistant, callback

from .const import (
    API_STATE_OBJECT,
    DATA_ATTRIBUTES,
    DATA_CONFIG_ENTRY,
    DATA_SENSOR_INFO,
    DATA_STATE,
    DOMAIN,
    VERSION,
)


@callback
def async_register(
    hass: HomeAssistant, register: system_health.SystemHealthRegistration
) -> None:
    """Register system health callbacks."""
    register.async_register_info(system_health_info)


async def system_health_info(hass):
    """Get info for the system health info (Configuration > Info)."""

    return_info = {}
    return_info["Version"] = VERSION

    if (
        DATA_STATE in hass.data[DOMAIN]
        and DATA_ATTRIBUTES in hass.data[DOMAIN]
        and DATA_SENSOR_INFO in hass.data[DOMAIN]
    ):
        apiState = hass.data[DOMAIN][DATA_STATE]
        apiAttributesObject = hass.data[DOMAIN][DATA_ATTRIBUTES]
        sensor_info = hass.data[DOMAIN][DATA_SENSOR_INFO]

        return_info["State"] = apiState

        attr_value = apiAttributesObject["api_calls_attempted"]
        if attr_value != 0:
            return_info["Geolocation Calls Attempted"] = attr_value

        attr_value = apiAttributesObject["api_calls_skipped"]
        if attr_value != 0:
            return_info["Geolocation Calls Skipped"] = attr_value

        attr_value = apiAttributesObject["api_calls_throttled"]
        if attr_value != 0:
            return_info["Geolocation Calls Throttled"] = attr_value

        attr_value = apiAttributesObject["api_error_count"]
        if attr_value != 0:
            return_info["Geolocation Error Count"] = attr_value

        attr_value = apiAttributesObject["waze_error_count"]
        if attr_value != 0:
            return_info["WAZE Error Count"] = attr_value

        if DATA_CONFIG_ENTRY in hass.data[DOMAIN]:
            return_info["Integration Configuration"] = hass.data[DOMAIN][
                DATA_CONFIG_ENTRY
            ].state
        else:
            return_info["Integration Configuration"] = "yaml only"

    return return_info
