"""Constants for the YouVersion Bible API integration."""
from __future__ import annotations

from datetime import timedelta

DOMAIN = "youversion"
PLATFORMS = ["sensor"]

CONF_TOKEN = "token"
CONF_VERSION = "version"
CONF_LANGUAGE = "language"

DEFAULT_VERSION_ID = 1  # 1 = KJV (English). User should override for other languages.
DEFAULT_UPDATE_INTERVAL = timedelta(hours=12)

API_BASE_URL = "https://developers.youversion.com/api/1.0"
API_USER_AGENT = "HomeAssistant-YouVersion"
