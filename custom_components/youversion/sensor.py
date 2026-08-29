"""Sensor platform for the YouVersion Bible API integration."""
from __future__ import annotations

import asyncio
import html as html_lib
import json
import logging
import re
from typing import Any

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
from homeassistant.util import dt as dt_util

from .const import (
    API_BASE_URL,
    API_KEY_HEADER,
    API_USER_AGENT,
    CONF_APP_KEY,
    CONF_VERSION,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_VERSION_ID,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

_TAG_RE = re.compile(r"<[^>]+>")
_REQUEST_TIMEOUT = 15


def _strip_html(raw_html: str | None) -> str:
    """Return a plain-text rendering of an HTML fragment."""
    if not raw_html:
        return ""
    return html_lib.unescape(_TAG_RE.sub("", raw_html)).strip()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the YouVersion sensor from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    app_key = entry.data[CONF_APP_KEY]
    version_id = int(entry.options.get(CONF_VERSION, DEFAULT_VERSION_ID))

    coordinator = YouVersionCoordinator(hass, app_key, version_id)
    await coordinator.async_config_entry_first_refresh()

    async_add_entities([YouVersionSensor(coordinator, entry, version_id)])


class YouVersionCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetches the verse of the day from the YouVersion Platform API."""

    def __init__(
        self,
        hass: HomeAssistant,
        app_key: str,
        version_id: int,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="YouVersion Bible API",
            update_interval=DEFAULT_UPDATE_INTERVAL,
        )
        self._app_key = app_key
        self._version_id = version_id
        self._session = aiohttp_client.async_get_clientsession(hass)

    @property
    def _headers(self) -> dict[str, str]:
        return {
            API_KEY_HEADER: self._app_key,
            "Accept": "application/json",
            "User-Agent": API_USER_AGENT,
        }

    async def _get_json(
        self, path: str, params: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """GET ``path`` on the YouVersion API and return the parsed body."""
        url = f"{API_BASE_URL}{path}"
        try:
            async with asyncio.timeout(_REQUEST_TIMEOUT):
                async with self._session.get(
                    url, headers=self._headers, params=params
                ) as resp:
                    raw_body = await resp.text()
                    if resp.status in (401, 403):
                        raise UpdateFailed(
                            f"YouVersion rejected the app key (HTTP {resp.status}). "
                            "Check the App Key in the integration options."
                        )
                    if resp.status == 429:
                        raise UpdateFailed(
                            "YouVersion rate limit reached (HTTP 429)"
                        )
                    if resp.status >= 400:
                        raise UpdateFailed(
                            f"YouVersion API returned HTTP {resp.status} for "
                            f"{path}: {raw_body[:300]}"
                        )
        except ClientError as err:
            raise UpdateFailed(
                f"Error communicating with YouVersion: {err}"
            ) from err
        except TimeoutError as err:
            raise UpdateFailed("Timeout communicating with YouVersion") from err

        try:
            data = json.loads(raw_body)
        except ValueError as err:
            raise UpdateFailed(
                f"YouVersion API returned invalid JSON for {path}: "
                f"{raw_body[:300]}"
            ) from err

        if not isinstance(data, dict):
            raise UpdateFailed(
                f"YouVersion API returned an unexpected payload for {path}: "
                f"{raw_body[:300]}"
            )
        return data

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch today's verse: reference -> passage text (+ html)."""
        day = dt_util.now().timetuple().tm_yday

        # 1) Which passage is the verse of the day for this day-of-year.
        votd = await self._get_json(f"/verse_of_the_days/{day}")
        passage_id = votd.get("passage_id")
        if not passage_id:
            raise UpdateFailed(
                f"YouVersion returned no passage_id for day {day}: {votd}"
            )

        # 2) The passage text in the selected Bible version.
        text_resp = await self._get_json(
            f"/bibles/{self._version_id}/passages/{passage_id}",
            params={"format": "text"},
        )

        # 3) HTML rendering is a nice-to-have; don't fail the update on it.
        html_content: str | None = None
        try:
            html_resp = await self._get_json(
                f"/bibles/{self._version_id}/passages/{passage_id}",
                params={"format": "html"},
            )
            html_content = html_resp.get("content")
        except UpdateFailed as err:
            _LOGGER.debug(
                "Could not fetch HTML rendering for %s: %s", passage_id, err
            )

        text_content = text_resp.get("content") or _strip_html(html_content)

        return {
            "day": day,
            "passage_id": passage_id,
            "reference": text_resp.get("reference"),
            "text": text_content,
            "html": html_content,
            "version_id": self._version_id,
        }


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

        The state is limited to 255 characters in Home Assistant and verses
        can exceed that, so the short reference is the state and the full
        text is exposed as an attribute.
        """
        data = self.coordinator.data or {}
        reference = data.get("reference")
        return reference[:255] if reference else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        data = self.coordinator.data or {}
        passage_id = data.get("passage_id")
        return {
            "text": data.get("text"),
            "html": data.get("html"),
            "reference": data.get("reference"),
            "passage_id": passage_id,
            "day": data.get("day"),
            "version_id": self._version_id,
            "url": (
                f"https://www.bible.com/bible/{self._version_id}/{passage_id}"
                if passage_id
                else None
            ),
        }
