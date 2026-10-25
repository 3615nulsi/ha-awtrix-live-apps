"""Icons from the LaMetric gallery, served by Awtrix Studio.

An app can name its icon `lametric:<id>`. Awtrix Studio downloads that icon
once, keeps it in Home Assistant's storage and sends it inline with the app (as
an 8x8 JPEG in Base64, which AWTRIX 3 accepts in the `icon` key). Nothing has
to be uploaded to the clock first. Animated icons are sent as their first frame.

Plain icon names and numbers keep their usual meaning: a file stored on the
clock.
"""

from __future__ import annotations

import asyncio
import base64
from io import BytesIO
import json
import logging
import re
from typing import Any, Final

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from PIL import Image

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PREFIX: Final = "lametric:"
ICON_RE: Final = re.compile(r"^lametric:(\d{1,7})$")
SEARCH_URL: Final = "https://developer.lametric.com/api/v1/dev/preloadicons"
ICON_URL: Final = "https://developer.lametric.com/content/apps/icon_thumbs/{id}"
STORAGE_VERSION: Final = 1
MAX_ICON_BYTES: Final = 64 * 1024
TIMEOUT: Final = aiohttp.ClientTimeout(total=10)
PAGE_SIZE: Final = 48
SIZE: Final = 8
# How long a failed download is not retried, in seconds.
RETRY_AFTER: Final = 300


class IconError(Exception):
    """An icon that could not be downloaded or read."""


def icon_id(value: Any) -> int | None:
    """Return the LaMetric id of a `lametric:<id>` icon, else None."""
    if isinstance(value, str) and (match := ICON_RE.fullmatch(value)):
        return int(match.group(1))
    return None


def convert(data: bytes) -> dict[str, Any]:
    """Turn a LaMetric icon file into pixels and an 8x8 Base64 JPEG.

    Runs in the executor (Pillow is blocking). Transparent pixels become black,
    the clock's "off".
    """
    try:
        with Image.open(BytesIO(data)) as image:
            animated = getattr(image, "n_frames", 1) > 1
            image.seek(0)
            frame = image.convert("RGBA")
    except (OSError, ValueError, Image.DecompressionBombError) as err:
        raise IconError(f"unreadable icon: {err}") from err
    if frame.size != (SIZE, SIZE):
        frame = frame.resize((SIZE, SIZE), Image.Resampling.NEAREST)
    background = Image.new("RGBA", frame.size, (0, 0, 0, 255))
    rgb = Image.alpha_composite(background, frame).convert("RGB")

    raw = rgb.tobytes()
    pixels = [
        (raw[i] << 16) | (raw[i + 1] << 8) | raw[i + 2] for i in range(0, len(raw), 3)
    ]
    buffer = BytesIO()
    # Full quality and no chroma subsampling: an 8x8 image is a single block.
    rgb.save(buffer, format="JPEG", quality=100, subsampling=0)
    return {
        "pixels": pixels,
        "jpeg": base64.b64encode(buffer.getvalue()).decode("ascii"),
        "animated": animated,
    }


class IconStore:
    """Downloaded LaMetric icons, kept in Home Assistant's storage."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the store (call async_load before use)."""
        self.hass = hass
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.icons"
        )
        self._icons: dict[str, dict[str, Any]] = {}
        self._pending: dict[int, asyncio.Future[dict[str, Any] | None]] = {}
        self._failed: dict[int, float] = {}

    async def async_load(self) -> None:
        """Read the icons downloaded earlier."""
        data = await self._store.async_load() or {}
        icons = data.get("icons", {})
        self._icons = {
            key: value
            for key, value in icons.items()
            if isinstance(value, dict) and isinstance(value.get("jpeg"), str)
        }

    def get(self, lametric_id: int) -> dict[str, Any] | None:
        """Return a downloaded icon, if any."""
        return self._icons.get(str(lametric_id))

    async def async_get(self, lametric_id: int) -> dict[str, Any] | None:
        """Return an icon, downloading it the first time. None if unavailable."""
        if (icon := self.get(lametric_id)) is not None:
            return icon
        if (pending := self._pending.get(lametric_id)) is not None:
            return await pending
        failed_at = self._failed.get(lametric_id)
        if failed_at is not None and self.hass.loop.time() - failed_at < RETRY_AFTER:
            return None

        future: asyncio.Future[dict[str, Any] | None] = self.hass.loop.create_future()
        self._pending[lametric_id] = future
        try:
            icon = await self._async_download(lametric_id)
        except IconError as err:
            _LOGGER.warning("LaMetric icon %s is not available: %s", lametric_id, err)
            self._failed[lametric_id] = self.hass.loop.time()
            icon = None
        else:
            self._icons[str(lametric_id)] = icon
            self._store.async_delay_save(lambda: {"icons": self._icons}, 5)
        finally:
            del self._pending[lametric_id]
        future.set_result(icon)
        return icon

    async def _async_download(self, lametric_id: int) -> dict[str, Any]:
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(
                ICON_URL.format(id=lametric_id), timeout=TIMEOUT
            ) as response:
                if response.status != 200:
                    raise IconError(f"HTTP {response.status}")
                length = response.headers.get("Content-Length", "0")
                if length.isdigit() and int(length) > MAX_ICON_BYTES:
                    raise IconError("file too large")
                data = await response.read()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise IconError(str(err) or type(err).__name__) from err
        if len(data) > MAX_ICON_BYTES:
            raise IconError("file too large")
        return await self.hass.async_add_executor_job(convert, data)

    async def async_search(self, query: str, page: int) -> dict[str, Any]:
        """Search the LaMetric gallery. Only ids, names and a flag come back."""
        session = async_get_clientsession(self.hass)
        params = {
            "page": str(page),
            "category": "",
            "search": query,
            "count": str(PAGE_SIZE),
        }
        try:
            async with session.get(
                SEARCH_URL, params=params, timeout=TIMEOUT
            ) as response:
                if response.status != 200:
                    raise IconError(f"HTTP {response.status}")
                payload = json.loads(await response.text())
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise IconError(str(err) or type(err).__name__) from err

        icons = []
        for item in payload.get("icons", []) if isinstance(payload, dict) else []:
            if not isinstance(item, dict):
                continue
            lametric_id = item.get("id")
            if not isinstance(lametric_id, int) or not 0 < lametric_id < 10_000_000:
                continue
            name = item.get("name")
            icons.append(
                {
                    "id": lametric_id,
                    "name": name[:64] if isinstance(name, str) else "",
                    "animated": item.get("type") == 1,
                }
            )
        total = payload.get("count_all") if isinstance(payload, dict) else None
        return {
            "icons": icons,
            "more": isinstance(total, int) and total > page * PAGE_SIZE,
        }

    async def async_resolve(self, payload: str) -> str:
        """Replace a `lametric:<id>` icon in a page payload by the icon itself."""
        if PREFIX not in payload:
            return payload
        try:
            page = json.loads(payload)
        except ValueError:
            return payload
        if (
            not isinstance(page, dict)
            or (lametric_id := icon_id(page.get("icon"))) is None
        ):
            return payload
        icon = await self.async_get(lametric_id)
        if icon is None:
            page.pop("icon")
        else:
            page["icon"] = icon["jpeg"]
        return json.dumps(page, ensure_ascii=False, separators=(",", ":"))
