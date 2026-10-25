"""Tests for color gradients ("the color follows the value")."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.template import Template
import pytest

from custom_components.awtrix_studio.gradients import (
    InvalidGradientError,
    color_at,
    jinja_lines,
    resolve_stops,
)
from custom_components.awtrix_studio.pages import parse_pages
from custom_components.awtrix_studio.templates import (
    InvalidSimpleOptionsError,
    build_app_template,
    build_indicator_template,
)

CUSTOM_STOPS = [
    {"value": -2, "color": [0, 150, 255]},
    {"value": 0, "color": "#00FF00"},
    {"value": 0.5, "color": [255, 255, 0]},
    {"value": 3, "color": [255, 0, 0]},
]


def render(hass: HomeAssistant, template: str) -> list[dict[str, Any]]:
    """Render like the engine does and return the pages."""
    return parse_pages(Template(template, hass).async_render(parse_result=True))


def test_presets_are_spread_between_min_and_max() -> None:
    """A preset's colors are evenly spread over the range."""
    stops = resolve_stops(
        {"gradient": "high_bad", "gradient_min": 400, "gradient_max": 1500}
    )
    assert [value for value, _ in stops] == [400, 950, 1500]
    assert color_at(stops, 0) == (0, 220, 0)
    assert color_at(stops, 950) == (255, 200, 0)
    assert color_at(stops, 99999) == (255, 0, 0)
    assert color_at(stops, 675) == (128, 210, 0)


def test_custom_stops() -> None:
    """Custom stops accept RGB lists and hex strings."""
    stops = resolve_stops({"gradient": "custom", "gradient_stops": CUSTOM_STOPS})
    assert stops[1] == (0.0, (0, 255, 0))
    assert color_at(stops, -1) == (0, 202, 128)


@pytest.mark.parametrize(
    ("options", "field", "key"),
    [
        ({"gradient": "evil"}, "gradient", "invalid_value"),
        ({"gradient": "high_bad"}, "gradient_min", "gradient_range_required"),
        (
            {"gradient": "high_bad", "gradient_min": 5, "gradient_max": 5},
            "gradient_max",
            "invalid_range",
        ),
        (
            {"gradient": "high_bad", "gradient_min": "nan", "gradient_max": 5},
            "gradient_min",
            "invalid_value",
        ),
        (
            {"gradient": "high_bad", "gradient_min": 0, "gradient_max": "1e99"},
            "gradient_max",
            "invalid_value",
        ),
        (
            {"gradient": "high_bad", "gradient_min": 0, "gradient_max": True},
            "gradient_max",
            "gradient_range_required",
        ),
        ({"gradient": "custom"}, "gradient_stops", "invalid_stops"),
        (
            {"gradient": "custom", "gradient_stops": CUSTOM_STOPS[:1]},
            "gradient_stops",
            "invalid_stops",
        ),
        (
            {"gradient": "custom", "gradient_stops": CUSTOM_STOPS * 2},
            "gradient_stops",
            "invalid_stops",
        ),
        (
            {"gradient": "custom", "gradient_stops": CUSTOM_STOPS[::-1]},
            "gradient_stops",
            "stops_not_increasing",
        ),
        (
            {
                "gradient": "custom",
                "gradient_stops": [
                    {"value": 0, "color": '#FFF" }}{{ 7*7 }}'},
                    {"value": 1, "color": [1, 2, 3]},
                ],
            },
            "gradient_stops",
            "invalid_color",
        ),
        (
            {
                "gradient": "custom",
                "gradient_stops": [
                    {"value": "1 }}{{ 7*7", "color": [1, 2, 3]},
                    {"value": 2, "color": [1, 2, 3]},
                ],
            },
            "gradient_stops",
            "invalid_value",
        ),
        (
            {
                "gradient": "custom",
                "gradient_stops": [
                    {"value": 0, "color": [1, 2, 300]},
                    {"value": 1, "color": [1, 2, 3]},
                ],
            },
            "gradient_stops",
            "invalid_color",
        ),
    ],
)
def test_invalid_gradients_are_refused(
    options: dict[str, Any], field: str, key: str
) -> None:
    """Nothing unchecked reaches a template."""
    with pytest.raises(InvalidGradientError) as err:
        resolve_stops(options)
    assert (err.value.field, err.value.key) == (field, key)


