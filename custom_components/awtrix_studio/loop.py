"""The order of the clock's app loop.

The user arranges the whole loop (built-in apps, Awtrix Studio apps and apps
pushed by anything else) and the order is kept as a list of app names. AWTRIX
appends an app at the end of the loop whenever it (re)appears, so the order is
checked again and restored when needed.

AWTRIX drops from the loop every app missing from a reorder request, and an app
dropped that way does not come back when it is pushed again. A request must
therefore always name every app currently in the loop: `desired_loop` never
leaves one out.

Kept free of Home Assistant imports so it can be tested in isolation.
"""

from __future__ import annotations

from collections.abc import Sequence
import json
from typing import Any, Final

MAX_LOOP: Final = 64
MAX_APP_NAME: Final = 64


def valid_name(value: Any) -> bool:
    """Return True for a name that can be sent back to the clock."""
    return (
        isinstance(value, str)
        and 0 < len(value) <= MAX_APP_NAME
        and value.isprintable()
    )


def parse_loop(payload: str) -> list[str] | None:
    """Return the app names of a loop message, in loop order.

    AWTRIX 3 sends an object mapping each app name to its position.
    """
    try:
        data = json.loads(payload)
    except ValueError:
        return None
    if not isinstance(data, dict) or len(data) > MAX_LOOP:
        return None
    positions = [
        (position, name)
        for name, position in data.items()
        if valid_name(name)
        and isinstance(position, int)
        and not isinstance(position, bool)
    ]
    return [name for _position, name in sorted(positions)]


def clean_order(order: Any) -> list[str]:
    """Return a stored or submitted order without duplicates or bad names."""
    if not isinstance(order, (list, tuple)):
        return []
    seen: set[str] = set()
    clean: list[str] = []
    for name in order[:MAX_LOOP]:
        if valid_name(name) and name not in seen:
            seen.add(name)
            clean.append(name)
    return clean


def desired_loop(
    current: Sequence[str], order: Sequence[str], *, keep_absent: bool = False
) -> list[str]:
    """Return the loop rearranged to follow `order`.

    Apps of the order that are not in the loop (hidden, removed) are skipped,
    or kept in their place with `keep_absent` (for a clock that reserves a
    place for apps that come later). Apps in the loop that the order does not
    know keep their place after the app they currently follow.
    """
    present = set(current) | (set(order) if keep_absent else set())
    result = [name for name in order if name in present]
    placed = set(result)
    for index, name in enumerate(current):
        if name in placed:
            continue
        # Insert after the closest app that precedes it in the current loop.
        position = 0
        for before in reversed(current[:index]):
            if before in placed:
                position = result.index(before) + 1
                break
        result.insert(position, name)
        placed.add(name)
    return result
