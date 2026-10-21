"""Config flow for the Bible Verse of the Day integration.

One entry holds one App Key and can track several Bible versions at once --
the App Key is entered once (async_step_user) and versions are picked with a
multi-select (async_step_select). Add or remove versions later from the
entry's "Configure" (options) without touching the App Key again. If the key
stops working, Home Assistant asks for a new one (async_step_reauth).
"""
from __future__ import annotations

from collections.abc import Mapping
import hashlib
import logging
from typing import Any

import voluptuous as vol

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

from .api import (
    ApiAuthError,
    ApiError,
    ApiForbiddenError,
    ApiRateLimitError,
    BibleApiClient,
)
from .const import (
    CONF_APP_KEY,
    CONF_LANGUAGE,
    CONF_VERSION,
    CONF_VERSION_NAMES,
    CONF_VERSIONS,
    COMMON_LANGUAGES,
    DEFAULT_LANGUAGE_RANGE,
    DEFAULT_VERSION_ID,
    DOMAIN,
)
from .helpers import entry_version_names, entry_versions, versions_tracked_elsewhere

_LOGGER = logging.getLogger(__name__)


def _key_unique_id(app_key: str) -> str:
    """Return a non-reversible id for an App Key, used as the entry's unique id.

    The key itself is a secret, so only a hash of it is stored there.
    """
    return hashlib.sha256(app_key.encode()).hexdigest()[:16]


async def _fetch_bibles(
    hass: HomeAssistant, app_key: str, language_range: str
) -> tuple[list[dict[str, Any]], str | None]:
    """Return ``(bibles, error_key)`` for this App Key and language.

    ``error_key`` is the translation key of the form error to show, or None.
    """
    client = BibleApiClient(aiohttp_client.async_get_clientsession(hass), app_key)
    try:
        return await client.async_get_bibles(language_range), None
    except ApiAuthError:
        return [], "invalid_app_key"
    except ApiForbiddenError as err:
        _LOGGER.warning("App Key recognized but not permitted: %s", err)
        return [], "forbidden"
    except ApiRateLimitError:
        return [], "rate_limited"
    except ApiError as err:
        _LOGGER.warning("Error contacting the Bible API: %s", err)
        return [], "cannot_connect"


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


def _language_selector() -> SelectSelector:
    return SelectSelector(
        SelectSelectorConfig(
            options=_language_options(),
            mode=SelectSelectorMode.DROPDOWN,
            custom_value=True,
        )
    )


def _versions_selector(options: list[dict[str, str]]) -> SelectSelector:
    return SelectSelector(
        SelectSelectorConfig(
            options=options,
            mode=SelectSelectorMode.DROPDOWN,
            multiple=True,
            custom_value=False,
        )
    )


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
            await self.async_set_unique_id(_key_unique_id(app_key))
            self._abort_if_unique_id_configured()

            bibles, error = await _fetch_bibles(self.hass, app_key, language)
            if error:
                errors["base"] = error
            elif not bibles:
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
                ): _language_selector(),
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
            elif dupes := set(version_ids) & in_use:
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
                ): _versions_selector(version_options)
            }
        )
        return self.async_show_form(
            step_id="select", data_schema=schema, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start re-authentication after the API rejected the stored App Key."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a new App Key and validate it."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()

        if user_input is not None:
            app_key = user_input[CONF_APP_KEY].strip()
            unique_id = _key_unique_id(app_key)
            if any(
                other.unique_id == unique_id and other.entry_id != entry.entry_id
                for other in self._async_current_entries(include_ignore=False)
            ):
                return self.async_abort(reason="already_configured")

            language = entry.options.get(CONF_LANGUAGE, DEFAULT_LANGUAGE_RANGE)
            _, error = await _fetch_bibles(self.hass, app_key, language)
            if error:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    unique_id=unique_id,
                    data_updates={CONF_APP_KEY: app_key},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_APP_KEY): str}),
            errors=errors,
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
        self._language: str | None = None
        self._selected: list[int] | None = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show a multi-select of versions fetched live from the API."""
        errors: dict[str, str] = {}
        current_versions = entry_versions(self.config_entry)
        known_names = entry_version_names(self.config_entry)
        if self._language is None:
            self._language = self.config_entry.options.get(
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
            if language != self._language:
                # The list on screen belongs to the old language: load the
                # new language's versions and show the form again.
                self._language = language
                self._bibles = []
                self._selected = version_ids or current_versions
                errors["base"] = "language_changed"
            elif version_ids is None:
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
                        else known_names.get(vid, str(vid))
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
            self._bibles, error = await _fetch_bibles(
                self.hass, self.config_entry.data[CONF_APP_KEY], self._language
            )
            if error:
                errors["base"] = error

        version_options = _build_version_options(self._bibles)
        selected = self._selected if self._selected is not None else current_versions

        # Keep already-selected versions on the list even when the fetch
        # failed or they belong to another language, so they can still be
        # kept or deselected.
        known_values = {opt["value"] for opt in version_options}
        for version_id in selected:
            if str(version_id) not in known_values:
                version_options.append(
                    {
                        "value": str(version_id),
                        "label": known_names.get(version_id, f"ID {version_id}"),
                    }
                )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_VERSION, default=[str(v) for v in selected]
                ): _versions_selector(version_options),
                vol.Required(
                    CONF_LANGUAGE, default=self._language
                ): _language_selector(),
            }
        )

        return self.async_show_form(
            step_id="init", data_schema=schema, errors=errors
        )
