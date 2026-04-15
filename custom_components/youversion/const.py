"""Constants for the YouVersion Bible API integration."""
from __future__ import annotations

from datetime import timedelta

DOMAIN = "youversion"
PLATFORMS = ["sensor"]

CONF_TOKEN = "token"
CONF_VERSION = "version"
CONF_LANGUAGE = "language"

DEFAULT_VERSION_ID = 1  # 1 = KJV (English). Overridden by user selection.
DEFAULT_UPDATE_INTERVAL = timedelta(hours=12)

API_BASE_URL = "https://developers.youversionapi.com/1.0"
API_USER_AGENT = "HomeAssistant-YouVersion"

# Common language codes offered in the selector. Users can still type
# a custom code since the selector allows free input.
COMMON_LANGUAGES: dict[str, str] = {
    "en": "English",
    "pt": "Português",
    "es": "Español",
    "fr": "Français",
    "de": "Deutsch",
    "it": "Italiano",
    "nl": "Nederlands",
    "pl": "Polski",
    "ru": "Русский",
    "uk": "Українська",
    "tr": "Türkçe",
    "ar": "العربية",
    "zh": "中文",
    "ja": "日本語",
    "ko": "한국어",
}
