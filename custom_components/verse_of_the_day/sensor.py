"""Sensor platform for the Bible Verse of the Day integration.

One config entry holds one App Key (from the YouVersion Platform API) and
can track several Bible versions at once (see helpers.py) -- this module
creates one coordinator + one sensor (its own device) per tracked version,
and drops the entity/device for any version that is no longer tracked after
the user changes the selection in the entry's options.
"""
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
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
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
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)
from .helpers import entry_version_names, entry_versions

_LOGGER = logging.getLogger(__name__)

_TAG_RE = re.compile(r"<[^>]+>")
_REQUEST_TIMEOUT = 15

# A DNS blip or a dropped connection is common and self-resolves in seconds;
# retry a couple of times within the same update before giving up (which
# would otherwise leave the sensor "unavailable" until the next poll).
_RETRY_ATTEMPTS = 3
_RETRY_DELAY = 5  # seconds between attempts


def _strip_html(raw_html: str | None) -> str:
    """Return a plain-text rendering of an HTML fragment."""
    if not raw_html:
        return ""
    return html_lib.unescape(_TAG_RE.sub("", raw_html)).strip()


def _unique_id_for(entry_id: str, version_id: int, *, is_primary: bool) -> str:
    """Return the sensor's unique id.

    The first/primary version of an entry keeps the pre-2.2.0 unique id
    (``{entry_id}_votd``, no version suffix) so upgrading an existing
    single-version install doesn't change its entity id. Any additional
    version tracked by the same entry gets its own suffixed id.
    """
    if is_primary:
        return f"{entry_id}_votd"
    return f"{entry_id}_votd_{version_id}"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one sensor per Bible version tracked by this entry."""
    hass.data.setdefault(DOMAIN, {})

    app_key = entry.data[CONF_APP_KEY]
    versions = entry_versions(entry)
    version_names = entry_version_names(entry)

    entities: list[VerseOfTheDaySensor] = []
    keep_unique_ids: set[str] = set()

    for index, version_id in enumerate(versions):
        version_name = version_names.get(version_id, str(version_id))
        unique_id = _unique_id_for(entry.entry_id, version_id, is_primary=index == 0)
        coordinator = VerseOfTheDayCoordinator(hass, app_key, version_id, version_name)
        await coordinator.async_config_entry_first_refresh()
        entities.append(
            VerseOfTheDaySensor(coordinator, entry, version_id, version_name, unique_id)
        )
        keep_unique_ids.add(unique_id)

    async_add_entities(entities)
    _cleanup_removed_versions(hass, entry, keep_unique_ids)


def _cleanup_removed_versions(
    hass: HomeAssistant, entry: ConfigEntry, keep_unique_ids: set[str]
) -> None:
    """Remove entities/devices for versions no longer tracked by this entry."""
    registry = er.async_get(hass)
    for entity_entry in list(
        er.async_entries_for_config_entry(registry, entry.entry_id)
    ):
        if entity_entry.unique_id not in keep_unique_ids:
            _LOGGER.debug(
                "Removing entity %s: its Bible version is no longer tracked",
                entity_entry.entity_id,
            )
            registry.async_remove(entity_entry.entity_id)

    device_registry = dr.async_get(hass)
    for device_entry in list(
        dr.async_entries_for_config_entry(device_registry, entry.entry_id)
    ):
        remaining = er.async_entries_for_device(
            registry, device_entry.id, include_disabled_entities=True
        )
        if not remaining:
            device_registry.async_remove_device(device_entry.id)


class VerseOfTheDayCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetches the verse of the day from the YouVersion Platform API."""

    def __init__(
        self,
        hass: HomeAssistant,
        app_key: str,
        version_id: int,
        version_name: str,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"Bible Verse of the Day ({version_name})",
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
        """GET ``path`` on the YouVersion API and return the parsed body.

        Transient network errors (DNS timeouts, dropped connections) are
        retried a few times before giving up; HTTP-level errors (bad key,
        rate limit, ...) fail immediately since retrying won't help.
        """
        url = f"{API_BASE_URL}{path}"
        raw_body: str | None = None
        status: int | None = None
        last_network_err: Exception | None = None

        for attempt in range(1, _RETRY_ATTEMPTS + 1):
            try:
                async with asyncio.timeout(_REQUEST_TIMEOUT):
                    async with self._session.get(
                        url, headers=self._headers, params=params
                    ) as resp:
                        status = resp.status
                        raw_body = await resp.text()
                break
            except (ClientError, TimeoutError) as err:
                last_network_err = err
                if attempt < _RETRY_ATTEMPTS:
                    _LOGGER.debug(
                        "YouVersion request to %s failed (%s); retrying in %ss "
                        "(%s/%s)",
                        path,
                        err,
                        _RETRY_DELAY,
                        attempt,
                        _RETRY_ATTEMPTS,
                    )
                    await asyncio.sleep(_RETRY_DELAY)

        if raw_body is None:
            raise UpdateFailed(
                f"Error communicating with YouVersion: {last_network_err}"
            ) from last_network_err

        if status in (401, 403):
            raise UpdateFailed(
                f"YouVersion rejected the app key (HTTP {status}). "
                "Check the App Key in the integration options."
            )
        if status == 429:
            raise UpdateFailed("YouVersion rate limit reached (HTTP 429)")
        if status is not None and status >= 400:
            raise UpdateFailed(
                f"YouVersion API returned HTTP {status} for {path}: "
                f"{raw_body[:300]}"
            )

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


class VerseOfTheDaySensor(
    CoordinatorEntity[VerseOfTheDayCoordinator], SensorEntity
):
    """Representation of the Verse of the Day sensor for one Bible version."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:book-open-variant"

    def __init__(
        self,
        coordinator: VerseOfTheDayCoordinator,
        entry: ConfigEntry,
        version_id: int,
        version_name: str,
        unique_id: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._version_id = version_id
        self._attr_name = "Verse of the Day"
        self._attr_unique_id = unique_id
        # A device per tracked version, so e.g. NVI and ARC show up as
        # clearly separate devices/entities instead of colliding on one name.
        # No `manufacturer` is set here on purpose -- this project is an
        # independent, unofficial client of the YouVersion API and isn't
        # branded as if it were their product; the README explains where
        # the data actually comes from.
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_{version_id}")},
            name=version_name,
            model="Bible Verse of the Day",
            entry_type=DeviceEntryType.SERVICE,
        )

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
