"""Config flow for the YouVersion Bible API integration."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import voluptuous as vol
from aiohttp import ClientError

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import aiohttp_client

from .const import (
    API_BASE_URL,
    API_USER_AGENT,
    CONF_LANGUAGE,
    CONF_TOKEN,
    CONF_VERSION,
    DEFAULT_VERSION_ID,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def _validate_token(
    hass: HomeAssistant, token: str, version_id: int, language: str
) -> str | None:
    """Validate credentials against the YouVersion API.

    Returns None on success, or an error key otherwise.
    """
    session = aiohttp_client.async_get_clientsession(hass)
    day = datetime.utcnow().timetuple().tm_yday

    url = f"{API_BASE_URL}/verse_of_the_day/{day}"
    headers = {
        "X-YouVersion-Developer-Token": token,
        "Accept": "application/json",
        "Accept-Language": language,
        "User-Agent": API_USER_AGENT,
    }
    params = {"version_id": str(version_id)}

    try:
        async with session.get(url, headers=headers, params=params) as resp:
            if resp.status in (401, 403):
                return "invalid_token"
            if resp.status == 404:
                return "invalid_version"
            if resp.status >= 400:
                _LOGGER.warning(
                    "YouVersion API returned unexpected status %s during validation",
                    resp.status,
                )
                return "cannot_connect"
    except ClientError as err:
        _LOGGER.warning("Error contacting YouVersion API: %s", err)
        return "cannot_connect"

    return None


class YouVersionConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the config flow for YouVersion Bible API."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle a configuration started by the user."""
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()

            error = await _validate_token(
                self.hass,
                user_input[CONF_TOKEN],
                user_input[CONF_VERSION],
                user_input[CONF_LANGUAGE],
            )
            if error:
                errors["base"] = error
            else:
                return self.async_create_entry(
                    title="YouVersion Bible API",
                    data={CONF_TOKEN: user_input[CONF_TOKEN]},
                    options={
                        CONF_VERSION: user_input[CONF_VERSION],
                        CONF_LANGUAGE: user_input[CONF_LANGUAGE],
                    },
                )

        default_language = self.hass.config.language or "en"
        schema = vol.Schema(
            {
                vol.Required(CONF_TOKEN): str,
                vol.Required(
                    CONF_VERSION, default=DEFAULT_VERSION_ID
                ): vol.All(vol.Coerce(int), vol.Range(min=1)),
                vol.Required(CONF_LANGUAGE, default=default_language): str,
            }
        )

        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
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

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            error = await _validate_token(
                self.hass,
                self.config_entry.data[CONF_TOKEN],
                user_input[CONF_VERSION],
                user_input[CONF_LANGUAGE],
            )
            if error:
                errors["base"] = error
            else:
                return self.async_create_entry(title="", data=user_input)

        current_version = self.config_entry.options.get(
            CONF_VERSION, DEFAULT_VERSION_ID
        )
        current_language = self.config_entry.options.get(
            CONF_LANGUAGE, self.hass.config.language or "en"
        )

        schema = vol.Schema(
            {
                vol.Required(CONF_VERSION, default=current_version): vol.All(
                    vol.Coerce(int), vol.Range(min=1)
                ),
                vol.Required(CONF_LANGUAGE, default=current_language): str,
            }
        )

        return self.async_show_form(
            step_id="init", data_schema=schema, errors=errors
        )