async def test_template_matches_python(hass: HomeAssistant) -> None:
    """The generated Jinja interpolates exactly like color_at."""
    for options in (
        {"gradient": "middle_good", "gradient_min": 20, "gradient_max": 80},
        {"gradient": "cold_hot", "gradient_min": -5, "gradient_max": 35},
        {"gradient": "custom", "gradient_stops": CUSTOM_STOPS},
    ):
        stops = resolve_stops(options)
        source = "\n".join(
            ["{%- set num = value | float -%}", *jinja_lines(stops), "{{ color }}"]
        )
        template = Template(source, hass)
        for value in (-10, -2, -1.3, 0, 0.25, 1, 22.5, 50, 66.6, 80, 1000):
            rendered = template.async_render({"value": value}, parse_result=True)
            assert tuple(rendered) == color_at(stops, value), (options, value)


async def test_app_gradient(hass: HomeAssistant) -> None:
    """The text color follows the value; non-numbers keep the text color."""
    template = build_app_template(
        {
            "entity_id": "sensor.co2",
            "color": [10, 20, 30],
            "color_mode": "gradient",
            "gradient": "high_bad",
            "gradient_min": 400,
            "gradient_max": 1500,
            # Ignored outside steps mode.
            "threshold_1": 500,
            "color_1": [1, 1, 1],
        }
    )
    hass.states.async_set("sensor.co2", "950", {"unit_of_measurement": "ppm"})
    assert render(hass, template) == [{"text": "950 ppm", "color": [255, 200, 0]}]
    hass.states.async_set("sensor.co2", "5000", {"unit_of_measurement": "ppm"})
    assert render(hass, template)[0]["color"] == [255, 0, 0]
    hass.states.async_set("sensor.co2", "high")
    assert render(hass, template)[0]["color"] == "#0A141E"


async def test_older_apps_keep_their_thresholds(hass: HomeAssistant) -> None:
    """Items saved without a color mode keep working as before."""
    options = {"entity_id": "sensor.x", "threshold_1": 5, "color_1": [255, 0, 0]}
    hass.states.async_set("sensor.x", "6")
    assert render(hass, build_app_template(options))[0]["color"] == "#FF0000"
    fixed = {**options, "color_mode": "fixed"}
    assert render(hass, build_app_template(fixed))[0]["color"] == "#FFFFFF"


async def test_indicator_gradient(hass: HomeAssistant) -> None:
    """A solar-surplus indicator: always lit, off while unavailable."""
    template = build_indicator_template(
        {
            "entity_id": "sensor.grid",
            "color_mode": "gradient",
            "gradient": "custom",
            "gradient_stops": CUSTOM_STOPS,
            "effect": "fade",
            "effect_interval": 2000,
        }
    )
    hass.states.async_set("sensor.grid", "-2.5")
    assert render(hass, template) == [{"color": [0, 150, 255], "fade": 2000}]
    hass.states.async_set("sensor.grid", "1.75")
    assert render(hass, template) == [{"color": [255, 128, 0], "fade": 2000}]
    hass.states.async_set("sensor.grid", "unavailable")
    assert render(hass, template) == []


def test_invalid_gradient_cannot_build() -> None:
    """A broken gradient never produces a template."""
    with pytest.raises(InvalidSimpleOptionsError):
        build_app_template(
            {"entity_id": "sensor.x", "color_mode": "gradient", "gradient": "high_bad"}
        )
    with pytest.raises(InvalidSimpleOptionsError):
        build_indicator_template(
            {"entity_id": "sensor.x", "color_mode": "gradient", "gradient": "custom"}
        )
