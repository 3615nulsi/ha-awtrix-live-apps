"""Display options: AWTRIX custom app keys set from a form.

Apps in both modes can carry display options (how long the app stays, an
effect behind the text, scrolling, text style…). They are applied to every
page as defaults: a key the template sets itself always wins.

Each option is an AWTRIX 3 key, checked and bounded here; only options that
differ from the firmware's default are stored.

Kept free of Home Assistant imports so it can be tested in isolation.
"""

from __future__ import annotations

from collections.abc import Mapping
import math
import re
from typing import Any, Final

# Key of the display options in an app's stored data.
CONF_DISPLAY: Final = "display"

EFFECTS: Final = (
    "BrickBreaker",
    "Checkerboard",
    "ColorWaves",
    "Fade",
    "Fireworks",
    "LookingEyes",
    "Matrix",
    "MovingLine",
    "Pacifica",
    "PingPong",
    "Plasma",
    "PlasmaCloud",
    "Radar",
    "Ripple",
    "Snake",
    "SwirlIn",
    "SwirlOut",
    "TheaterChase",
    "TwinklingStars",
)
PALETTES: Final = (
    "Cloud",
    "Lava",
    "Ocean",
    "Forest",
    "Stripe",
    "Party",
    "Heat",
    "Rainbow",
)
OVERLAYS: Final = ("clear", "snow", "rain", "drizzle", "storm", "thunder", "frost")

# Effects and palettes added to the firmware later, or palette files stored on
# the clock, are accepted by name.
NAME_RE: Final = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
HEX_COLOR_RE: Final = re.compile(r"^#[0-9A-Fa-f]{6}$")


class InvalidDisplayError(ValueError):
    """A display option that cannot be accepted."""

    def __init__(self, field: str, key: str) -> None:
        """Remember which option failed and why."""
        super().__init__(f"{field}: {key}")
        self.field = field
        self.key = key


def _int(data: Mapping[str, Any], key: str, low: int, high: int) -> int | None:
    value = data.get(key)
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise InvalidDisplayError(key, "invalid_value")
    try:
        number = float(value)
    except (TypeError, ValueError) as err:
        raise InvalidDisplayError(key, "invalid_value") from err
    if not math.isfinite(number):
        raise InvalidDisplayError(key, "invalid_value")
    return int(max(low, min(high, round(number))))


def _bool(data: Mapping[str, Any], key: str) -> bool | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise InvalidDisplayError(key, "invalid_value")
    return value


def _choice(data: Mapping[str, Any], key: str, choices: tuple[int, ...]) -> int | None:
    value = data.get(key)
    if value is None or value == "":
        return None
    if isinstance(value, bool) or value not in choices:
        raise InvalidDisplayError(key, "invalid_value")
    return int(value)


def _color(data: Mapping[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None or value == "":
        return None
    if isinstance(value, str) and HEX_COLOR_RE.fullmatch(value):
        return value.upper()
    if (
        isinstance(value, (list, tuple))
        and len(value) == 3
        and all(isinstance(c, int) and not isinstance(c, bool) for c in value)
        and all(0 <= c <= 255 for c in value)
    ):
        return "#{:02X}{:02X}{:02X}".format(*value)
    raise InvalidDisplayError(key, "invalid_color")


def _name(data: Mapping[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None or value == "":
        return None
    if not isinstance(value, str) or not NAME_RE.fullmatch(value):
        raise InvalidDisplayError(key, "invalid_value")
    return value


def _effect_settings(data: Mapping[str, Any]) -> dict[str, Any] | None:
    value = data.get("effectSettings")
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise InvalidDisplayError("effectSettings", "invalid_value")
    clean: dict[str, Any] = {}
    if (speed := _int(value, "speed", 1, 20)) is not None:
        clean["speed"] = speed
    if (palette := _name(value, "palette")) is not None:
        clean["palette"] = palette
    if (blend := _bool(value, "blend")) is not None:
        clean["blend"] = blend
    return clean or None


def normalize_display(data: Any) -> dict[str, Any]:
    """Return the display options worth storing, or raise InvalidDisplayError.

    Unknown keys are dropped. Values equal to the firmware's default are
    dropped too, so that an app only carries what was actually changed.
    """
    if data is None:
        return {}
    if not isinstance(data, Mapping):
        raise InvalidDisplayError(CONF_DISPLAY, "invalid_value")

    clean: dict[str, Any] = {}

    def keep(key: str, value: Any, default: Any = None) -> None:
        if value is not None and value != default:
            clean[key] = value

    # How long the app stays, and how many times its text scrolls.
    keep("duration", _int(data, "duration", 1, 3600))
    keep("repeat", _int(data, "repeat", -1, 100), -1)

    # Text placement and scrolling.
    keep("textCase", _choice(data, "textCase", (0, 1, 2)), 0)
    keep("topText", _bool(data, "topText"), False)
    keep("textOffset", _int(data, "textOffset", -32, 32), 0)
    keep("center", _bool(data, "center"), True)
    keep("noScroll", _bool(data, "noScroll"), False)
    keep("scrollSpeed", _int(data, "scrollSpeed", 10, 500), 100)
    keep("pushIcon", _choice(data, "pushIcon", (0, 1, 2)), 0)

    # Text style: these replace each other on the clock, so one at most.
    styles = {
        "rainbow": _bool(data, "rainbow") or None,
        "gradient": _gradient(data),
        "blinkText": _int(data, "blinkText", 50, 60000),
        "fadeText": _int(data, "fadeText", 50, 60000),
    }
    chosen = [key for key, value in styles.items() if value is not None]
    if len(chosen) > 1:
        raise InvalidDisplayError(chosen[1], "text_style_conflict")
    for key in chosen:
        clean[key] = styles[key]

    # Behind the text.
    keep("background", _color(data, "background"))
    effect = _name(data, "effect")
    if effect is not None:
        clean["effect"] = effect
        keep("effectSettings", _effect_settings(data))
    overlay = data.get("overlay")
    if overlay not in (None, ""):
        if overlay not in OVERLAYS:
            raise InvalidDisplayError("overlay", "invalid_value")
        clean["overlay"] = overlay

    # What the clock does with the app.
    keep("lifetimeMode", _choice(data, "lifetimeMode", (0, 1)), 0)
    keep("save", _bool(data, "save"), False)
    return clean


def _gradient(data: Mapping[str, Any]) -> list[str] | None:
    value = data.get("gradient")
    if value is None or value == "":
        return None
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise InvalidDisplayError("gradient", "invalid_color")
    colors = [_color({"gradient": c}, "gradient") for c in value]
    if None in colors:
        raise InvalidDisplayError("gradient", "invalid_color")
    return colors


def apply_display(
    pages: list[dict[str, Any]], display: Mapping[str, Any] | None
) -> list[dict[str, Any]]:
    """Return the pages with the display options added where not already set."""
    if not display:
        return pages
    return [{**display, **page} for page in pages]
