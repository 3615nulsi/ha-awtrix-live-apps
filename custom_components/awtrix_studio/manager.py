"""Per-clock coordination: MQTT subscriptions shared by all apps of a clock."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
import logging

from homeassistant.components import mqtt
from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_call_later, async_track_time_interval

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
from .icons import IconStore
from .live_app import AppConfig, LiveApp
from .templates import (
    InvalidSimpleOptionsError,
    build_app_template,
    build_indicator_template,
)

MANAGED_SUBENTRY_TYPES = (SUBENTRY_TYPE_APP, SUBENTRY_TYPE_INDICATOR)

# How often the screen mirror asks the clock for its screen, while a panel
# is watching. Nothing is requested when no one is.
SCREEN_REFRESH = timedelta(seconds=1)
# How long a "test on the clock" stays before the real content comes back.
TEST_DURATION = 15.0

_LOGGER = logging.getLogger(__name__)


def subentry_template(subentry: ConfigSubentry) -> str:
    """Return the template of an app or indicator, generating it in simple mode."""
    data = subentry.data
    if data.get(CONF_MODE) != MODE_SIMPLE:
        return data[CONF_TEMPLATE]
    try:
        if subentry.subentry_type == SUBENTRY_TYPE_INDICATOR:
            return build_indicator_template(data)
        return build_app_template(data)
    except InvalidSimpleOptionsError as err:
        _LOGGER.error("Cannot build %s: %s", subentry.title, err)
        return "{}"


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

    def __init__(
        self, hass: HomeAssistant, driver: FirmwareDriver, icons: IconStore
    ) -> None:
        """Initialize the manager."""
        self.hass = hass
        self.driver = driver
        self.icons = icons
        # Keyed by config subentry id.
        self.apps: dict[str, LiveApp] = {}
        self._unsubscribers: list[Callable[[], None]] = []
        self._current_app: str | None = None
        self._last_uptime: float | None = None
        self._listeners: list[Callable[[], None]] = []
        self._screen_listeners: list[Callable[[list[int]], None]] = []
        self._screen_unsubscribers: list[Callable[[], None]] = []
        self._test_timers: dict[str, CALLBACK_TYPE] = {}

    @property
    def current_app(self) -> str | None:
        """Return the name of the app the clock is showing, if known."""
        return self._current_app

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> CALLBACK_TYPE:
        """Call `listener` when an app changes or the clock switches app."""
        self._listeners.append(listener)

        @callback
        def remove() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return remove

    @callback
    def _notify(self) -> None:
        for listener in list(self._listeners):
            listener()

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
        app.async_add_listener(self._notify)
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
        self._screen_listeners.clear()
        self._stop_screen()
        for cancel in self._test_timers.values():
            cancel()
        self._test_timers.clear()
        for app in self.apps.values():
            await app.async_shutdown()

    async def async_send(self, message: tuple[str, str] | None) -> None:
        """Publish a (topic, payload) command, if the firmware has one."""
        if message is not None:
            await self._publish(*message)

    async def async_test(
        self, topic: str, payload: str, restore: LiveApp | None
    ) -> None:
        """Show a payload for a while, then bring the real content back."""
        if cancel := self._test_timers.pop(topic, None):
            cancel()
        await self._publish(topic, payload)

        async def _restore(_now: datetime) -> None:
            self._test_timers.pop(topic, None)
            if restore is not None and restore.enabled:
                await restore.async_republish()
            else:
                await self._publish(topic, self.driver.remove_payload)

        self._test_timers[topic] = async_call_later(self.hass, TEST_DURATION, _restore)

    # ---------------------------------------------------------- screen mirror

    async def async_subscribe_screen(
        self, listener: Callable[[list[int]], None]
    ) -> CALLBACK_TYPE:
        """Stream the clock's screen to `listener` while subscribed."""
        self._screen_listeners.append(listener)
        if len(self._screen_listeners) == 1:
            await self._async_start_screen()

        @callback
        def remove() -> None:
            if listener in self._screen_listeners:
                self._screen_listeners.remove(listener)
            if not self._screen_listeners:
                self._stop_screen()

        return remove

    async def _async_start_screen(self) -> None:
        topic = self.driver.screen_topic
        if topic is None or self.driver.screen_request() is None:
            return
        self._screen_unsubscribers.append(
            await mqtt.async_subscribe(self.hass, topic, self._on_screen)
        )

        async def _request(_now: datetime | None = None) -> None:
            await self.async_send(self.driver.screen_request())

        self._screen_unsubscribers.append(
            async_track_time_interval(
                self.hass,
                _request,
                SCREEN_REFRESH,
                name=f"awtrix_studio screen {self.prefix}",
            )
        )
        await _request()

    @callback
    def _stop_screen(self) -> None:
        while self._screen_unsubscribers:
            self._screen_unsubscribers.pop()()

    @callback
    def _on_screen(self, msg: mqtt.ReceiveMessage) -> None:
        payload = msg.payload
        if isinstance(payload, bytes):
            payload = payload.decode(errors="replace")
        pixels = self.driver.parse_screen(str(payload))
        if pixels is None:
            return
        for listener in list(self._screen_listeners):
            listener(pixels)

    async def async_republish_all(self) -> None:
        """Publish every enabled app again."""
        for app in self.apps.values():
            await app.async_republish()

    async def _publish(self, topic: str, payload: str) -> None:
        # Icons from the LaMetric gallery are sent inline, nothing is stored
        # on the clock.
        payload = await self.icons.async_resolve(payload)
        try:
            await mqtt.async_publish(self.hass, topic, payload, qos=0, retain=False)
        except HomeAssistantError as err:
            _LOGGER.debug("Could not publish to %s: %s", topic, err)

    @callback
    def _on_current_app(self, msg: mqtt.ReceiveMessage) -> None:
        payload = msg.payload
        if isinstance(payload, bytes):
            payload = payload.decode(errors="replace")
        current = self.driver.parse_current_app(str(payload))
        if current == self._current_app:
            return
        self._current_app = current
        for app in self.apps.values():
            app.async_set_on_screen(app.name == self._current_app)
        self._notify()

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
