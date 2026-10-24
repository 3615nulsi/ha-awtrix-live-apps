"""Validation shared by the config flows and the panel.

Anything coming from a user is checked here before it is stored, rendered or
published: only known keys are kept, every value is typed and bounded, and
names that end up in MQTT topics are restricted to a safe alphabet.
"""

from __future__ import annotations

from collections.abc import Mapping
import math
import re
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import TemplateError
from homeassistant.helpers.template import Template

from .const import (
    APP_NAME_PATTERN,
    CONF_ACTIVE_STATE,
    CONF_APP_NAME,
    CONF_COLOR,
    CONF_COLOR_1,
    CONF_COLOR_2,
    CONF_CYCLE_ONLY_ON_SCREEN,
    CONF_DECIMALS,
    CONF_EFFECT,
    CONF_EFFECT_INTERVAL,
    CONF_ENTITY_ID,
    CONF_HIDE_WHEN_EMPTY,
    CONF_HIDE_WHEN_ZERO,
    CONF_ICON,
    CONF_INDICATOR,
    CONF_LABEL,
    CONF_LIFETIME,
    CONF_MODE,
    CONF_PAGE_INTERVAL,
    CONF_SHOW_UNIT,
    CONF_TEMPLATE,
    CONF_THRESHOLD_1,
    CONF_THRESHOLD_2,
    DEFAULT_ACTIVE_STATE,
    DEFAULT_COLOR,
    DEFAULT_CYCLE_ONLY_ON_SCREEN,
    DEFAULT_EFFECT_INTERVAL,
    DEFAULT_HIDE_WHEN_EMPTY,
    DEFAULT_INDICATOR_COLOR,
    DEFAULT_LIFETIME,
    DEFAULT_PAGE_INTERVAL,
    EFFECT_NONE,
    EFFECTS,
    INDICATORS,
    MAX_LIFETIME,
    MAX_PAGE_INTERVAL,
    MIN_PAGE_INTERVAL,
    MODE_SIMPLE,
    MODE_TEMPLATE,
    SUBENTRY_TYPE_APP,
    SUBENTRY_TYPE_INDICATOR,
)
from .pages import InvalidPagesError, parse_pages
from .templates import ENTITY_ID_RE, HEX_COLOR_RE

MAX_TEXT = 64
MAX_TEMPLATE = 20_000


class Invalid(Exception):
    """A value that cannot be accepted, with the error key to show."""

    def __init__(self, field: str, key: str, detail: str = "") -> None:
        """Remember which field failed and why."""
        super().__init__(f"{field}: {key} {detail}".strip())
        self.field = field
        self.key = key
        self.detail = detail


# ------------------------------------------------------------- primitives


def check_template(hass: HomeAssistant, template_str: str) -> tuple[str, str] | None:
    """Render a template once; return (error key, detail) if it fails."""
    template = Template(template_str, hass)
    try:
        template.ensure_valid()
        result = template.async_render(parse_result=True)
    except TemplateError as err:
        return "invalid_template", str(err)
    try:
        parse_pages(result)
    except InvalidPagesError as err:
        return "invalid_pages", str(err)
    return None


def _bool(data: Mapping[str, Any], key: str, default: bool) -> bool:
    value = data.get(key, default)
    return value if isinstance(value, bool) else default


def _text(data: Mapping[str, Any], key: str, default: str = "") -> str:
    value = data.get(key, default)
    if value is None:
        return default
    if not isinstance(value, str):
        raise Invalid(key, "invalid_value")
    return value.strip()[:MAX_TEXT]


def _number(data: Mapping[str, Any], key: str, low: float, high: float) -> float | None:
    value = data.get(key)
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise Invalid(key, "invalid_value")
    try:
        number = float(value)
    except (TypeError, ValueError) as err:
        raise Invalid(key, "invalid_value") from err
    if not math.isfinite(number):
        raise Invalid(key, "invalid_value")
    return max(low, min(high, number))


