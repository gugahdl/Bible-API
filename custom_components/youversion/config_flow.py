"""Config flow for the YouVersion Bible API integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from aiohttp import ClientError

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    API_BASE_URL,
    API_USER_AGENT,
    COMMON_LANGUAGES,
    CONF_LANGUAGE,
    CONF_TOKEN,
    CONF_VERSION,
    DEFAULT_VERSION_ID,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

_MAX_VERSION_PAGES = 50


class InvalidAuth(Exception):
    """Raised when the YouVersion API rejects the token."""


class CannotConnect(Exception):
    """Raised when the YouVersion API cannot be reached."""


async def _fetch_versions(
    hass: HomeAssistant, token: str, language: str
) -> list[dict[str, Any]]:
    """Fetch the full list of Bible versions from the YouVersion API."""
    session = aiohttp_client.async_get_clientsession(hass)
    headers = {
        "X-YouVersion-Developer-Token": token,
        "Accept": "application/json",
        "Accept-Language": language,
        "User-Agent": API_USER_AGENT,
    }

    versions: list[dict[str, Any]] = []
    page = 1

    while page <= _MAX_VERSION_PAGES:
        try:
            async with session.get(
                f"{API_BASE_URL}/versions",
                headers=headers,
                params={"page": str(page)},
            ) as resp:
                if resp.status in (401, 403):
                    raise InvalidAuth
                if resp.status >= 400:
                    _LOGGER.warning(
                        "Unexpected status %s from YouVersion /versions", resp.status
                    )
                    raise CannotConnect
                body = await resp.json()
        except ClientError as err:
            _LOGGER.warning("Error contacting YouVersion API: %s", err)
            raise CannotConnect from err

        versions.extend(body.get("data") or [])
        if not body.get("next_page"):
            break
        page += 1

    return versions


def _build_version_options(
    versions: list[dict[str, Any]]
) -> list[dict[str, str]]:
    """Turn the raw versions list into selector options."""

    def label(version: dict[str, Any]) -> str:
        title = version.get("local_title") or version.get("title") or "Unknown"
        abbreviation = (
            version.get("local_abbreviation")
            or version.get("abbreviation")
            or ""
        )
        if abbreviation:
            return f"{title} ({abbreviation})"
        return title

    return sorted(
        (
            {"value": str(version["id"]), "label": label(version)}
            for version in versions
            if version.get("id") is not None
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
        self._token: str | None = None
        self._versions: list[dict[str, Any]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Ask the user for the developer token."""
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()

            token = user_input[CONF_TOKEN]
            language = self.hass.config.language or "en"
            try:
                versions = await _fetch_versions(self.hass, token, language)
            except InvalidAuth:
                errors["base"] = "invalid_token"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            else:
                if not versions:
                    errors["base"] = "no_versions"
                else:
                    self._token = token
                    self._versions = versions
                    return await self.async_step_select()

        schema = vol.Schema({vol.Required(CONF_TOKEN): str})
        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )

    async def async_step_select(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Let the user pick the Bible version and language."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                version_id = int(user_input[CONF_VERSION])
            except (TypeError, ValueError):
                errors["base"] = "invalid_version"
            else:
                assert self._token is not None
                return self.async_create_entry(
                    title="YouVersion Bible API",
                    data={CONF_TOKEN: self._token},
                    options={
                        CONF_VERSION: version_id,
                        CONF_LANGUAGE: user_input[CONF_LANGUAGE],
                    },
                )

        version_options = _build_version_options(self._versions)
        default_version = (
            str(DEFAULT_VERSION_ID)
            if any(opt["value"] == str(DEFAULT_VERSION_ID) for opt in version_options)
            else version_options[0]["value"]
        )
        default_language = self.hass.config.language or "en"

        schema = vol.Schema(
            {
                vol.Required(CONF_VERSION, default=default_version): SelectSelector(
                    SelectSelectorConfig(
                        options=version_options,
                        mode=SelectSelectorMode.DROPDOWN,
                        custom_value=False,
                    )
                ),
                vol.Required(
                    CONF_LANGUAGE, default=default_language
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
            step_id="select", data_schema=schema, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow handler."""
        return YouVersionOptionsFlow(config_entry)


class YouVersionOptionsFlow(OptionsFlow):
    """Handle options for the YouVersion Bible API."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry
        self._versions: list[dict[str, Any]] = []

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show version/language dropdowns fetched from the API."""
        errors: dict[str, str] = {}

        current_version = self.config_entry.options.get(
            CONF_VERSION, DEFAULT_VERSION_ID
        )
        current_language = self.config_entry.options.get(
            CONF_LANGUAGE, self.hass.config.language or "en"
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
                        CONF_LANGUAGE: user_input[CONF_LANGUAGE],
                    },
                )

        if not self._versions:
            try:
                self._versions = await _fetch_versions(
                    self.hass,
                    self.config_entry.data[CONF_TOKEN],
                    current_language,
                )
            except InvalidAuth:
                errors["base"] = "invalid_token"
            except CannotConnect:
                errors["base"] = "cannot_connect"

        version_options = _build_version_options(self._versions)

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
                vol.Required(CONF_VERSION, default=default_version): SelectSelector(
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
