"""Per-clock coordination: MQTT subscriptions shared by all apps of a clock."""

from __future__ import annotations

from collections.abc import Callable
import logging

from homeassistant.components import mqtt
from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError

from .const import (
    CONF_APP_NAME,
    CONF_CYCLE_ONLY_ON_SCREEN,
    CONF_HIDE_WHEN_EMPTY,
    CONF_INDICATOR,
    CONF_LIFETIME,
    CONF_MODE,
    CONF_PAGE_INTERVAL,
    CONF_TEMPLATE,
    DEFAULT_CYCLE_ONLY_ON_SCREEN,
    DEFAULT_HIDE_WHEN_EMPTY,
    DEFAULT_LIFETIME,
    DEFAULT_PAGE_INTERVAL,
    MODE_SIMPLE,
    SUBENTRY_TYPE_APP,
    SUBENTRY_TYPE_INDICATOR,
)
from .drivers import FirmwareDriver
from .live_app import AppConfig, LiveApp
from .templates import build_app_template, build_indicator_template

MANAGED_SUBENTRY_TYPES = (SUBENTRY_TYPE_APP, SUBENTRY_TYPE_INDICATOR)

_LOGGER = logging.getLogger(__name__)


def subentry_template(subentry: ConfigSubentry) -> str:
    """Return the template of an app or indicator, generating it in simple mode."""
    data = subentry.data
    if data.get(CONF_MODE) == MODE_SIMPLE:
        if subentry.subentry_type == SUBENTRY_TYPE_INDICATOR:
            return build_indicator_template(data)
        return build_app_template(data)
    return data[CONF_TEMPLATE]


def subentry_topic(driver: FirmwareDriver, subentry: ConfigSubentry) -> str:
    """Return the topic an app or indicator publishes to."""
    if subentry.subentry_type == SUBENTRY_TYPE_INDICATOR:
        return driver.indicator_topic(subentry.data[CONF_INDICATOR])
    return driver.app_topic(subentry.data[CONF_APP_NAME])


def app_config_from_subentry(subentry: ConfigSubentry) -> AppConfig:
    """Build the engine configuration of an app or indicator."""
    data = subentry.data
    if subentry.subentry_type == SUBENTRY_TYPE_INDICATOR:
        return AppConfig(
            name=f"indicator{data[CONF_INDICATOR]}",
            template=subentry_template(subentry),
            page_interval=DEFAULT_PAGE_INTERVAL,
            cycle_only_on_screen=True,
            hide_when_empty=True,
            lifetime=0,
            single_page=True,
        )
    simple = data.get(CONF_MODE) == MODE_SIMPLE
    return AppConfig(
        name=data[CONF_APP_NAME],
        template=subentry_template(subentry),
        page_interval=float(data.get(CONF_PAGE_INTERVAL, DEFAULT_PAGE_INTERVAL)),
        cycle_only_on_screen=bool(
            data.get(CONF_CYCLE_ONLY_ON_SCREEN, DEFAULT_CYCLE_ONLY_ON_SCREEN)
        ),
        hide_when_empty=simple
        or bool(data.get(CONF_HIDE_WHEN_EMPTY, DEFAULT_HIDE_WHEN_EMPTY)),
        lifetime=int(data.get(CONF_LIFETIME, DEFAULT_LIFETIME)),
    )


class ClockManager:
    """Own the apps of one clock and the topics they share."""

    def __init__(self, hass: HomeAssistant, driver: FirmwareDriver) -> None:
        """Initialize the manager."""
        self.hass = hass
        self.driver = driver
        # Keyed by config subentry id.
        self.apps: dict[str, LiveApp] = {}
        self._unsubscribers: list[Callable[[], None]] = []
        self._current_app: str | None = None
        self._last_uptime: float | None = None

    @property
    def prefix(self) -> str:
        """Return the clock's MQTT prefix."""
        return self.driver.prefix

    @callback
    def add_app(self, subentry: ConfigSubentry) -> LiveApp:
        """Create the live app or indicator for a subentry (not enabled yet)."""
        app = LiveApp(
            self.hass,
            self.driver,
            app_config_from_subentry(subentry),
            self._publish,
            topic=subentry_topic(self.driver, subentry),
        )
        app.async_set_on_screen(app.name == self._current_app)
        self.apps[subentry.subentry_id] = app
        return app

    async def async_start(self) -> None:
        """Subscribe to the clock's topics."""
        if topic := self.driver.current_app_topic:
            self._unsubscribers.append(
                await mqtt.async_subscribe(self.hass, topic, self._on_current_app)
            )
        if topic := self.driver.status_topic:
            self._unsubscribers.append(
                await mqtt.async_subscribe(self.hass, topic, self._on_status)
            )
        self._unsubscribers.append(
            mqtt.async_subscribe_connection_status(self.hass, self._on_connection)
        )

    async def async_stop(self) -> None:
        """Stop all apps without touching the clock."""
        while self._unsubscribers:
            self._unsubscribers.pop()()
        for app in self.apps.values():
            await app.async_shutdown()

    async def async_republish_all(self) -> None:
        """Publish every enabled app again."""
        for app in self.apps.values():
            await app.async_republish()

    async def _publish(self, topic: str, payload: str) -> None:
        try:
            await mqtt.async_publish(self.hass, topic, payload, qos=0, retain=False)
        except HomeAssistantError as err:
            _LOGGER.debug("Could not publish to %s: %s", topic, err)

    @callback
    def _on_current_app(self, msg: mqtt.ReceiveMessage) -> None:
        payload = msg.payload
        if isinstance(payload, bytes):
            payload = payload.decode(errors="replace")
        self._current_app = self.driver.parse_current_app(str(payload))
        for app in self.apps.values():
            app.async_set_on_screen(app.name == self._current_app)

    @callback
    def _on_status(self, msg: mqtt.ReceiveMessage) -> None:
        payload = msg.payload
        if isinstance(payload, bytes):
            payload = payload.decode(errors="replace")
        uptime = self.driver.parse_uptime(str(payload))
        if uptime is None:
            return
        rebooted = self._last_uptime is not None and uptime < self._last_uptime
        self._last_uptime = uptime
        if rebooted:
            _LOGGER.debug("Clock %s restarted, publishing apps again", self.prefix)
            self.hass.async_create_task(
                self.async_republish_all(), f"awtrix_studio republish {self.prefix}"
            )

    @callback
    def _on_connection(self, connected: bool) -> None:
        if connected:
            self.hass.async_create_task(
                self.async_republish_all(), f"awtrix_studio republish {self.prefix}"
            )
