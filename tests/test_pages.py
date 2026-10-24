"""Tests for template result parsing."""

from __future__ import annotations

import pytest

from custom_components.awtrix_studio.pages import (
    InvalidPagesError,
    parse_pages,
    serialize_page,
)


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (None, []),
        ("", []),
        ("   \n", []),
        ({}, []),
        ([], []),
        ("{}", []),
        ({"text": "a"}, [{"text": "a"}]),
        ('{"text": "a", "center": true}', [{"text": "a", "center": True}]),
        ([{"text": "a"}, {}, {"text": "b"}], [{"text": "a"}, {"text": "b"}]),
        ('[{"text": "a"}, {"text": "b"}]', [{"text": "a"}, {"text": "b"}]),
    ],
)
def test_parse_pages(result: object, expected: list[dict[str, object]]) -> None:
    """Objects are one page, lists are several, empty means no page."""
    assert parse_pages(result) == expected


@pytest.mark.parametrize(
    "result",
    ["not json", "{text: 1}", 42, "42", [{"text": "a"}, "b"], True],
)
def test_parse_pages_invalid(result: object) -> None:
    """Anything else is rejected."""
    with pytest.raises(InvalidPagesError):
        parse_pages(result)


def test_serialize_page_is_compact_and_keeps_accents() -> None:
    """Payloads are small and readable."""
    assert serialize_page({"text": "Quai", "c": "é"}) == '{"text":"Quai","c":"é"}'
