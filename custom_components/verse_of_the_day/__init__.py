"""Bible Verse of the Day -- an unofficial client of a third-party Bible API."""
from __future__ import annotations

from datetime import datetime

from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_time_change

from .api import BibleApiClient
from .const import CONF_APP_KEY, DOMAIN, PLATFORMS
from .coordinator import VerseOfTheDayConfigEntry, VerseOfTheDayCoordinator
from .helpers import entry_versions, sensor_unique_id


async def async_setup_entry(
    hass: HomeAssistant, entry: VerseOfTheDayConfigEntry
) -> bool:
    """Set up this entry."""
    _migrate_primary_unique_id(hass, entry)

    client = BibleApiClient(
        aiohttp_client.async_get_clientsession(hass), entry.data[CONF_APP_KEY]
    )
    coordinator = VerseOfTheDayCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    # The verse changes at midnight; fetch the new one right away instead of
    # waiting for the next hourly wake-up.
    async def _async_new_day(now: datetime) -> None:
        await coordinator.async_request_refresh()

    entry.async_on_unload(
        async_track_time_change(hass, _async_new_day, hour=0, minute=0, second=30)
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: VerseOfTheDayConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(
    hass: HomeAssistant, entry: VerseOfTheDayConfigEntry
) -> None:
    """Reload the config entry when options are updated."""
    await hass.config_entries.async_reload(entry.entry_id)


def _migrate_primary_unique_id(
    hass: HomeAssistant, entry: VerseOfTheDayConfigEntry
) -> None:
    """Give the first version's sensor the same unique id scheme as the rest.

    Before 3.1.0 the first tracked version used ``{entry_id}_votd`` with no
    version suffix. Removing that version then handed its entity (and entity
    id) to whichever version became first. Renaming it in place keeps the
    entity id the user already has.
    """
    versions = entry_versions(entry)
    if not versions:
        return
    registry = er.async_get(hass)
    old_entity_id = registry.async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_votd"
    )
    new_unique_id = sensor_unique_id(entry.entry_id, versions[0])
    if old_entity_id and not registry.async_get_entity_id(
        "sensor", DOMAIN, new_unique_id
    ):
        registry.async_update_entity(old_entity_id, new_unique_id=new_unique_id)