def _color(
    data: Mapping[str, Any], key: str, default: list[int] | None
) -> list[int] | None:
    value = data.get(key)
    if value is None or value == "":
        return default
    if isinstance(value, str) and HEX_COLOR_RE.fullmatch(value):
        return [int(value[i : i + 2], 16) for i in (1, 3, 5)]
    if (
        isinstance(value, (list, tuple))
        and len(value) == 3
        and all(isinstance(c, int) and not isinstance(c, bool) for c in value)
        and all(0 <= c <= 255 for c in value)
    ):
        return list(value)
    raise Invalid(key, "invalid_color")


def _entity(data: Mapping[str, Any]) -> str:
    value = data.get(CONF_ENTITY_ID)
    if not isinstance(value, str) or not ENTITY_ID_RE.fullmatch(value):
        raise Invalid(CONF_ENTITY_ID, "invalid_entity")
    return value


def _raw_template(data: Mapping[str, Any]) -> str:
    value = data.get(CONF_TEMPLATE)
    if not isinstance(value, str):
        raise Invalid(CONF_TEMPLATE, "invalid_template", "empty")
    if len(value) > MAX_TEMPLATE:
        raise Invalid(CONF_TEMPLATE, "invalid_template", "too long")
    return value


def _template(hass: HomeAssistant, data: Mapping[str, Any]) -> str:
    value = data.get(CONF_TEMPLATE)
    if not isinstance(value, str) or not value.strip():
        raise Invalid(CONF_TEMPLATE, "invalid_template", "empty")
    if len(value) > MAX_TEMPLATE:
        raise Invalid(CONF_TEMPLATE, "invalid_template", "too long")
    if error := check_template(hass, value):
        raise Invalid(CONF_TEMPLATE, error[0], error[1])
    return value


# --------------------------------------------------------- whole items


def _siblings(
    entry: ConfigEntry, kind: str, subentry_id: str | None
) -> list[Mapping[str, Any]]:
    return [
        subentry.data
        for sid, subentry in entry.subentries.items()
        if subentry.subentry_type == kind and sid != subentry_id
    ]


def normalize_app(
    hass: HomeAssistant,
    entry: ConfigEntry,
    data: Mapping[str, Any],
    subentry_id: str | None,
    *,
    preview: bool = False,
) -> dict[str, Any]:
    """Return clean app data, or raise Invalid.

    In preview mode the name is not required and the template is not rendered
    here (the preview renders it continuously instead).
    """
    mode = data.get(CONF_MODE)
    if mode not in (MODE_SIMPLE, MODE_TEMPLATE):
        raise Invalid(CONF_MODE, "invalid_value")

    if subentry_id is not None:
        name = entry.subentries[subentry_id].data[CONF_APP_NAME]
    elif preview:
        name = "preview"
    else:
        name = data.get(CONF_APP_NAME)
        if not isinstance(name, str) or not re.fullmatch(APP_NAME_PATTERN, name):
            raise Invalid(CONF_APP_NAME, "invalid_app_name")
        if any(
            o.get(CONF_APP_NAME) == name
            for o in _siblings(entry, SUBENTRY_TYPE_APP, None)
        ):
            raise Invalid(CONF_APP_NAME, "app_name_exists")

    if mode == MODE_SIMPLE:
        clean: dict[str, Any] = {
            CONF_MODE: MODE_SIMPLE,
            CONF_APP_NAME: name,
            CONF_ENTITY_ID: _entity(data),
            CONF_LABEL: _text(data, CONF_LABEL),
            CONF_ICON: _text(data, CONF_ICON),
            CONF_COLOR: _color(data, CONF_COLOR, list(DEFAULT_COLOR)),
            CONF_SHOW_UNIT: _bool(data, CONF_SHOW_UNIT, True),
            CONF_HIDE_WHEN_ZERO: _bool(data, CONF_HIDE_WHEN_ZERO, False),
        }
        decimals = _number(data, CONF_DECIMALS, 0, 4)
        if decimals is not None:
            clean[CONF_DECIMALS] = int(decimals)
        for threshold, color in (
            (CONF_THRESHOLD_1, CONF_COLOR_1),
            (CONF_THRESHOLD_2, CONF_COLOR_2),
        ):
            value = _number(data, threshold, -1e9, 1e9)
            if value is None:
                continue
            chosen = _color(data, color, None)
            if chosen is None:
                raise Invalid(color, "color_required")
            clean[threshold] = value
            clean[color] = chosen
        return clean

    return {
        CONF_MODE: MODE_TEMPLATE,
        CONF_APP_NAME: name,
        CONF_TEMPLATE: _raw_template(data) if preview else _template(hass, data),
        CONF_PAGE_INTERVAL: _number(
            data, CONF_PAGE_INTERVAL, MIN_PAGE_INTERVAL, MAX_PAGE_INTERVAL
        )
        or DEFAULT_PAGE_INTERVAL,
        CONF_CYCLE_ONLY_ON_SCREEN: _bool(
            data, CONF_CYCLE_ONLY_ON_SCREEN, DEFAULT_CYCLE_ONLY_ON_SCREEN
        ),
        CONF_HIDE_WHEN_EMPTY: _bool(
            data, CONF_HIDE_WHEN_EMPTY, DEFAULT_HIDE_WHEN_EMPTY
        ),
        CONF_LIFETIME: int(
            _number(data, CONF_LIFETIME, 0, MAX_LIFETIME) or DEFAULT_LIFETIME
        ),
    }


