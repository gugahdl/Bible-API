"""Constants for the Bible Verse of the Day integration."""
from __future__ import annotations

from datetime import timedelta

# Renamed from "youversion" in v3.0.0 -- this is an independent, unofficial
# client of a third-party Bible API and should not be named after that
# company. Renaming this changes the integration's identity in Home
# Assistant: existing config entries under the old domain will not carry
# over automatically (see the upgrade notes in the README).
DOMAIN = "verse_of_the_day"
PLATFORMS = ["sensor"]

# Config-entry data keys
CONF_APP_KEY = "app_key"
CONF_LANGUAGE = "language"

# Config-entry OPTIONS keys: one entry -- one App Key -- can track several
# Bible versions at once (each gets its own device and sensor).
# CONF_VERSIONS is the list of tracked ids; CONF_VERSION_NAMES maps each id
# (as a string) to its short display label (e.g. "NVI").
CONF_VERSIONS = "versions"
CONF_VERSION_NAMES = "version_names"

# Name of the multi-select field in the config/options forms.
CONF_VERSION = "version"

# Default Bible version id. 129 = "Nova Versão Internacional – Português".
# Always overridden by the user's selection in the config flow.
DEFAULT_VERSION_ID = 129

# Value sent in the repeated language_ranges[] query parameter of /bibles.
# Accepts ISO-639 codes (e.g. "por", "eng", "spa"); the selector allows a
# custom value for anything not listed.
DEFAULT_LANGUAGE_RANGE = "por"

# How often the coordinator wakes up. The verse only changes once a day, so
# a wake-up that already has today's verse makes no API call at all -- this
# interval only matters for retrying after a failed fetch. A separate
# listener refreshes right after midnight (see __init__.py).
DEFAULT_UPDATE_INTERVAL = timedelta(hours=1)

# Offered in the language selector. Keys are the codes passed to the API.
COMMON_LANGUAGES: dict[str, str] = {
    "eng": "English",
    "por": "Português",
    "spa": "Español",
    "fra": "Français",
    "deu": "Deutsch",
    "ita": "Italiano",
    "nld": "Nederlands",
    "pol": "Polski",
    "rus": "Русский",
    "ukr": "Українська",
    "tur": "Türkçe",
    "ara": "العربية",
    "zho": "中文",
    "jpn": "日本語",
    "kor": "한국어",
}
