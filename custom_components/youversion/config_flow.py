"""Config flow for the YouVersion Bible API integration."""
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
    DEFAULT_LANGUAGE_RANGE,
    DEFAULT_VERSION_ID,
    DOMAIN,
)

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


class YouVersionConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the config flow for the YouVersion Bible API."""

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
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()

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
        """Let the user pick the Bible version."""
        errors: dict[str, str] = {}
        version_options = _build_version_options(self._bibles)

        if user_input is not None:
            try:
                version_id = int(user_input[CONF_VERSION])
            except (TypeError, ValueError):
                errors["base"] = "invalid_version"
            else:
                assert self._app_key is not None
                return self.async_create_entry(
                    title="YouVersion Bible API",
                    data={CONF_APP_KEY: self._app_key},
                    options={
                        CONF_VERSION: version_id,
                        CONF_LANGUAGE: self._language,
                    },
                )

        default_version = (
            str(DEFAULT_VERSION_ID)
            if any(opt["value"] == str(DEFAULT_VERSION_ID) for opt in version_options)
            else version_options[0]["value"]
        )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_VERSION, default=default_version
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=version_options,
                        mode=SelectSelectorMode.DROPDOWN,
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
        return YouVersionOptionsFlow()


class YouVersionOptionsFlow(OptionsFlow):
    """Handle options for the YouVersion Bible API."""

    def __init__(self) -> None:
        """Initialize options flow."""
        self._bibles: list[dict[str, Any]] = []

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show version/language dropdowns fetched from the API."""
        errors: dict[str, str] = {}

        current_version = self.config_entry.options.get(
            CONF_VERSION, DEFAULT_VERSION_ID
        )
        current_language = self.config_entry.options.get(
            CONF_LANGUAGE, DEFAULT_LANGUAGE_RANGE
        )

        if user_input is not None:
            try:
                version_id = int(user_input[CONF_VERSION])
            except (TypeError, ValueError):
                errors["base"] = "invalid_version"
            else:
                return self.async_create_entry(
                    title="",
                    data={
                        CONF_VERSION: version_id,
                        CONF_LANGUAGE: (
                            user_input[CONF_LANGUAGE].strip()
                            or DEFAULT_LANGUAGE_RANGE
                        ),
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

        # If the fetch failed, still show a usable form with the current value
        # so the user isn't fully locked out.
        if not version_options:
            version_options = [
                {
                    "value": str(current_version),
                    "label": f"ID {current_version}",
                }
            ]

        default_version = (
            str(current_version)
            if any(opt["value"] == str(current_version) for opt in version_options)
            else version_options[0]["value"]
        )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_VERSION, default=default_version
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=version_options,
                        mode=SelectSelectorMode.DROPDOWN,
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
