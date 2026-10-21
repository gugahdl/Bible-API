"""Shared fixtures for the Bible Verse of the Day tests."""
from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from homeassistant.util import dt as dt_util

from custom_components.verse_of_the_day.config_flow import _key_unique_id
from custom_components.verse_of_the_day.const import (
    CONF_APP_KEY,
    CONF_LANGUAGE,
    CONF_VERSION_NAMES,
    CONF_VERSIONS,
    DOMAIN,
)

pytest_plugins = "pytest_homeassistant_custom_component"

BASE = "https://api.youversion.com/v1"
APP_KEY = "test-app-key"

BIBLES = {
    "data": [
        {"id": 129, "abbreviation": "NVI", "title": "Nova Versão Internacional"},
        {"id": 212, "abbreviation": "ARC", "title": "Almeida Revista e Corrigida"},
    ]
}
COPYRIGHT = {
    129: "Nova Versão Internacional © Biblica, Inc.",
    212: "Almeida Revista e Corrigida © Sociedade Bíblica do Brasil",
}
TEXT = {
    129: "Porque Deus tanto amou o mundo...",
    212: "Porque Deus amou o mundo de tal maneira...",
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: Any) -> None:
    """Let Home Assistant load the integration from custom_components/."""


@pytest.fixture(autouse=True)
def no_retry_delay():
    """Don't sleep between network retries in tests."""
    with patch("custom_components.verse_of_the_day.api._RETRY_DELAY", 0):
        yield


def today() -> int:
    """Day of the year, as the integration computes it."""
    return dt_util.now().timetuple().tm_yday


def mock_bibles(aioclient_mock: AiohttpClientMocker, **kwargs: Any) -> None:
    """Mock GET /bibles (pass status=... to make it fail)."""
    if kwargs:
        aioclient_mock.get(f"{BASE}/bibles", **kwargs)
    else:
        aioclient_mock.get(f"{BASE}/bibles", json=BIBLES)


def mock_day(
    aioclient_mock: AiohttpClientMocker,
    day: int,
    passage_id: str = "JHN.3.16",
    *,
    path: str = "verse-of-the-days",
    versions: tuple[int, ...] = (129, 212),
) -> None:
    """Mock everything one day's update needs."""
    aioclient_mock.get(
        f"{BASE}/{path}/{day}", json={"day": day, "passage_id": passage_id}
    )
    for version_id in versions:
        aioclient_mock.get(
            f"{BASE}/bibles/{version_id}/passages/{passage_id}?format=text",
            json={
                "id": passage_id,
                "content": TEXT[version_id],
                "reference": "João 3:16",
            },
        )
        aioclient_mock.get(
            f"{BASE}/bibles/{version_id}/passages/{passage_id}?format=html",
            json={"id": passage_id, "content": f"<p>{TEXT[version_id]}</p>"},
        )
        aioclient_mock.get(
            f"{BASE}/bibles/{version_id}",
            json={"id": version_id, "copyright": COPYRIGHT[version_id]},
        )


def make_entry(
    versions: list[int] | None = None, app_key: str = APP_KEY
) -> MockConfigEntry:
    """Return a config entry like the config flow creates."""
    versions = versions if versions is not None else [129, 212]
    names = {129: "NVI", 212: "ARC"}
    return MockConfigEntry(
        domain=DOMAIN,
        title="Bible Verse of the Day",
        unique_id=_key_unique_id(app_key),
        data={CONF_APP_KEY: app_key},
        options={
            CONF_VERSIONS: versions,
            CONF_VERSION_NAMES: {str(v): names[v] for v in versions},
            CONF_LANGUAGE: "por",
        },
    )
