"""Requests to the clock's web server: animated icons and the app loop.

AWTRIX only animates icons stored in its own memory. For an animated icon of
the LaMetric gallery, Awtrix Studio drops the GIF into the clock's /ICONS
folder through its web file manager (the one the clock's web page uses), once,
and the app then names the icon by its number.

The clock's address comes from its MQTT stats and is limited to private IPv4
addresses. Files are only ever added, never deleted. When the clock cannot be
reached (or its web page is password protected), the caller falls back to the
icon's first image sent inline.

The app loop order is also read and changed there: AWTRIX has no MQTT command
to reorder apps.
"""

from __future__ import annotations

import json
import logging
from typing import Final

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .drivers import FirmwareDriver

_LOGGER = logging.getLogger(__name__)

TIMEOUT: Final = aiohttp.ClientTimeout(total=5)
# How long a failed upload is not retried, in seconds.
RETRY_AFTER: Final = 300


def upload_form(path: str, data: bytes) -> aiohttp.FormData:
    """The multipart form of the clock's file manager.

    The file name is the destination path and must reach the clock as is:
    aiohttp would otherwise percent-encode its slashes.
    """
    form = aiohttp.FormData(quote_fields=False)
    form.add_field("data", data, filename=path, content_type="application/octet-stream")
    return form


class ClockFiles:
    """Icon files of one clock."""

    def __init__(self, hass: HomeAssistant, driver: FirmwareDriver) -> None:
        """Initialize (the address is learned from the clock's stats)."""
        self.hass = hass
        self.driver = driver
        self.address: str | None = None
        self._present: set[str] | None = None
        self._failed_at: dict[str, float] = {}
        self._list_failed_at: float | None = None
        self._warned = False

    @property
    def supported(self) -> bool:
        """Return True if icons can be stored on this clock."""
        return self.address is not None and self.driver.icon_file("x") is not None

    def set_address(self, address: str | None) -> bool:
        """Remember the clock's address; return True if it changed."""
        if address == self.address:
            return False
        self.address = address
        self._present = None
        self._failed_at.clear()
        self._list_failed_at = None
        return True

    async def async_has(self, name: str) -> bool | None:
        """Return True if an icon file `<name>.*` is on the clock.

        None when the clock's files cannot be listed.
        """
        if not self.supported:
            return None
        if self._present is None:
            failed_at = self._list_failed_at
            if (
                failed_at is not None
                and self.hass.loop.time() - failed_at < RETRY_AFTER
            ):
                return None
            try:
                self._present = await self._async_list()
            except (aiohttp.ClientError, TimeoutError, ValueError):
                self._list_failed_at = self.hass.loop.time()
                return None
        return any(filename.rsplit(".", 1)[0] == name for filename in self._present)

    async def async_ensure(self, name: str, data: bytes, extension: str) -> bool:
        """Make sure `<name>.<extension>` is on the clock; return True if it is."""
        if not self.supported:
            return False
        filename = f"{name}.{extension}"
        failed_at = self._failed_at.get(filename)
        if failed_at is not None and self.hass.loop.time() - failed_at < RETRY_AFTER:
            return False
        try:
            if self._present is None:
                self._present = await self._async_list()
            if filename in self._present:
                return True
            await self._async_upload(filename, data)
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            self._failed_at[filename] = self.hass.loop.time()
            if not self._warned:
                self._warned = True
                _LOGGER.warning(
                    "Cannot store animated icons on the clock at %s (%s); their "
                    "first image is shown instead. If the clock's web page has a "
                    "password, animated icons need it disabled",
                    self.address,
                    err,
                )
            return False
        self._present.add(filename)
        return True

    def _url(self, path: str) -> str:
        return f"http://{self.address}{path}"

    async def _async_list(self) -> set[str]:
        folder = self.driver.icon_file("").rstrip("/")
        session = async_get_clientsession(self.hass)
        async with session.get(
            self._url("/list"), params={"dir": folder}, timeout=TIMEOUT
        ) as response:
            response.raise_for_status()
            entries = json.loads(await response.text())
        if not isinstance(entries, list):
            raise ValueError("unexpected file list")
        return {
            entry["name"]
            for entry in entries
            if isinstance(entry, dict) and isinstance(entry.get("name"), str)
        }

    async def _async_upload(self, filename: str, data: bytes) -> None:
        form = upload_form(self.driver.icon_file(filename), data)
        session = async_get_clientsession(self.hass)
        async with session.post(
            self._url("/edit"), data=form, timeout=TIMEOUT
        ) as response:
            response.raise_for_status()
        _LOGGER.debug("Stored icon %s on the clock at %s", filename, self.address)

    async def async_get_text(self, path: str) -> str:
        """GET a path of the clock's web server and return the body."""
        if self.address is None:
            raise ValueError("address unknown")
        session = async_get_clientsession(self.hass)
        async with session.get(self._url(path), timeout=TIMEOUT) as response:
            response.raise_for_status()
            return await response.text()

    async def async_post_json(self, path: str, body: object) -> None:
        """POST a JSON body to a path of the clock's web server."""
        if self.address is None:
            raise ValueError("address unknown")
        session = async_get_clientsession(self.hass)
        async with session.post(
            self._url(path),
            data=json.dumps(body, ensure_ascii=False),
            headers={"Content-Type": "application/json"},
            timeout=TIMEOUT,
        ) as response:
            response.raise_for_status()
