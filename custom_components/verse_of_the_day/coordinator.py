"""Data coordinator for the Bible Verse of the Day integration.

One coordinator per config entry. The verse of the day is the same for
every Bible version, so it is fetched once and shared; each tracked version
then needs its passage text plus its copyright notice. All of it changes
only once a day, so once today's data is in, later wake-ups return the
cached result without touching the API.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util import dt as dt_util

from .api import (
    ApiAuthError,
    ApiError,
    ApiForbiddenError,
    ApiRateLimitError,
    BibleApiClient,
    bible_attribution,
    strip_html,
)
from .const import DEFAULT_UPDATE_INTERVAL, DOMAIN
from .helpers import entry_versions

_LOGGER = logging.getLogger(__name__)

type VerseOfTheDayConfigEntry = ConfigEntry[VerseOfTheDayCoordinator]


class VerseOfTheDayCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetches today's verse for every Bible version of one entry.

    ``data`` is ``{"day", "passage_id", "versions": {version_id: {...}}}``.
    A version missing from ``versions`` could not be fetched today; its
    sensor shows as unavailable and the next wake-up retries just that one.
    """

    config_entry: VerseOfTheDayConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: VerseOfTheDayConfigEntry,
        client: BibleApiClient,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=DEFAULT_UPDATE_INTERVAL,
        )
        self.client = client
        self.versions = entry_versions(entry)

    async def _async_update_data(self) -> dict[str, Any]:
        """Return today's verse, calling the API only for what is missing."""
        day = dt_util.now().timetuple().tm_yday
        today = self.data if self.data and self.data.get("day") == day else None
        cached: dict[int, dict[str, Any]] = dict(today["versions"]) if today else {}

        if today and all(version_id in cached for version_id in self.versions):
            return today

        if today:
            passage_id = today["passage_id"]
        else:
            try:
                passage_id = await self.client.async_get_verse_of_the_day(day)
            except ApiAuthError as err:
                raise ConfigEntryAuthFailed(str(err)) from err
            except ApiError as err:
                raise UpdateFailed(
                    f"Could not fetch the verse of the day: {err}"
                ) from err

        versions: dict[int, dict[str, Any]] = {}
        for version_id in self.versions:
            if version_id in cached:
                versions[version_id] = cached[version_id]
                continue
            try:
                versions[version_id] = await self._async_fetch_version(
                    version_id, passage_id
                )
            except ApiAuthError as err:
                raise ConfigEntryAuthFailed(str(err)) from err
            except ApiRateLimitError as err:
                # Every further call would hit the same limit; stop here and
                # let the next wake-up pick up the remaining versions.
                _LOGGER.warning("%s; will retry later", err)
                break
            except ApiForbiddenError as err:
                _LOGGER.warning(
                    "Bible version %s is not available to this App Key -- is "
                    "its license accepted on the developer portal? (%s)",
                    version_id,
                    err,
                )
            except ApiError as err:
                _LOGGER.warning(
                    "Could not fetch Bible version %s: %s", version_id, err
                )

        if not versions:
            raise UpdateFailed(
                "Could not fetch the verse of the day for any tracked Bible "
                "version"
            )
        return {"day": day, "passage_id": passage_id, "versions": versions}

    async def _async_fetch_version(
        self, version_id: int, passage_id: str
    ) -> dict[str, Any]:
        """Fetch one version's text, HTML and copyright notice."""
        text_resp = await self.client.async_get_passage(
            version_id, passage_id, "text"
        )

        # The HTML rendering is a nice-to-have; don't fail the version on it.
        html_content: str | None = None
        try:
            html_resp = await self.client.async_get_passage(
                version_id, passage_id, "html"
            )
            html_content = html_resp.get("content")
        except (ApiAuthError, ApiRateLimitError):
            raise
        except ApiError as err:
            _LOGGER.debug(
                "Could not fetch HTML rendering for %s: %s", passage_id, err
            )

        # The license requires the version's copyright notice wherever its
        # text is shown. Like the official SDKs, refuse to show text that has
        # no notice rather than show it without one.
        attribution = bible_attribution(
            await self.client.async_get_bible(version_id)
        )
        if not attribution:
            raise ApiError(
                f"Bible version {version_id} has no copyright notice to show "
                "with its text"
            )

        text = text_resp.get("content") or strip_html(html_content)
        if not text:
            raise ApiError(f"Empty passage {passage_id} for version {version_id}")

        return {
            "reference": text_resp.get("reference") or passage_id,
            "text": text,
            "html": html_content,
            "copyright": attribution,
        }
