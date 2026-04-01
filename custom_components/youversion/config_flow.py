import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client

from .const import DOMAIN, CONF_TOKEN, CONF_VERSION

API_VALIDATE_URL = "https://developers.youversionapi.com/1.0/verse_of_the_day.json"


async def validate_token(hass: HomeAssistant, token: str) -> bool:
    """Validate the YouVersion API token."""
    session = aiohttp_client.async_get_clientsession(hass)

    headers = {
        "X-YouVersion-Developer-Token": token,
        "Accept-Language": "en"
    }

    try:
        async with session.get(API_VALIDATE_URL, headers=headers) as resp:
            return resp.status == 200
    except Exception:
        return False


class YouVersionConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the config flow for YouVersion Bible API."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            token = user_input[CONF_TOKEN]

            valid = await validate_token(self.hass, token)
            if not valid:
                errors["base"] = "invalid_token"
            else:
                return self.async_create_entry(
                    title="YouVersion Bible API",
                    data=user_input
                )

        schema = vol.Schema({
            vol.Required(CONF_TOKEN): str,
            vol.Optional(CONF_VERSION, default="nvi"): str
        })

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors
        )

    async def async_step_import(self, user_input):
        """Handle import from configuration.yaml (optional)."""
        return await self.async_step_user(user_input)


class YouVersionOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow."""

    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        errors = {}

        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        schema = vol.Schema({
            vol.Required(
                CONF_VERSION,
                default=self.config_entry.options.get(CONF_VERSION, "nvi")
            ): str
        })

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors
        )


async def async_get_options_flow(config_entry):
    return YouVersionOptionsFlow(config_entry)
