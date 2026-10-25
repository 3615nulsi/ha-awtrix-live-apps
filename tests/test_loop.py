"""Tests for the app loop order."""

from __future__ import annotations

from custom_components.awtrix_studio.loop import (
    clean_order,
    desired_loop,
    parse_loop,
)


def test_parse_loop() -> None:
    """The loop comes as name → position."""
    assert parse_loop('{"Date": 1, "Time": 0, "tram": 2}') == ["Time", "Date", "tram"]
    assert parse_loop('{"Time": 0, "": 1, "x": true}') == ["Time"]
    assert parse_loop("[]") is None
    assert parse_loop("nope") is None


def test_clean_order() -> None:
    """Duplicates, non-strings and control characters are dropped."""
    assert clean_order(["a", "b", "a", 3, "c\n", ""]) == ["a", "b"]
    assert clean_order("abc") == []


def test_desired_loop_follows_the_order() -> None:
    """Apps are rearranged; missing ones are skipped."""
    assert desired_loop(
        ["Time", "Date", "tram", "co2"], ["co2", "tram", "Time", "Date", "gone"]
    ) == [
        "co2",
        "tram",
        "Time",
        "Date",
    ]


def test_desired_loop_keeps_every_app() -> None:
    """Apps the order does not know stay after the app they follow."""
    current = ["new", "Time", "Date", "other", "tram"]
    wanted = desired_loop(current, ["tram", "Date", "Time"])
    assert wanted == ["new", "tram", "Date", "other", "Time"]
    assert sorted(wanted) == sorted(current)
    assert desired_loop(current, []) == current
