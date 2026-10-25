"""Constants for Awtrix Studio."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "awtrix_studio"
# hass.data key of the shared LaMetric icon store.
DATA_ICONS: Final = f"{DOMAIN}_icons"

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

# How the color is chosen (apps: fixed, steps or gradient; indicators: lit in
# a state, or gradient). Missing on items created before 0.4: inferred.
CONF_COLOR_MODE: Final = "color_mode"
COLOR_FIXED: Final = "fixed"
COLOR_STEPS: Final = "steps"
COLOR_GRADIENT: Final = "gradient"
COLOR_STATE: Final = "state"
APP_COLOR_MODES: Final = (COLOR_FIXED, COLOR_STEPS, COLOR_GRADIENT)
INDICATOR_COLOR_MODES: Final = (COLOR_STATE, COLOR_GRADIENT)

CONF_GRADIENT: Final = "gradient"
CONF_GRADIENT_MIN: Final = "gradient_min"
CONF_GRADIENT_MAX: Final = "gradient_max"
CONF_GRADIENT_STOPS: Final = "gradient_stops"
GRADIENT_CUSTOM: Final = "custom"
DEFAULT_GRADIENT: Final = "high_bad"

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

# Simple mode, progress bar
CONF_PROGRESS: Final = "progress"
CONF_PROGRESS_ENTITY: Final = "progress_entity"
CONF_PROGRESS_MIN: Final = "progress_min"
CONF_PROGRESS_MAX: Final = "progress_max"
CONF_PROGRESS_COLOR: Final = "progress_color"
CONF_PROGRESS_BG: Final = "progress_bg"
DEFAULT_PROGRESS_MIN: Final = 0.0
DEFAULT_PROGRESS_MAX: Final = 100.0
DEFAULT_PROGRESS_BG: Final = [46, 46, 46]
