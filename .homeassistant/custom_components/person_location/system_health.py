"""Provide info to system health."""

# https://developers.home-assistant.io/blog/2020/11/09/system-health-and-templates

from homeassistant.components import system_health
from homeassistant.core import HomeAssistant, callback

from .const import API_STATE_OBJECT, DOMAIN, VERSION


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

        attr_value = apiAttributesObject["attempted_api_calls"]
        if attr_value != 0:
            return_info["Attempted API Calls"] = attr_value

        attr_value = apiAttributesObject["skipped_api_calls"]
        if attr_value != 0:
            return_info["Skipped API Calls"] = attr_value

        attr_value = apiAttributesObject["throttled_api_calls"]
        if attr_value != 0:
            return_info["Throttled API Calls"] = attr_value

        attr_value = apiAttributesObject["api_error_count"]
        if attr_value != 0:
            return_info["API Error Count"] = attr_value

        attr_value = apiAttributesObject["waze_error_count"]
        if attr_value != 0:
            return_info["WAZE Error Count"] = attr_value

    return return_info
