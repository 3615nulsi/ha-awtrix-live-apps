"""Color gradients for simple mode: "the color follows the value".

A gradient is a list of stops, each a value and a color, with strictly
increasing values. Below the first stop the color is the first stop's, above
the last one it is the last stop's, and in between colors are interpolated.

Presets are color sequences spread evenly between a minimum and a maximum;
a custom gradient lists its stops explicitly.

Kept free of Home Assistant imports so it can be tested in isolation. The
panel has a copy of the presets in `frontend/gradients.js`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from itertools import pairwise
import math
from typing import Any, Final

from .const import (
    CONF_GRADIENT,
    CONF_GRADIENT_MAX,
    CONF_GRADIENT_MIN,
    CONF_GRADIENT_STOPS,
    GRADIENT_CUSTOM,
)

GREEN: Final = (0, 220, 0)
YELLOW: Final = (255, 200, 0)
ORANGE: Final = (255, 110, 0)
RED: Final = (255, 0, 0)
BLUE: Final = (0, 110, 255)
WHITE: Final = (255, 255, 255)

# Colors chosen to stay vivid on LEDs: going from green to red through yellow
# avoids the muddy khaki of a direct mix.
PRESETS: Final[dict[str, tuple[tuple[int, int, int], ...]]] = {
    "high_bad": (GREEN, YELLOW, RED),
    "low_bad": (RED, YELLOW, GREEN),
    "middle_good": (RED, YELLOW, GREEN, YELLOW, RED),
    "cold_hot": (BLUE, WHITE, ORANGE, RED),
}
GRADIENTS: Final = (*PRESETS, GRADIENT_CUSTOM)

MIN_STOPS: Final = 2
MAX_STOPS: Final = 5
MAX_ABS_VALUE: Final = 1e9

Stop = tuple[float, tuple[int, int, int]]


class InvalidGradientError(ValueError):
    """A gradient that cannot be used, with the field and error key to show."""

    def __init__(self, field: str, key: str) -> None:
        """Remember which field failed and why."""
        super().__init__(f"{field}: {key}")
        self.field = field
        self.key = key


def _value(value: Any, field: str) -> float:
    if isinstance(value, bool) or value is None or value == "":
        raise InvalidGradientError(field, "gradient_range_required")
    try:
        number = float(value)
    except (TypeError, ValueError) as err:
        raise InvalidGradientError(field, "invalid_value") from err
    if not math.isfinite(number) or abs(number) > MAX_ABS_VALUE:
        raise InvalidGradientError(field, "invalid_value")
    return number


def _rgb(value: Any, field: str) -> tuple[int, int, int]:
    if isinstance(value, str) and len(value) == 7 and value[0] == "#":
        try:
            return (int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16))
        except ValueError as err:
            raise InvalidGradientError(field, "invalid_color") from err
    if (
        isinstance(value, (list, tuple))
        and len(value) == 3
        and all(isinstance(c, int) and not isinstance(c, bool) for c in value)
        and all(0 <= c <= 255 for c in value)
    ):
        return (value[0], value[1], value[2])
    raise InvalidGradientError(field, "invalid_color")


def preset_stops(name: str, low: float, high: float) -> list[Stop]:
    """Spread a preset's colors evenly between low and high."""
    colors = PRESETS[name]
    step = (high - low) / (len(colors) - 1)
    return [(round(low + step * i, 6), color) for i, color in enumerate(colors)]


def resolve_stops(options: Mapping[str, Any]) -> list[Stop]:
    """Return the stops described by simple-mode options, or raise.

    Everything is checked: these values end up in a generated template.
    """
    name = options.get(CONF_GRADIENT)
    if name == GRADIENT_CUSTOM:
        raw = options.get(CONF_GRADIENT_STOPS)
        if not isinstance(raw, (list, tuple)) or not (
            MIN_STOPS <= len(raw) <= MAX_STOPS
        ):
            raise InvalidGradientError(CONF_GRADIENT_STOPS, "invalid_stops")
        stops: list[Stop] = []
        for stop in raw:
            if not isinstance(stop, Mapping):
                raise InvalidGradientError(CONF_GRADIENT_STOPS, "invalid_stops")
            stops.append(
                (
                    _value(stop.get("value"), CONF_GRADIENT_STOPS),
                    _rgb(stop.get("color"), CONF_GRADIENT_STOPS),
                )
            )
        if any(b[0] <= a[0] for a, b in pairwise(stops)):
            raise InvalidGradientError(CONF_GRADIENT_STOPS, "stops_not_increasing")
        return stops

    if name not in PRESETS:
        raise InvalidGradientError(CONF_GRADIENT, "invalid_value")
    low = _value(options.get(CONF_GRADIENT_MIN), CONF_GRADIENT_MIN)
    high = _value(options.get(CONF_GRADIENT_MAX), CONF_GRADIENT_MAX)
    if high <= low:
        raise InvalidGradientError(CONF_GRADIENT_MAX, "invalid_range")
    stops = preset_stops(name, low, high)
    if any(b[0] <= a[0] for a, b in pairwise(stops)):
        raise InvalidGradientError(CONF_GRADIENT_MAX, "invalid_range")
    return stops


def stops_to_data(stops: Sequence[Stop]) -> list[dict[str, Any]]:
    """Stops in the form they are stored in."""
    return [{"value": value, "color": list(color)} for value, color in stops]


def color_at(stops: Sequence[Stop], value: float) -> tuple[int, int, int]:
    """The color for a value; mirrors the generated template (used by tests)."""
    color = stops[0][1]
    for (low, low_color), (high, high_color) in pairwise(stops):
        if value > low:
            ratio = min((value - low) / (high - low), 1)
            color = tuple(  # type: ignore[assignment]
                round(a + (b - a) * ratio)
                for a, b in zip(low_color, high_color, strict=True)
            )
    return color


def _literal(number: float) -> str:
    """A finite number written as a Jinja literal."""
    return repr(round(float(number), 6))


def jinja_lines(stops: Sequence[Stop], number: str = "num") -> list[str]:
    """Template lines setting `color` (an RGB list) from the variable `number`.

    `number` must be a variable already set to a float.
    """
    literal = ", ".join(
        f"[{_literal(value)}, [{color[0]}, {color[1]}, {color[2]}]]"
        for value, color in stops
    )
    channel = "(a[1][{i}] + (b[1][{i}] - a[1][{i}]) * t) | round | int"
    return [
        "{#- Color follows the value: [value, [red, green, blue]] -#}",
        f"{{%- set stops = [{literal}] -%}}",
        "{%- set ns = namespace(color=stops[0][1]) -%}",
        "{%- for a in stops[:-1] -%}",
        "{%- set b = stops[loop.index] -%}",
        f"{{%- if {number} > a[0] -%}}",
        f"{{%- set t = [({number} - a[0]) / (b[0] - a[0]), 1] | min -%}}",
        "{%- set ns.color = ["
        + ", ".join(channel.format(i=i) for i in range(3))
        + "] -%}",
        "{%- endif -%}",
        "{%- endfor -%}",
        "{%- set color = ns.color -%}",
    ]
