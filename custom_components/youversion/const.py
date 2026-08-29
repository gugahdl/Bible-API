"""Constants for the YouVersion Bible API integration."""
from __future__ import annotations

from datetime import timedelta

DOMAIN = "youversion"
PLATFORMS = ["sensor"]

# Config-entry data / options keys
CONF_APP_KEY = "app_key"
CONF_VERSION = "version"
CONF_LANGUAGE = "language"

# YouVersion Platform API -- https://developers.youversion.com
# (the old developers.youversionapi.com/1.0 host was shut down in 2026).
API_BASE_URL = "https://api.youversion.com/v1"
API_KEY_HEADER = "X-YVP-App-Key"
API_USER_AGENT = "HomeAssistant-YouVersion"

# Default Bible version id. 129 = "Nova Versão Internacional – Português".
# Always overridden by the user's selection in the config flow.
DEFAULT_VERSION_ID = 129

# Value sent in the repeated language_ranges[] query parameter of /bibles.
# Accepts ISO-639 codes (e.g. "por", "eng", "spa"); the selector allows a
# custom value for anything not listed.
DEFAULT_LANGUAGE_RANGE = "por"

DEFAULT_UPDATE_INTERVAL = timedelta(hours=12)

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
