"""Firmware drivers.

A driver only knows how to *transport* apps for a given firmware: which topic
to publish to, how to remove an app, how to tell which app is on screen and how
to detect a reboot. The app *content* is the firmware's native JSON, written by
the user in the template, and is never translated.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import ipaddress
import json
from typing import Any

from .const import FIRMWARE_AWTRIX3

SCREEN_PIXELS = 32 * 8


class FirmwareDriver(ABC):
    """Transport details for one firmware family."""

    firmware: str

    def __init__(self, prefix: str) -> None:
        """Initialize the driver for a clock identified by its MQTT prefix."""
        self.prefix = prefix

    @abstractmethod
    def app_topic(self, app_name: str) -> str:
        """Return the topic used to publish an app."""

    @abstractmethod
    def indicator_topic(self, number: str) -> str:
        """Return the topic of a colored indicator (1, 2 or 3)."""

    @property
    @abstractmethod
    def remove_payload(self) -> str:
        """Return the payload that removes an app from the clock."""

    @property
    @abstractmethod
    def current_app_topic(self) -> str | None:
        """Return the topic announcing the app on screen, if any."""

    @property
    @abstractmethod
    def status_topic(self) -> str | None:
        """Return the topic carrying periodic device stats, if any."""

    @abstractmethod
    def parse_current_app(self, payload: str) -> str | None:
        """Extract the name of the app on screen from a message."""

    @abstractmethod
    def parse_uptime(self, payload: str) -> float | None:
        """Extract the device uptime in seconds from a status message."""

    @abstractmethod
    def with_lifetime(self, page: dict[str, Any], seconds: int) -> dict[str, Any]:
        """Return the page with the firmware's lifetime field set.

        A lifetime explicitly set by the user in the template is kept.
        """

    # Panel helpers: the screen mirror and navigation. A firmware that cannot
    # do something returns None and the panel hides the matching feature.

    @property
    def screen_topic(self) -> str | None:
        """Return the topic on which the clock sends its screen content."""
        return None

    def screen_request(self) -> tuple[str, str] | None:
        """Return the (topic, payload) asking the clock for its screen."""
        return None

    def parse_screen(self, payload: str) -> list[int] | None:
        """Return the screen as 256 colors (0xRRGGBB), row by row."""
        return None

    def show_app(self, app_name: str) -> tuple[str, str] | None:
        """Return the (topic, payload) bringing an app on screen now."""
        return None

    # Icon files: firmware that can store icons and play animated ones.

    def parse_address(self, payload: str) -> str | None:
        """Return the clock's IP address from a status message, if any."""
        return None

    def icon_file(self, name: str) -> str | None:
        """Return the path of an icon file on the clock (None: not supported)."""
        return None

    def navigate(self, forward: bool) -> tuple[str, str] | None:
        """Return the (topic, payload) moving to the next or previous app."""
        return None

    # App loop order, read and changed over HTTP on the clock's web server.

    @property
    def loop_path(self) -> str | None:
        """Return the HTTP path listing the apps of the loop, in order."""
        return None

    @property
    def reorder_path(self) -> str | None:
        """Return the HTTP path taking the loop's new order (a list of names)."""
        return None


class Awtrix3Driver(FirmwareDriver):
    """AWTRIX 3 (https://blueforcer.github.io/awtrix3/)."""

    firmware = FIRMWARE_AWTRIX3

    def app_topic(self, app_name: str) -> str:
        """Return the custom app topic."""
        return f"{self.prefix}/custom/{app_name}"

    def indicator_topic(self, number: str) -> str:
        """Indicators have one topic each."""
        return f"{self.prefix}/indicator{number}"

    @property
    def remove_payload(self) -> str:
        """An empty payload deletes a custom app or turns an indicator off."""
        return ""

    @property
    def current_app_topic(self) -> str:
        """AWTRIX 3 publishes the name of the app on screen."""
        return f"{self.prefix}/stats/currentApp"

    @property
    def status_topic(self) -> str:
        """AWTRIX 3 publishes its stats periodically."""
        return f"{self.prefix}/stats"

    def parse_current_app(self, payload: str) -> str | None:
        """The payload is the bare app name."""
        name = payload.strip()
        return name or None

    def parse_uptime(self, payload: str) -> float | None:
        """Read the `uptime` field of the stats JSON."""
        try:
            data = json.loads(payload)
        except ValueError:
            return None
        if not isinstance(data, dict):
            return None
        uptime = data.get("uptime")
        if isinstance(uptime, bool) or not isinstance(uptime, (int, float)):
            return None
        return float(uptime)

    def with_lifetime(self, page: dict[str, Any], seconds: int) -> dict[str, Any]:
        """AWTRIX 3 uses `lifetime`, in seconds."""
        if "lifetime" in page:
            return page
        return {**page, "lifetime": seconds}

    @property
    def screen_topic(self) -> str:
        """The clock answers screen requests on this topic."""
        return f"{self.prefix}/screen"

    def screen_request(self) -> tuple[str, str]:
        """Any message on `sendscreen` asks for the screen."""
        return f"{self.prefix}/sendscreen", ""

    def parse_screen(self, payload: str) -> list[int] | None:
        """The screen is a JSON array of 256 RGB integers."""
        try:
            data = json.loads(payload)
        except ValueError:
            return None
        if not isinstance(data, list) or len(data) != SCREEN_PIXELS:
            return None
        if not all(
            isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 0xFFFFFF
            for v in data
        ):
            return None
        return data

    def parse_address(self, payload: str) -> str | None:
        """The stats JSON carries `ip_address`; only private addresses count."""
        try:
            data = json.loads(payload)
        except ValueError:
            return None
        value = data.get("ip_address") if isinstance(data, dict) else None
        if not isinstance(value, str):
            return None
        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            return None
        # The address is read from MQTT: never send requests outside the LAN.
        if address.version != 4 or not address.is_private or address.is_loopback:
            return None
        return str(address)

    def icon_file(self, name: str) -> str:
        """Icons live in /ICONS; the app names them without the extension."""
        return f"/ICONS/{name}"

    def show_app(self, app_name: str) -> tuple[str, str]:
        """`switch` brings an app on screen by name."""
        return f"{self.prefix}/switch", json.dumps({"name": app_name})

    def navigate(self, forward: bool) -> tuple[str, str]:
        """`nextapp` and `previousapp` move through the rotation."""
        return f"{self.prefix}/{'nextapp' if forward else 'previousapp'}", ""

    @property
    def loop_path(self) -> str:
        """An object mapping each app name to its position."""
        return "/api/loop"

    @property
    def reorder_path(self) -> str:
        """Only available over HTTP; apps left out leave the loop."""
        return "/api/reorder"


DRIVERS: dict[str, type[FirmwareDriver]] = {
    FIRMWARE_AWTRIX3: Awtrix3Driver,
}


def get_driver(firmware: str, prefix: str) -> FirmwareDriver:
    """Return the driver for a firmware."""
    return DRIVERS[firmware](prefix)
