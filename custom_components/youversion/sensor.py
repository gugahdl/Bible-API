"""Sensor platform for the YouVersion Bible API integration."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import async_timeout
from aiohttp import ClientError

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    API_BASE_URL,
    API_USER_AGENT,
    CONF_LANGUAGE,
    CONF_TOKEN,
    CONF_VERSION,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_VERSION_ID,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the YouVersion sensor from a config entry."""
    token = entry.data[CONF_TOKEN]
    version_id = int(entry.options.get(CONF_VERSION, DEFAULT_VERSION_ID))
    language = entry.options.get(CONF_LANGUAGE, hass.config.language or "en")

    coordinator = YouVersionCoordinator(hass, token, version_id, language)
    await coordinator.async_config_entry_first_refresh()

    async_add_entities([YouVersionSensor(coordinator, entry, version_id)])


class YouVersionCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Manages fetching data from the YouVersion API."""

    def __init__(
        self,
        hass: HomeAssistant,
        token: str,
        version_id: int,
        language: str,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="YouVersion Bible API",
            update_interval=DEFAULT_UPDATE_INTERVAL,
        )
        self._token = token
        self._version_id = version_id
        self._language = language
        self._session = aiohttp_client.async_get_clientsession(hass)

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch the verse of the day from YouVersion."""
        day = datetime.utcnow().timetuple().tm_yday
        url = f"{API_BASE_URL}/verse_of_the_day/{day}"

        headers = {
            "X-YouVersion-Developer-Token": self._token,
            "Accept": "application/json",
            "Accept-Language": self._language,
            "User-Agent": API_USER_AGENT,
        }
        params = {"version_id": str(self._version_id)}

        try:
            async with async_timeout.timeout(15):
                async with self._session.get(
                    url, headers=headers, params=params
                ) as resp:
                    if resp.status in (401, 403):
                        raise UpdateFailed(
                            f"Authentication failed (HTTP {resp.status})"
                        )
                    if resp.status >= 400:
                        raise UpdateFailed(
                            f"YouVersion API returned HTTP {resp.status}"
                        )
                    return await resp.json()
        except ClientError as err:
            raise UpdateFailed(f"Error communicating with YouVersion: {err}") from err
        except TimeoutError as err:
            raise UpdateFailed("Timeout communicating with YouVersion") from err


class YouVersionSensor(
    CoordinatorEntity[YouVersionCoordinator], SensorEntity
):
    """Representation of the Verse of the Day sensor."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:book-open-variant"

    def __init__(
        self,
        coordinator: YouVersionCoordinator,
        entry: ConfigEntry,
        version_id: int,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._version_id = version_id
        self._attr_name = "Verse of the Day"
        self._attr_unique_id = f"{entry.entry_id}_votd"

    @property
    def native_value(self) -> str | None:
        """Return the verse reference as the state.

        The state is limited to 255 characters in Home Assistant, and verses
        can exceed that, so we expose the short reference as the state and
        the full text as an attribute.
        """
        verse = (self.coordinator.data or {}).get("verse") or {}
        return verse.get("human_reference")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        data = self.coordinator.data or {}
        verse = data.get("verse") or {}
        image = data.get("image") or {}
        return {
            "text": verse.get("text"),
            "html": verse.get("html"),
            "reference": verse.get("human_reference"),
            "usfms": verse.get("usfms"),
            "url": verse.get("url"),
            "image_url": image.get("url"),
            "image_attribution": image.get("attribution"),
            "day": data.get("day"),
            "version_id": self._version_id,
        }
