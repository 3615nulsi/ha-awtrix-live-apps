"""Constants for Awtrix Studio."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "awtrix_studio"

# Clock (config entry) settings
CONF_FIRMWARE: Final = "firmware"
CONF_PREFIX: Final = "prefix"

FIRMWARE_AWTRIX3: Final = "awtrix3"
DEFAULT_PREFIX: Final = "awtrix"

# App (config subentry) settings
SUBENTRY_TYPE_APP: Final = "app"

CONF_APP_NAME: Final = "app_name"
CONF_TEMPLATE: Final = "template"
CONF_PAGE_INTERVAL: Final = "page_interval"
CONF_CYCLE_ONLY_ON_SCREEN: Final = "cycle_only_on_screen"
CONF_HIDE_WHEN_EMPTY: Final = "hide_when_empty"
CONF_LIFETIME: Final = "lifetime"

DEFAULT_PAGE_INTERVAL: Final = 1.5
DEFAULT_CYCLE_ONLY_ON_SCREEN: Final = True
DEFAULT_HIDE_WHEN_EMPTY: Final = True
DEFAULT_LIFETIME: Final = 0

MIN_PAGE_INTERVAL: Final = 0.5
MAX_PAGE_INTERVAL: Final = 60.0
MAX_LIFETIME: Final = 86400

# AWTRIX strips spaces from app names; keep names to a safe, topic-friendly set.
APP_NAME_PATTERN: Final = r"^[A-Za-z0-9_-]{1,32}$"

# Minimum delay between two publications triggered by data changes, per app.
# Page cycling has its own pace and is not throttled.
DATA_CHANGE_COOLDOWN: Final = 1.0

SERVICE_REFRESH: Final = "refresh"
