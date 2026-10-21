"""Tests for the config, options and reauth flows."""
from __future__ import annotations

from aiohttp import ClientError
import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.verse_of_the_day.config_flow import _key_unique_id
from custom_components.verse_of_the_day.const import (
    CONF_APP_KEY,
    CONF_LANGUAGE,
    CONF_VERSION,
    CONF_VERSION_NAMES,
    CONF_VERSIONS,
    DOMAIN,
)

from .conftest import APP_KEY, BASE, make_entry, mock_bibles, mock_day, today


async def _start(hass: HomeAssistant, app_key: str = APP_KEY):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["description_placeholders"]["portal_url"].startswith("https://")
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_APP_KEY: f"  {app_key} ", CONF_LANGUAGE: "por"}
    )


async def test_full_flow(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """App Key + language, then two versions -> one entry with both."""
    mock_bibles(aioclient_mock)
    mock_day(aioclient_mock, today())

    result = await _start(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "select"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_VERSION: ["212", "129"]}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_APP_KEY: APP_KEY}
    assert result["options"] == {
        CONF_VERSIONS: [129, 212],
        CONF_VERSION_NAMES: {"129": "NVI", "212": "ARC"},
        CONF_LANGUAGE: "por",
    }
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.unique_id == _key_unique_id(APP_KEY)
    assert APP_KEY not in entry.unique_id


@pytest.mark.parametrize(
    ("mock_kwargs", "error"),
    [
        ({"status": 401}, "invalid_app_key"),
        ({"status": 403, "text": "app archived"}, "forbidden"),
        ({"status": 429, "text": "Rate limit exceeded."}, "rate_limited"),
        ({"status": 503}, "cannot_connect"),
        ({"exc": ClientError()}, "cannot_connect"),
        # A language with no versions comes back as 204 with no body.
        ({"status": 204}, "no_versions"),
        ({"json": {"data": []}}, "no_versions"),
    ],
)
async def test_user_step_errors(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_kwargs: dict,
    error: str,
) -> None:
    """Each API failure maps to its own form error."""
    mock_bibles(aioclient_mock, **mock_kwargs)

    result = await _start(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": error}


async def test_same_app_key_aborts(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Adding an App Key that is already configured aborts."""
    make_entry().add_to_hass(hass)

    result = await _start(hass)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert aioclient_mock.call_count == 0


async def test_version_tracked_by_other_entry(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A version already tracked by another entry can't be picked again."""
    make_entry(versions=[129], app_key="other-key").add_to_hass(hass)
    mock_bibles(aioclient_mock)

    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_VERSION: ["129"]}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "version_in_use"}


async def test_options_change_versions(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """The options flow can drop a version without asking for the key."""
    entry = make_entry()
    entry.add_to_hass(hass)
    mock_bibles(aioclient_mock)
    mock_day(aioclient_mock, today())
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_VERSION: ["212"], CONF_LANGUAGE: "por"}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_VERSIONS] == [212]
    assert entry.options[CONF_VERSION_NAMES] == {"212": "ARC"}
    assert hass.states.get("sensor.nvi_verse_of_the_day") is None
    assert hass.states.get("sensor.arc_verse_of_the_day") is not None


async def test_options_language_change_reloads_list(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Changing the language reloads the version list before saving."""
    entry = make_entry(versions=[129])
    entry.add_to_hass(hass)
    mock_day(aioclient_mock, today(), versions=(129,))
    aioclient_mock.get(
        f"{BASE}/bibles?language_ranges[]=eng",
        json={"data": [{"id": 111, "abbreviation": "NIV", "title": "NIV"}]},
    )
    mock_bibles(aioclient_mock)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_VERSION: ["129"], CONF_LANGUAGE: "eng"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "language_changed"}
    assert entry.options[CONF_LANGUAGE] == "por"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_VERSION: ["129", "111"], CONF_LANGUAGE: "eng"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_LANGUAGE] == "eng"
    assert entry.options[CONF_VERSIONS] == [111, 129]
    # The old version keeps its name even though it is not in the new list.
    assert entry.options[CONF_VERSION_NAMES] == {"111": "NIV", "129": "NVI"}


async def test_reauth(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A rejected key at setup starts reauth, and a new key fixes it."""
    entry = make_entry(app_key="old-key")
    entry.add_to_hass(hass)
    aioclient_mock.get(f"{BASE}/verse-of-the-days/{today()}", status=401)

    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is config_entries.ConfigEntryState.SETUP_ERROR

    flows = hass.config_entries.flow.async_progress()
    assert len(flows) == 1
    assert flows[0]["context"]["source"] == config_entries.SOURCE_REAUTH

    aioclient_mock.clear_requests()
    mock_bibles(aioclient_mock)
    mock_day(aioclient_mock, today())
    result = await hass.config_entries.flow.async_configure(
        flows[0]["flow_id"], {CONF_APP_KEY: "new-key"}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_APP_KEY] == "new-key"
    assert entry.unique_id == _key_unique_id("new-key")
    assert entry.state is config_entries.ConfigEntryState.LOADED


async def test_reauth_invalid_key(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A wrong key in the reauth form shows an error and keeps the old key."""
    entry = make_entry()
    entry.add_to_hass(hass)
    mock_bibles(aioclient_mock, status=401)

    result = await entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_APP_KEY: "still-wrong"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_app_key"}
    assert entry.data[CONF_APP_KEY] == APP_KEY
