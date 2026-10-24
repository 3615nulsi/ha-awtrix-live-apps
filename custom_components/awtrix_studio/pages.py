"""Turn a rendered template into AWTRIX pages.

Kept free of Home Assistant imports so it can be tested in isolation.
"""

from __future__ import annotations

import json
from typing import Any


class InvalidPagesError(ValueError):
    """The template did not render to a JSON object or a list of objects."""


def parse_pages(result: Any) -> list[dict[str, Any]]:
    """Return the non-empty pages described by a template result.

    Home Assistant may hand us either a native Python value (when the output
    looks like a Python literal) or the raw string (for JSON using `true`,
    `false` or `null`). Both are accepted:

    - an object is a single page;
    - a list of objects is several pages;
    - empty objects, an empty list, an empty string or `None` mean "no page".
    """
    if result is None:
        return []

    if isinstance(result, str):
        text = result.strip()
        if not text:
            return []
        try:
            result = json.loads(text)
        except ValueError as err:
            raise InvalidPagesError(f"not valid JSON: {err}") from err

    if isinstance(result, dict):
        return [result] if result else []

    if isinstance(result, list):
        pages: list[dict[str, Any]] = []
        for index, item in enumerate(result, start=1):
            if not isinstance(item, dict):
                raise InvalidPagesError(
                    f"page {index} is a {type(item).__name__}, expected an object"
                )
            if item:
                pages.append(item)
        return pages

    raise InvalidPagesError(
        f"got a {type(result).__name__}, expected an object or a list of objects"
    )


def serialize_page(page: dict[str, Any]) -> str:
    """Serialize a page compactly, keeping non-ASCII characters readable."""
    return json.dumps(page, ensure_ascii=False, separators=(",", ":"))
