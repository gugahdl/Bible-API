from __future__ import annotations

import logging
from datetime import timedelta

import aiohttp
import async_timeout

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    CoordinatorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from .const import DOMAIN, CONF_TOKEN, CONF_VERSION

_LOGGER = logging.getLogger(__name__)

API_URL = "https://developers.youversionapi.com/1.0/verse_of_the_day.json"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    """Set up the YouVersion sensor from a config entry."""

    token = entry.data[CONF_TOKEN]
    version = entry.data.get(CONF_VERSION, "nvi")

    coordinator = YouVersionCoordinator(hass, token, version)

    await coordinator.async_config_entry_first_refresh()

    async_add_entities([YouVersionSensor(coordinator)], True)


class YouVersionCoordinator(DataUpdateCoordinator):
    """Manages fetching data from the YouVersion API."""

    def __init__(self, hass, token, version):
        super().__init__(
            hass,
            _LOGGER,
            name="YouVersion Bible API",
            update_interval=timedelta(hours=1),
        )
        self.token = token
        self.version = version

    async def _async_update_data(self):
        """Fetch data from YouVersion."""
        headers = {
            "X-YouVersion-Developer-Token": self.token,
            "Accept-Language": "en",
        }

        params = {"version_id": self.version}

        try:
            async with async_timeout.timeout(10):
                async with aiohttp.ClientSession() as session:
                    async with session.get(API_URL, headers=headers, params=params) as resp:
                        if resp.status != 200:
                            raise Exception(f"API returned status {resp.status}")

                        data = await resp.json()
                        return data

        except Exception as err:
            _LOGGER.error("Error fetching YouVersion data: %s", err)
            raise


class YouVersionSensor(CoordinatorEntity, SensorEntity):
    """Representation of the Verse of the Day sensor."""

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_name = "YouVersion Verse of the Day"
        self._attr_unique_id = "youversion_votd"

    @property
    def native_value(self):
        """Return the verse text."""
        return self.coordinator.data.get("verse", {}).get("text")

    @property
    def extra_state_attributes(self):
        """Return additional attributes."""
        verse = self.coordinator.data.get("verse", {})
        return {
            "reference": verse.get("human_reference"),
            "version": verse.get("version_id"),
        }
