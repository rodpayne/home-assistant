"""API Client Wrapper."""

import asyncio
import logging
import socket
import traceback

import aiohttp
import async_timeout

TIMEOUT = 10

_LOGGER: logging.Logger = logging.getLogger(__package__)

HEADERS = {"Content-type": "application/json; charset=UTF-8"}


class PersonLocation_aiohttp_Client:
    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    async def async_get_data(
        self, method: str, url: str, data: dict = {}, headers: dict = {}
    ) -> dict:
        """Get data from the API."""

        return await self.api_wrapper(method, url, data, headers)

    async def api_wrapper(
        self, method: str, url: str, data: dict = {}, headers: dict = {}
    ) -> dict:
        """Get information from the API."""
        try:
            async with async_timeout.timeout(TIMEOUT, loop=asyncio.get_event_loop()):
                if method == "get":
                    response = await self._session.get(url, headers=headers)
                    return await response.json()

                elif method == "put":
                    response = await self._session.put(url, headers=headers, json=data)
                    return await response.json()

                elif method == "patch":
                    response = await self._session.patch(
                        url, headers=headers, json=data
                    )
                    return await response.json()

                elif method == "post":
                    response = await self._session.post(url, headers=headers, json=data)
                    return await response.json()
        except asyncio.TimeoutError as exception:
            error_message = f"Timeout error fetching information from {url.split('?',1)[0]} - {exception}"
            _LOGGER.error(error_message)
            return {"error": error_message}

        except (KeyError, TypeError) as exception:
            error_message = (
                f"Error parsing information from {url.split('?',1)[0]} - {exception}"
            )
            _LOGGER.error(error_message)
            return {"error": error_message}

        except (aiohttp.ClientError, socket.gaierror) as exception:
            error_message = (
                f"Error fetching information from {url.split('?',1)[0]} - {exception}"
            )
            _LOGGER.error(error_message)
            return {"error": error_message}

        except Exception as e:  # pylint: disable=broad-except
            error_message = f"Something wrong happened! - {type(e).__name__}: {e}"
            _LOGGER.error(error_message)
            _LOGGER.debug(traceback.format_exc())
            return {"error": error_message}
