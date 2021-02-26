"""Provide info to system health."""

# https://developers.home-assistant.io/blog/2020/11/09/system-health-and-templates

from homeassistant.components import system_health
from homeassistant.core import HomeAssistant, callback

from .const import API_STATE_OBJECT, VERSION


@callback
def async_register(
    hass: HomeAssistant, register: system_health.SystemHealthRegistration
) -> None:
    """Register system health callbacks."""
    register.async_register_info(system_health_info)


async def system_health_info(hass):
    """Get info for the info page."""
    return_info = {}
    return_info["Version"] = VERSION

    apiStateObject = hass.states.get(API_STATE_OBJECT)
    if apiStateObject != None:
        apiState = apiStateObject.state
        apiAttributesObject = apiStateObject.attributes.copy()

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

    return return_info
