"""Tests for display options."""

from __future__ import annotations

import pytest

from custom_components.awtrix_studio.display import (
    InvalidDisplayError,
    apply_display,
    ng_display,
    normalize_display,
)


def test_only_changed_options_are_kept() -> None:
    """Defaults, unknown keys and empty values are dropped."""
    assert normalize_display(None) == {}
    assert (
        normalize_display(
            {
                "duration": "",
                "repeat": -1,
                "center": True,
                "topText": False,
                "scrollSpeed": 100,
                "textCase": 0,
                "evil": "<script>",
            }
        )
        == {}
    )


def test_values_are_typed_and_bounded() -> None:
    """Numbers are clamped, colors normalized, names checked."""
    assert normalize_display(
        {
            "duration": "12",
            "repeat": 500,
            "scrollSpeed": 2,
            "textOffset": -99,
            "center": False,
            "noScroll": True,
            "textCase": 1,
            "pushIcon": 2,
            "background": [0, 16, 255],
            "effect": "Plasma",
            "effectSettings": {"speed": 99, "palette": "Ocean", "blend": False},
            "overlay": "snow",
            "lifetimeMode": 1,
            "save": True,
        }
    ) == {
        "duration": 12,
        "repeat": 100,
        "scrollSpeed": 10,
        "textOffset": -32,
        "center": False,
        "noScroll": True,
        "textCase": 1,
        "pushIcon": 2,
        "background": "#0010FF",
        "effect": "Plasma",
        "effectSettings": {"speed": 20, "palette": "Ocean", "blend": False},
        "overlay": "snow",
        "lifetimeMode": 1,
        "save": True,
    }


def test_effect_settings_need_an_effect() -> None:
    """Without an effect, its settings are meaningless and dropped."""
    assert normalize_display({"effectSettings": {"speed": 3}}) == {}
    assert normalize_display({"effect": "Matrix", "effectSettings": {}}) == {
        "effect": "Matrix"
    }


@pytest.mark.parametrize(
    ("data", "field", "key"),
    [
        ({"duration": True}, "duration", "invalid_value"),
        ({"duration": "nan"}, "duration", "invalid_value"),
        ({"textCase": 3}, "textCase", "invalid_value"),
        ({"center": "yes"}, "center", "invalid_value"),
        ({"background": "red"}, "background", "invalid_color"),
        ({"effect": "{{ 1 }}"}, "effect", "invalid_value"),
        (
            {"effect": "Fade", "effectSettings": {"palette": "a/b"}},
            "palette",
            "invalid_value",
        ),
        ({"overlay": "lava"}, "overlay", "invalid_value"),
        ({"gradient": ["#FF0000"]}, "gradient", "invalid_color"),
        ({"gradient": ["#FF0000", "blue"]}, "gradient", "invalid_color"),
        ({"rainbow": True, "blinkText": 500}, "blinkText", "text_style_conflict"),
        ("duration", "display", "invalid_value"),
    ],
)
def test_invalid_options(data: object, field: str, key: str) -> None:
    """Bad values are refused with the field at fault."""
    with pytest.raises(InvalidDisplayError) as err:
        normalize_display(data)
    assert (err.value.field, err.value.key) == (field, key)


def test_text_styles() -> None:
    """One text style is kept as is."""
    assert normalize_display({"rainbow": True}) == {"rainbow": True}
    assert normalize_display({"rainbow": False, "fadeText": 10}) == {"fadeText": 50}
    assert normalize_display({"gradient": ["#ff0000", [0, 0, 255]]}) == {
        "gradient": ["#FF0000", "#0000FF"]
    }


def test_apply_display_never_overrides_the_page() -> None:
    """Options are defaults: what the template sets wins."""
    pages = [{"text": "a"}, {"text": "b", "duration": 3}]
    assert apply_display(pages, {}) is pages
    assert apply_display(pages, {"duration": 10, "effect": "Fade"}) == [
        {"duration": 10, "effect": "Fade", "text": "a"},
        {"duration": 3, "effect": "Fade", "text": "b"},
    ]


def test_ng_drops_what_it_lacks() -> None:
    """NG has no topText, save or "clear" overlay; its effect speed is a factor."""
    assert normalize_display(
        {
            "topText": True,
            "save": True,
            "effect": "Plasma",
            "effectSettings": {"speed": 0.45, "palette": "Lava"},
        },
        "awtrix_ng",
    ) == {"effect": "Plasma", "effectSettings": {"speed": 0.5, "palette": "Lava"}}
    assert normalize_display(
        {"effect": "Fade", "effectSettings": {"speed": 1}}, "awtrix_ng"
    ) == {"effect": "Fade"}
    with pytest.raises(InvalidDisplayError):
        normalize_display({"overlay": "clear"}, "awtrix_ng")


def test_ng_keys() -> None:
    """Every option finds its NG key."""
    assert ng_display(
        {
            "duration": 8,
            "repeat": 2,
            "textCase": 2,
            "textOffset": 3,
            "center": False,
            "noScroll": True,
            "scrollSpeed": 50,
            "pushIcon": 1,
            "fadeText": 400,
            "background": "#102030",
            "effect": "Plasma",
            "effectSettings": {"speed": 0.5, "palette": "Lava", "blend": False},
            "overlay": "snow",
            "lifetimeMode": 1,
        }
    ) == {
        "durationMs": 8000,
        "repeat": 2,
        "textCase": "asTyped",
        "textOffsetX": 3,
        "textAlign": "start",
        "scroll": {"mode": "static", "speed": 50},
        "iconMode": "pushOnce",
        "textFadeMs": 400,
        "backgroundColor": "#102030",
        "effect": "Plasma",
        "effectSpeed": 0.5,
        "paletteBlend": False,
        "palette": "Lava",
        "overlay": "snow",
        "lifetimeExpiry": "mark",
    }
    assert ng_display({"repeat": 0, "overlay": "clear"}) == {}


def test_ng_text_palette_wins() -> None:
    """A rainbow or gradient text paints the text from the app's one palette."""
    pages = [{"text": "a", "textColor": "#FFFFFF"}, {"text": "b", "palette": "Ocean"}]
    assert apply_display(
        pages,
        {"rainbow": True, "effect": "Plasma", "effectSettings": {"palette": "Lava"}},
        "awtrix_ng",
    ) == [
        {"effect": "Plasma", "palette": "Rainbow", "text": "a", "textColor": "palette"},
        {"effect": "Plasma", "palette": "Ocean", "text": "b"},
    ]
    assert apply_display(
        pages[:1], {"gradient": ["#FF0000", "#0000FF"]}, "awtrix_ng"
    ) == [{"palette": ["#FF0000", "#0000FF"], "text": "a", "textColor": "palette"}]
