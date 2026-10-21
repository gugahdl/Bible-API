"""Sensor platform for the Bible Verse of the Day integration.

One config entry can track several Bible versions (see helpers.py); this
module creates one sensor (its own device) per tracked version, all fed by
the entry's single coordinator, and drops the entity/device for any version
that is no longer tracked after the user changes the entry's options.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import VerseOfTheDayConfigEntry, VerseOfTheDayCoordinator
from .helpers import entry_version_names, sensor_unique_id

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VerseOfTheDayConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one sensor per Bible version tracked by this entry."""
    coordinator = entry.runtime_data
    version_names = entry_version_names(entry)

    entities = [
        VerseOfTheDaySensor(
            coordinator,
            entry.entry_id,
            version_id,
            version_names.get(version_id, str(version_id)),
        )
        for version_id in coordinator.versions
    ]
    async_add_entities(entities)
    _cleanup_removed_versions(
        hass, entry, {entity.unique_id for entity in entities}
    )


def _cleanup_removed_versions(
    hass: HomeAssistant, entry: VerseOfTheDayConfigEntry, keep_unique_ids: set[str]
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


class VerseOfTheDaySensor(
    CoordinatorEntity[VerseOfTheDayCoordinator], SensorEntity
):
    """Representation of the Verse of the Day sensor for one Bible version."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:book-open-variant"
    _attr_name = "Verse of the Day"
    # The Bible text is shown live, not stored: keep it (and its notice) out
    # of the recorder database. Only the short reference -- the state -- and
    # the small metadata attributes end up in history.
    _unrecorded_attributes = frozenset({"text", "html", "copyright"})

    def __init__(
        self,
        coordinator: VerseOfTheDayCoordinator,
        entry_id: str,
        version_id: int,
        version_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._version_id = version_id
        self._version_name = version_name
        self._attr_unique_id = sensor_unique_id(entry_id, version_id)
        # A device per tracked version, so e.g. NVI and ARC show up as
        # clearly separate devices/entities instead of colliding on one name.
        # No `manufacturer` is set here on purpose -- this project is an
        # independent, unofficial API client and isn't branded as if it were
        # the API provider's product.
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_{version_id}")},
            name=version_name,
            model="Bible Verse of the Day",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def _version_data(self) -> dict[str, Any] | None:
        data = self.coordinator.data or {}
        return data.get("versions", {}).get(self._version_id)

    @property
    def available(self) -> bool:
        """Unavailable when today's verse could not be fetched for this version."""
        return super().available and self._version_data is not None

    @property
    def native_value(self) -> str | None:
        """Return the verse reference as the state.

        The state is limited to 255 characters in Home Assistant and verses
        can exceed that, so the short reference is the state and the full
        text is exposed as an attribute.
        """
        version = self._version_data or {}
        reference = version.get("reference")
        return reference[:255] if reference else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        data = self.coordinator.data or {}
        version = self._version_data or {}
        passage_id = data.get("passage_id")
        return {
            "text": version.get("text"),
            "html": version.get("html"),
            "reference": version.get("reference"),
            # Must be shown together with the text -- see the README.
            "copyright": version.get("copyright"),
            "passage_id": passage_id,
            "day": data.get("day"),
            "version": self._version_name,
            "version_id": self._version_id,
            "url": (
                f"https://www.bible.com/bible/{self._version_id}/{passage_id}"
                if passage_id
                else None
            ),
        }
