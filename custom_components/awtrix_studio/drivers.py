"""Firmware drivers.

A driver only knows how to *transport* apps for a given firmware: which topic
to publish to, how to remove an app, how to tell which app is on screen and how
to detect a reboot. The app *content* is the firmware's native JSON, written by
the user in the template, and is never translated.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import json
from typing import Any

from .const import FIRMWARE_AWTRIX3


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


DRIVERS: dict[str, type[FirmwareDriver]] = {
    FIRMWARE_AWTRIX3: Awtrix3Driver,
}


def get_driver(firmware: str, prefix: str) -> FirmwareDriver:
    """Return the driver for a firmware."""
    return DRIVERS[firmware](prefix)
