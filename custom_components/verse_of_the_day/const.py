"""Constants for the Bible Verse of the Day integration."""
from __future__ import annotations

from datetime import timedelta

# Renamed from "youversion" in v3.0.0 -- this is an independent, unofficial
# client of the YouVersion Platform API and should not be named after that
# company. Renaming this changes the integration's identity in Home
# Assistant: existing config entries under the old domain will not carry
# over automatically (see MIGRATION notes in the repo).
DOMAIN = "verse_of_the_day"
PLATFORMS = ["sensor"]

# Config-entry data keys
CONF_APP_KEY = "app_key"
CONF_LANGUAGE = "language"

# Config-entry OPTIONS keys (current, since v2.2.0): one entry -- one App Key
# -- can track several Bible versions at once (each gets its own device and
# sensor). CONF_VERSIONS is the list of tracked ids; CONF_VERSION_NAMES maps
# each id (as a string) to its short display label (e.g. "NVI").
CONF_VERSIONS = "versions"
CONF_VERSION_NAMES = "version_names"

# Legacy options keys, written by versions <= 2.1.0 (one version per entry).
# Kept only so entries created before v2.2.0 keep working -- see helpers.py.
CONF_VERSION = "version"
CONF_VERSION_NAME = "version_name"

# This project fetches Bible text from the YouVersion Platform API
# (https://developers.youversion.com). It is an independent, unofficial
# client -- not created, endorsed, or affiliated with YouVersion / Life.Church.
API_BASE_URL = "https://api.youversion.com/v1"
API_KEY_HEADER = "X-YVP-App-Key"
API_USER_AGENT = "HomeAssistant-BibleVerseOfTheDay"

# Default Bible version id. 129 = "Nova Versão Internacional – Português".
# Always overridden by the user's selection in the config flow.
DEFAULT_VERSION_ID = 129

# Value sent in the repeated language_ranges[] query parameter of /bibles.
# Accepts ISO-639 codes (e.g. "por", "eng", "spa"); the selector allows a
# custom value for anything not listed.
DEFAULT_LANGUAGE_RANGE = "por"

# Kept short so a transient outage (DNS blip, etc.) self-heals within an hour
# instead of sitting "unavailable" until the next 12h poll. The API has no
# documented rate limit and this is only 3 requests/hour per tracked version.
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
