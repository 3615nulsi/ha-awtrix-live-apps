"""Constants for Awtrix Studio."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "awtrix_studio"

# Clock (config entry) settings
CONF_FIRMWARE: Final = "firmware"
CONF_PREFIX: Final = "prefix"

FIRMWARE_AWTRIX3: Final = "awtrix3"
DEFAULT_PREFIX: Final = "awtrix"

# Subentry types
SUBENTRY_TYPE_APP: Final = "app"
SUBENTRY_TYPE_INDICATOR: Final = "indicator"

# How an app or indicator is described
CONF_MODE: Final = "mode"
MODE_SIMPLE: Final = "simple"
MODE_TEMPLATE: Final = "template"

# App (config subentry) settings

CONF_APP_NAME: Final = "app_name"
CONF_TEMPLATE: Final = "template"
CONF_PAGE_INTERVAL: Final = "page_interval"
CONF_CYCLE_ONLY_ON_SCREEN: Final = "cycle_only_on_screen"
CONF_HIDE_WHEN_EMPTY: Final = "hide_when_empty"
CONF_LIFETIME: Final = "lifetime"

# Simple mode, apps
CONF_ENTITY_ID: Final = "entity_id"
CONF_LABEL: Final = "label"
CONF_ICON: Final = "icon"
CONF_COLOR: Final = "color"
CONF_DECIMALS: Final = "decimals"
CONF_SHOW_UNIT: Final = "show_unit"
CONF_HIDE_WHEN_ZERO: Final = "hide_when_zero"
CONF_THRESHOLD_1: Final = "threshold_1"
CONF_COLOR_1: Final = "color_1"
CONF_THRESHOLD_2: Final = "threshold_2"
CONF_COLOR_2: Final = "color_2"

DEFAULT_COLOR: Final = [255, 255, 255]

# Indicators
CONF_INDICATOR: Final = "indicator"
INDICATORS: Final = ("1", "2", "3")

# Simple mode, indicators
CONF_ACTIVE_STATE: Final = "active_state"
CONF_EFFECT: Final = "effect"
CONF_EFFECT_INTERVAL: Final = "effect_interval"
EFFECT_NONE: Final = "none"
EFFECT_BLINK: Final = "blink"
EFFECT_FADE: Final = "fade"
EFFECTS: Final = (EFFECT_NONE, EFFECT_BLINK, EFFECT_FADE)

DEFAULT_ACTIVE_STATE: Final = "on"
DEFAULT_INDICATOR_COLOR: Final = [255, 140, 0]
DEFAULT_EFFECT_INTERVAL: Final = 1000

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
