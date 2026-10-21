"""Helpers shared by the config flow and the sensor platform."""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_VERSION_NAMES, CONF_VERSIONS, DOMAIN


def _as_int_set(raw: Any) -> set[int]:
    result: set[int] = set()
    for value in raw or []:
        try:
            result.add(int(value))
        except (TypeError, ValueError):
            continue
    return result


def entry_versions(entry: ConfigEntry) -> list[int]:
    """Return the Bible version ids tracked by ``entry``, sorted."""
    return sorted(_as_int_set(entry.options.get(CONF_VERSIONS)))


def entry_version_names(entry: ConfigEntry) -> dict[int, str]:
    """Return ``{version_id: short label}`` for the versions of ``entry``."""
    names: dict[int, str] = {}
    for key, label in (entry.options.get(CONF_VERSION_NAMES) or {}).items():
        try:
            names[int(key)] = str(label)
        except (TypeError, ValueError):
            continue
    return names


def sensor_unique_id(entry_id: str, version_id: int) -> str:
    """Return the unique id of the sensor for one tracked version."""
    return f"{entry_id}_votd_{version_id}"


def versions_tracked_elsewhere(
    hass: HomeAssistant, exclude_entry_id: str | None = None
) -> set[int]:
    """Return the version ids already tracked by other entries of this domain."""
    in_use: set[int] = set()
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.entry_id != exclude_entry_id:
            in_use.update(entry_versions(entry))
    return in_use