def normalize_indicator(
    hass: HomeAssistant,
    entry: ConfigEntry,
    data: Mapping[str, Any],
    subentry_id: str | None,
    *,
    preview: bool = False,
) -> dict[str, Any]:
    """Return clean indicator data, or raise Invalid."""
    mode = data.get(CONF_MODE)
    if mode not in (MODE_SIMPLE, MODE_TEMPLATE):
        raise Invalid(CONF_MODE, "invalid_value")

    if subentry_id is not None:
        number = entry.subentries[subentry_id].data[CONF_INDICATOR]
    elif preview:
        number = (
            data.get(CONF_INDICATOR) if data.get(CONF_INDICATOR) in INDICATORS else "1"
        )
    else:
        number = data.get(CONF_INDICATOR)
        if number not in INDICATORS:
            raise Invalid(CONF_INDICATOR, "invalid_value")
        if any(
            o.get(CONF_INDICATOR) == number
            for o in _siblings(entry, SUBENTRY_TYPE_INDICATOR, None)
        ):
            raise Invalid(CONF_INDICATOR, "indicator_in_use")

    if mode == MODE_SIMPLE:
        effect = data.get(CONF_EFFECT, EFFECT_NONE)
        if effect not in EFFECTS:
            raise Invalid(CONF_EFFECT, "invalid_value")
        return {
            CONF_MODE: MODE_SIMPLE,
            CONF_INDICATOR: number,
            CONF_ENTITY_ID: _entity(data),
            CONF_ACTIVE_STATE: _text(data, CONF_ACTIVE_STATE, DEFAULT_ACTIVE_STATE)
            or DEFAULT_ACTIVE_STATE,
            CONF_COLOR: _color(data, CONF_COLOR, list(DEFAULT_INDICATOR_COLOR)),
            CONF_EFFECT: effect,
            CONF_EFFECT_INTERVAL: int(
                _number(data, CONF_EFFECT_INTERVAL, 100, 10000)
                or DEFAULT_EFFECT_INTERVAL
            ),
        }
    return {
        CONF_MODE: MODE_TEMPLATE,
        CONF_INDICATOR: number,
        CONF_TEMPLATE: _raw_template(data) if preview else _template(hass, data),
    }


def normalize(
    hass: HomeAssistant,
    entry: ConfigEntry,
    kind: str,
    data: Mapping[str, Any],
    subentry_id: str | None,
    *,
    preview: bool = False,
) -> dict[str, Any]:
    """Normalize app or indicator data."""
    if kind == SUBENTRY_TYPE_INDICATOR:
        return normalize_indicator(hass, entry, data, subentry_id, preview=preview)
    return normalize_app(hass, entry, data, subentry_id, preview=preview)
