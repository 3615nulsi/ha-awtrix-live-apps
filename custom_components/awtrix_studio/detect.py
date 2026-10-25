"""Tell which firmware a clock runs, from what it publishes over MQTT.

AWTRIX NG keeps its state on retained topics, so a subscriber gets it at once.
AWTRIX 3 answers a screen request right away. Nothing else is sent: a screen
request only makes the clock publish its screen.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import logging
from typing import Final

from homeassistant.components import mqtt
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError

from .const import FIRMWARE_AWTRIX3, FIRMWARE_AWTRIX_NG

_LOGGER = logging.getLogger(__name__)

# How long the clock has to show itself, in seconds.
DETECT_TIMEOUT: Final = 3.0


def detection_topics(prefix: str) -> dict[str, str]:
    """Topics only one firmware publishes, with the firmware they reveal."""
    return {
        f"{prefix}/state/prefix": FIRMWARE_AWTRIX_NG,
        f"{prefix}/state/device": FIRMWARE_AWTRIX_NG,
        f"{prefix}/screen": FIRMWARE_AWTRIX3,
        f"{prefix}/stats": FIRMWARE_AWTRIX3,
    }


async def async_detect_firmware(
    hass: HomeAssistant, prefix: str, timeout: float = DETECT_TIMEOUT
) -> str | None:
    """Return the firmware of the clock using `prefix`, or None if it is silent."""
    found: asyncio.Future[str] = hass.loop.create_future()

    def listener(firmware: str) -> Callable[[mqtt.ReceiveMessage], None]:
        @callback
        def on_message(_msg: mqtt.ReceiveMessage) -> None:
            if not found.done():
                found.set_result(firmware)

        return on_message

    unsubscribers: list[Callable[[], None]] = []
    try:
        for topic, firmware in detection_topics(prefix).items():
            unsubscribers.append(
                await mqtt.async_subscribe(hass, topic, listener(firmware))
            )
        # AWTRIX 3 answers on `<prefix>/screen`; AWTRIX NG ignores this topic.
        await mqtt.async_publish(hass, f"{prefix}/sendscreen", "", qos=0)
        return await asyncio.wait_for(found, timeout)
    except TimeoutError:
        return None
    except HomeAssistantError as err:
        _LOGGER.debug("Cannot detect the firmware of %s: %s", prefix, err)
        return None
    finally:
        for unsubscribe in unsubscribers:
            unsubscribe()
