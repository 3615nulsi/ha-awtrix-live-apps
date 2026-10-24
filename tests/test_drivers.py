"""Tests for firmware drivers."""

from __future__ import annotations

import pytest

from custom_components.awtrix_studio.drivers import Awtrix3Driver, get_driver


def test_awtrix3_topics() -> None:
    """AWTRIX 3 topics follow the documented layout."""
    driver = get_driver("awtrix3", "awtrix_1f1b94")
    assert isinstance(driver, Awtrix3Driver)
    assert driver.app_topic("tram") == "awtrix_1f1b94/custom/tram"
    assert driver.current_app_topic == "awtrix_1f1b94/stats/currentApp"
    assert driver.status_topic == "awtrix_1f1b94/stats"
    assert driver.remove_payload == ""


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ('{"uptime": 120, "bat": 99}', 120.0),
        ('{"uptime": 1.5}', 1.5),
        ('{"bat": 99}', None),
        ('{"uptime": "12"}', None),
        ('{"uptime": true}', None),
        ("not json", None),
        ("[1, 2]", None),
    ],
)
def test_awtrix3_uptime(payload: str, expected: float | None) -> None:
    """Uptime is read from the stats JSON when present."""
    assert Awtrix3Driver("awtrix").parse_uptime(payload) == expected


def test_awtrix3_current_app() -> None:
    """The current app payload is the bare name."""
    driver = Awtrix3Driver("awtrix")
    assert driver.parse_current_app(" tram\n") == "tram"
    assert driver.parse_current_app("") is None


def test_awtrix3_lifetime_keeps_user_value() -> None:
    """A lifetime set in the template wins."""
    driver = Awtrix3Driver("awtrix")
    assert driver.with_lifetime({"text": "a"}, 60) == {"text": "a", "lifetime": 60}
    assert driver.with_lifetime({"lifetime": 5}, 60) == {"lifetime": 5}
