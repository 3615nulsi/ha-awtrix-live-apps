"""One switch per live app: turning it off removes the app from the clock."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigSubentry
from homeassistant.const import STATE_OFF
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import AwtrixStudioConfigEntry
from .const import CONF_PREFIX, DOMAIN, SUBENTRY_TYPE_APP
from .live_app import LiveApp

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AwtrixStudioConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add a switch for every app of the clock."""
    manager = entry.runtime_data
    for subentry in entry.subentries.values():
        if subentry.subentry_type != SUBENTRY_TYPE_APP:
            continue
        async_add_entities(
            [AppSwitch(entry, subentry, manager.apps[subentry.subentry_id])],
            config_subentry_id=subentry.subentry_id,
        )


class AppSwitch(SwitchEntity, RestoreEntity):
    """Enable or disable a live app."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "app"

    def __init__(
        self,
        entry: AwtrixStudioConfigEntry,
        subentry: ConfigSubentry,
        app: LiveApp,
    ) -> None:
        """Initialize the switch."""
        self._app = app
        self._attr_unique_id = f"{subentry.subentry_id}_enabled"
        self._attr_translation_placeholders = {"app_name": app.name}
        prefix = entry.data[CONF_PREFIX]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"{prefix} Studio",
            manufacturer="Awtrix Studio",
            model="AWTRIX clock",
        )

    @property
    def is_on(self) -> bool:
        """Return True if the app is running."""
        return self._app.enabled

    async def async_added_to_hass(self) -> None:
        """Restore the previous state and start the app accordingly."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is None or last_state.state != STATE_OFF:
            await self._app.async_enable()
        else:
            # Make sure a previously disabled app is not left on the clock.
            await self._app.async_remove_from_clock()

    async def async_will_remove_from_hass(self) -> None:
        """Stop the app when the entity goes away.

        On a plain unload (restart, reload) the app stays on the clock until it
        is published again. If the user disabled the entity, the app is removed.
        """
        disabled = self.registry_entry is not None and self.registry_entry.disabled
        await self._app.async_disable(remove=disabled)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Start the app."""
        await self._app.async_enable()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Stop the app and remove it from the clock."""
        await self._app.async_disable(remove=True)
        self.async_write_ha_state()
