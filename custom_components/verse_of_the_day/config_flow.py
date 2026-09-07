"""Config flow for the Bible Verse of the Day integration.

One entry holds one App Key (from the YouVersion Platform API) and can track
several Bible versions at once -- the App Key is entered once
(async_step_user) and versions are picked with a multi-select
(async_step_select). Add or remove versions later from the entry's
"Configure" (options) without touching the App Key again.
"""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from aiohttp import ClientError

from homeassistant import config_entries
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    API_BASE_URL,
    API_KEY_HEADER,
    API_USER_AGENT,
    COMMON_LANGUAGES,
    CONF_APP_KEY,
    CONF_LANGUAGE,
    CONF_VERSION,
    CONF_VERSION_NAMES,
    CONF_VERSIONS,
    DEFAULT_LANGUAGE_RANGE,
    DEFAULT_VERSION_ID,
    DOMAIN,
)
from .helpers import entry_versions, versions_tracked_elsewhere

_LOGGER = logging.getLogger(__name__)

_MAX_BIBLE_PAGES = 20
_PAGE_SIZE = 99


class InvalidAuth(Exception):
    """Raised when the YouVersion API rejects the app key."""


class CannotConnect(Exception):
    """Raised when the YouVersion API cannot be reached."""


async def _fetch_bibles(
    hass: HomeAssistant, app_key: str, language_range: str
) -> list[dict[str, Any]]:
    """Return the list of Bibles enabled for this app key in ``language_range``.

    Calls ``GET /v1/bibles`` on the YouVersion Platform API, following
    ``next_page_token`` pagination.
    """
    session = aiohttp_client.async_get_clientsession(hass)
    headers = {
        API_KEY_HEADER: app_key,
        "Accept": "application/json",
        "User-Agent": API_USER_AGENT,
    }

    bibles: list[dict[str, Any]] = []
    page_token: str | None = None

    for _ in range(_MAX_BIBLE_PAGES):
        params: list[tuple[str, str]] = [
            ("language_ranges[]", language_range),
            ("page_size", str(_PAGE_SIZE)),
        ]
        if page_token:
            params.append(("page_token", page_token))

        try:
            async with session.get(
                f"{API_BASE_URL}/bibles", headers=headers, params=params
            ) as resp:
                if resp.status in (401, 403):
                    raise InvalidAuth
                if resp.status >= 400:
                    text = await resp.text()
                    _LOGGER.warning(
                        "Unexpected status %s from YouVersion /bibles: %s",
                        resp.status,
                        text[:300],
                    )
                    raise CannotConnect
                body = await resp.json()
        except ClientError as err:
            _LOGGER.warning("Error contacting YouVersion API: %s", err)
            raise CannotConnect from err

        bibles.extend(body.get("data") or [])
        page_token = body.get("next_page_token")
        if not page_token:
            break

    return bibles


def _bible_label(bible: dict[str, Any]) -> str:
    """Build a human-readable label for a Bible entry."""
    title = (
        bible.get("localized_title")
        or bible.get("title")
        or f"Bible {bible.get('id')}"
    )
    abbreviation = (
        bible.get("localized_abbreviation") or bible.get("abbreviation") or ""
    )
    return f"{title} ({abbreviation})" if abbreviation else title


def _bible_short_label(bible: dict[str, Any]) -> str:
    """Short label used for the device name (e.g. "NVI").

    Several versions can be tracked at once, each as its own device, so this
    needs to stay short and distinct.
    """
    return (
        bible.get("localized_abbreviation")
        or bible.get("abbreviation")
        or bible.get("localized_title")
        or bible.get("title")
        or f"Bible {bible.get('id')}"
    )


def _build_version_options(
    bibles: list[dict[str, Any]]
) -> list[dict[str, str]]:
    """Turn the raw bibles list into selector options."""
    return sorted(
        (
            {"value": str(bible["id"]), "label": _bible_label(bible)}
            for bible in bibles
            if bible.get("id") is not None
        ),
        key=lambda option: option["label"].lower(),
    )


def _language_options() -> list[dict[str, str]]:
    """Return the language selector options."""
    return [
        {"value": code, "label": f"{name} ({code})"}
        for code, name in COMMON_LANGUAGES.items()
    ]


def _parse_selected_versions(raw: Any) -> list[int] | None:
    """Parse the multi-select's raw value into a sorted list of ints, or None."""
    if not raw:
        return None
    try:
        return sorted({int(v) for v in raw})
    except (TypeError, ValueError):
        return None


class VerseOfTheDayConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the config flow for Bible Verse of the Day."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._app_key: str | None = None
        self._language: str = DEFAULT_LANGUAGE_RANGE
        self._bibles: list[dict[str, Any]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the app key and language, then validate against the API."""
        errors: dict[str, str] = {}

        if user_input is not None:
            app_key = user_input[CONF_APP_KEY].strip()
            language = (
                user_input[CONF_LANGUAGE].strip() or DEFAULT_LANGUAGE_RANGE
            )
            try:
                bibles = await _fetch_bibles(self.hass, app_key, language)
            except InvalidAuth:
                errors["base"] = "invalid_app_key"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            else:
                if not bibles:
                    errors["base"] = "no_versions"
                else:
                    self._app_key = app_key
                    self._language = language
                    self._bibles = bibles
                    return await self.async_step_select()

        schema = vol.Schema(
            {
                vol.Required(CONF_APP_KEY): str,
                vol.Required(
                    CONF_LANGUAGE, default=DEFAULT_LANGUAGE_RANGE
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=_language_options(),
                        mode=SelectSelectorMode.DROPDOWN,
                        custom_value=True,
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )

    async def async_step_select(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user pick one or more Bible versions to track."""
        errors: dict[str, str] = {}
        version_options = _build_version_options(self._bibles)

        if user_input is not None:
            version_ids = _parse_selected_versions(user_input[CONF_VERSION])
            in_use = versions_tracked_elsewhere(self.hass) if version_ids else set()
            if version_ids is None:
                errors["base"] = "no_selection"
            elif version_ids and (dupes := set(version_ids) & in_use):
                errors["base"] = "version_in_use"
                _LOGGER.debug("Versions already tracked elsewhere: %s", dupes)
            else:
                by_id = {b["id"]: b for b in self._bibles if b.get("id") is not None}
                version_names = {
                    str(vid): _bible_short_label(by_id[vid])
                    for vid in version_ids
                    if vid in by_id
                }
                assert self._app_key is not None
                labels = ", ".join(version_names.values())
                return self.async_create_entry(
                    title=f"Bible Verse of the Day – {labels}",
                    data={CONF_APP_KEY: self._app_key},
                    options={
                        CONF_VERSIONS: version_ids,
                        CONF_VERSION_NAMES: version_names,
                        CONF_LANGUAGE: self._language,
                    },
                )

        default_versions = (
            [str(DEFAULT_VERSION_ID)]
            if any(opt["value"] == str(DEFAULT_VERSION_ID) for opt in version_options)
            else [version_options[0]["value"]]
        )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_VERSION, default=default_versions
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=version_options,
                        mode=SelectSelectorMode.DROPDOWN,
                        multiple=True,
                        custom_value=False,
                    )
                )
            }
        )
        return self.async_show_form(
            step_id="select", data_schema=schema, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow handler."""
        return VerseOfTheDayOptionsFlow()


class VerseOfTheDayOptionsFlow(OptionsFlow):
    """Change which Bible versions (and language) this entry tracks."""

    def __init__(self) -> None:
        """Initialize options flow."""
        self._bibles: list[dict[str, Any]] = []

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show a multi-select of versions fetched live from the API."""
        errors: dict[str, str] = {}

        current_versions = entry_versions(self.config_entry)
        current_language = self.config_entry.options.get(
            CONF_LANGUAGE, DEFAULT_LANGUAGE_RANGE
        )

        if user_input is not None:
            language = (
                user_input[CONF_LANGUAGE].strip() or DEFAULT_LANGUAGE_RANGE
            )
            version_ids = _parse_selected_versions(user_input[CONF_VERSION])
            in_use = versions_tracked_elsewhere(
                self.hass, exclude_entry_id=self.config_entry.entry_id
            )
            if version_ids is None:
                errors["base"] = "no_selection"
            elif dupes := set(version_ids) & in_use:
                errors["base"] = "version_in_use"
                _LOGGER.debug("Versions already tracked elsewhere: %s", dupes)
            else:
                by_id = {b["id"]: b for b in self._bibles if b.get("id") is not None}
                version_names = {
                    str(vid): (
                        _bible_short_label(by_id[vid])
                        if vid in by_id
                        else str(vid)
                    )
                    for vid in version_ids
                }
                return self.async_create_entry(
                    title="",
                    data={
                        CONF_VERSIONS: version_ids,
                        CONF_VERSION_NAMES: version_names,
                        CONF_LANGUAGE: language,
                    },
                )

        if not self._bibles:
            try:
                self._bibles = await _fetch_bibles(
                    self.hass,
                    self.config_entry.data[CONF_APP_KEY],
                    current_language,
                )
            except InvalidAuth:
                errors["base"] = "invalid_app_key"
            except CannotConnect:
                errors["base"] = "cannot_connect"

        version_options = _build_version_options(self._bibles)

        # If the fetch failed, still show the currently tracked versions so
        # the user isn't fully locked out (they just can't add new ones now).
        known_values = {opt["value"] for opt in version_options}
        for version_id in current_versions:
            if str(version_id) not in known_values:
                version_options.append(
                    {"value": str(version_id), "label": f"ID {version_id}"}
                )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_VERSION, default=[str(v) for v in current_versions]
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=version_options,
                        mode=SelectSelectorMode.DROPDOWN,
                        multiple=True,
                        custom_value=False,
                    )
                ),
                vol.Required(
                    CONF_LANGUAGE, default=current_language
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=_language_options(),
                        mode=SelectSelectorMode.DROPDOWN,
                        custom_value=True,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="init", data_schema=schema, errors=errors
        )
