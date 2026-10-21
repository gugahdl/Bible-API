"""Tests for setup, the coordinator and the sensors."""
from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from pytest_homeassistant_custom_component.common import async_fire_time_changed
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.verse_of_the_day.const import DOMAIN
from custom_components.verse_of_the_day.sensor import VerseOfTheDaySensor

from .conftest import BASE, COPYRIGHT, TEXT, make_entry, mock_day, today

NVI = "sensor.nvi_verse_of_the_day"
ARC = "sensor.arc_verse_of_the_day"


async def _setup(hass: HomeAssistant, entry=None):
    entry = entry or make_entry()
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_sensors(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """One sensor per version, with text, copyright and link."""
    mock_day(aioclient_mock, today())
    entry = await _setup(hass)
    assert entry.state is ConfigEntryState.LOADED

    for entity_id, version_id, name in ((NVI, 129, "NVI"), (ARC, 212, "ARC")):
        state = hass.states.get(entity_id)
        assert state is not None, entity_id
        assert state.state == "João 3:16"
        assert state.attributes["text"] == TEXT[version_id]
        assert state.attributes["html"] == f"<p>{TEXT[version_id]}</p>"
        assert state.attributes["copyright"] == COPYRIGHT[version_id]
        assert state.attributes["passage_id"] == "JHN.3.16"
        assert state.attributes["day"] == today()
        assert state.attributes["version"] == name
        assert state.attributes["version_id"] == version_id
        assert (
            state.attributes["url"]
            == f"https://www.bible.com/bible/{version_id}/JHN.3.16"
        )

    # The verse of the day is fetched once for both versions.
    votd_calls = [c for c in aioclient_mock.mock_calls if "verse" in str(c[1])]
    assert len(votd_calls) == 1


async def test_text_not_recorded() -> None:
    """Bible text stays out of the recorder database."""
    unrecorded = VerseOfTheDaySensor._Entity__combined_unrecorded_attributes
    assert {"text", "html", "copyright"} <= unrecorded
    assert "passage_id" not in unrecorded


async def test_cached_until_next_day(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Hourly wake-ups make no API calls; midnight fetches the new verse."""
    freezer.move_to("2026-10-21 12:00:00-07:00")
    mock_day(aioclient_mock, today())
    mock_day(aioclient_mock, today() + 1, "PSA.23.1")
    await _setup(hass)
    calls_after_setup = aioclient_mock.call_count

    for _ in range(5):
        freezer.tick(timedelta(hours=1))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
    assert aioclient_mock.call_count == calls_after_setup
    assert hass.states.get(NVI).attributes["day"] == today()

    freezer.move_to("2026-10-22 00:00:30-07:00")
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    freezer.tick(timedelta(seconds=15))  # request_refresh is debounced
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    state = hass.states.get(NVI)
    assert state.attributes["day"] == today()
    assert state.attributes["passage_id"] == "PSA.23.1"
    assert aioclient_mock.call_count > calls_after_setup


async def test_underscore_endpoint_fallback(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """If the documented path 404s, the older underscore path is used."""
    aioclient_mock.get(f"{BASE}/verse-of-the-days/{today()}", status=404)
    mock_day(aioclient_mock, today(), path="verse_of_the_days")
    await _setup(hass)

    assert hass.states.get(NVI).state == "João 3:16"


async def test_one_version_forbidden(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A version whose license isn't accepted is unavailable; others work."""
    aioclient_mock.get(
        f"{BASE}/bibles/212/passages/JHN.3.16?format=text", status=403
    )
    mock_day(aioclient_mock, today())
    await _setup(hass)

    assert hass.states.get(NVI).state == "João 3:16"
    assert hass.states.get(ARC).state == "unavailable"


async def test_no_copyright_no_text(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Text is never shown without its version's copyright notice."""
    aioclient_mock.get(f"{BASE}/bibles/212", json={"id": 212, "copyright": " "})
    mock_day(aioclient_mock, today())
    await _setup(hass)

    assert hass.states.get(NVI).state == "João 3:16"
    assert hass.states.get(ARC).state == "unavailable"


async def test_promotional_content_fallback(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Without ``copyright``, ``promotional_content`` is the notice."""
    aioclient_mock.get(
        f"{BASE}/bibles/212",
        json={"id": 212, "copyright": None, "promotional_content": "<p>© SBB</p>"},
    )
    mock_day(aioclient_mock, today())
    await _setup(hass)

    assert hass.states.get(ARC).attributes["copyright"] == "© SBB"


async def test_rate_limited_at_setup(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A 429 (plain-text body) makes setup retry later instead of crashing."""
    aioclient_mock.get(
        f"{BASE}/verse-of-the-days/{today()}",
        status=429,
        text="Rate limit exceeded.",
        headers={"Retry-After": "60"},
    )
    entry = await _setup(hass)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_migrates_old_primary_unique_id(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """The pre-3.1.0 ``{entry_id}_votd`` sensor keeps its entity id."""
    entry = make_entry()
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    old = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{entry.entry_id}_votd",
        config_entry=entry,
        suggested_object_id="nvi_verse_of_the_day",
    )
    mock_day(aioclient_mock, today())
    await _setup(hass, entry)

    migrated = registry.async_get(old.entity_id)
    assert migrated is not None
    assert migrated.unique_id == f"{entry.entry_id}_votd_129"
    assert hass.states.get(old.entity_id).attributes["version_id"] == 129
    assert hass.states.get(ARC) is not None


async def test_unload(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """The entry unloads cleanly."""
    mock_day(aioclient_mock, today())
    entry = await _setup(hass)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
