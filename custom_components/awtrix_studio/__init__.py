"""Awtrix Studio: AWTRIX apps bound to Home Assistant templates."""

from __future__ import annotations

import logging

from homeassistant.components import mqtt
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.typing import ConfigType

from . import websocket
from .const import CONF_FIRMWARE, CONF_PREFIX, DOMAIN, SERVICE_REFRESH
from .drivers import get_driver
from .manager import MANAGED_SUBENTRY_TYPES, ClockManager, subentry_topic
from .panel import async_register_panel

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SWITCH]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type AwtrixStudioConfigEntry = ConfigEntry[ClockManager]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the integration's services."""

    async def _async_refresh(call: ServiceCall) -> None:
        for entry in hass.config_entries.async_loaded_entries(DOMAIN):
            await entry.runtime_data.async_republish_all()

    hass.services.async_register(DOMAIN, SERVICE_REFRESH, _async_refresh)
    websocket.async_setup(hass)
    await async_register_panel(hass)
    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: AwtrixStudioConfigEntry
) -> bool:
    """Set up one clock."""
    if not await mqtt.async_wait_for_mqtt_client(hass):
        raise ConfigEntryNotReady("MQTT is not available")

    manager = ClockManager(
        hass, get_driver(entry.data[CONF_FIRMWARE], entry.data[CONF_PREFIX])
    )
    for subentry in entry.subentries.values():
        if subentry.subentry_type in MANAGED_SUBENTRY_TYPES:
            manager.add_app(subentry)
    await manager.async_start()
    entry.runtime_data = manager

    # Apps are enabled by their switch, once its last state is restored.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    async_dispatcher_send(hass, websocket.signal_entry_loaded(entry.entry_id))
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: AwtrixStudioConfigEntry
) -> bool:
    """Unload a clock, leaving its apps on the clock until they are replaced."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_stop()
        async_dispatcher_send(hass, websocket.signal_entry_loaded(entry.entry_id))
    return unloaded


async def async_remove_entry(
    hass: HomeAssistant, entry: AwtrixStudioConfigEntry
) -> None:
    """Remove every app and indicator from the clock when it is deleted."""
    if not await mqtt.async_wait_for_mqtt_client(hass):
        return
    driver = get_driver(entry.data[CONF_FIRMWARE], entry.data[CONF_PREFIX])
    for subentry in entry.subentries.values():
        if subentry.subentry_type in MANAGED_SUBENTRY_TYPES:
            topic = subentry_topic(driver, subentry)
            await _async_remove_from_clock(hass, topic, driver.remove_payload)


async def _async_update_listener(
    hass: HomeAssistant, entry: AwtrixStudioConfigEntry
) -> None:
    """Apply app additions, edits and deletions."""
    manager = entry.runtime_data
    for subentry_id in _removed_app_ids(manager, entry):
        app = manager.apps[subentry_id]
        # The app's switch may already be gone (and the app stopped) by now,
        # so remove the app from the clock explicitly.
        await app.async_disable(remove=False)
        await app.async_remove_from_clock()
    await hass.config_entries.async_reload(entry.entry_id)


@callback
def _removed_app_ids(
    manager: ClockManager, entry: AwtrixStudioConfigEntry
) -> list[str]:
    return [sid for sid in manager.apps if sid not in entry.subentries]


async def _async_remove_from_clock(
    hass: HomeAssistant, topic: str, payload: str
) -> None:
    try:
        await mqtt.async_publish(hass, topic, payload, qos=0, retain=False)
    except HomeAssistantError as err:
        _LOGGER.debug("Could not remove app on %s: %s", topic, err)
