"""Tests for the live app engine, with a fake publisher."""

from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.awtrix_studio.drivers import Awtrix3Driver
from custom_components.awtrix_studio.live_app import AppConfig, LiveApp

TOPIC = "awtrix/custom/demo"
TWO_PAGES = '[{"text": "a"}, {"text": "b"}]'


class FakePublisher:
    """Record what the app publishes."""

    def __init__(self) -> None:
        """Start with nothing published."""
        self.messages: list[tuple[str, str]] = []

    async def __call__(self, topic: str, payload: str) -> None:
        """Record one publication."""
        self.messages.append((topic, payload))

    @property
    def payloads(self) -> list[str]:
        """Return the payloads only."""
        return [payload for _, payload in self.messages]


def make_app(
    hass: HomeAssistant,
    template: str,
    publisher: FakePublisher,
    **overrides: object,
) -> LiveApp:
    """Build an app with sensible defaults."""
    settings: dict[str, object] = {
        "name": "demo",
        "template": template,
        "page_interval": 1.5,
        "cycle_only_on_screen": True,
        "hide_when_empty": True,
        "lifetime": 0,
    }
    settings.update(overrides)
    return LiveApp(hass, Awtrix3Driver("awtrix"), AppConfig(**settings), publisher)  # type: ignore[arg-type]


async def tick(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, seconds: float
) -> None:
    """Advance time and run what became due."""
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_publishes_first_render(hass: HomeAssistant) -> None:
    """Enabling the app publishes its first page."""
    hass.states.async_set("sensor.minutes", "4")
    publisher = FakePublisher()
    app = make_app(hass, '{"text": "{{ states(\'sensor.minutes\') }} min"}', publisher)

    await app.async_enable()
    await hass.async_block_till_done()

    assert publisher.messages == [(TOPIC, '{"text":"4 min"}')]
    await app.async_shutdown()


async def test_republishes_only_on_change(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Unrelated or identical updates publish nothing."""
    hass.states.async_set("sensor.minutes", "4")
    publisher = FakePublisher()
    app = make_app(
        hass, '{"text": "{{ states(\'sensor.minutes\') | int }} min"}', publisher
    )
    await app.async_enable()
    await hass.async_block_till_done()

    # Same rendered value: nothing new.
    hass.states.async_set("sensor.minutes", "4.0")
    await tick(hass, freezer, 2)
    # Unrelated entity: nothing new.
    hass.states.async_set("sensor.other", "x")
    await tick(hass, freezer, 2)
    assert publisher.payloads == ['{"text":"4 min"}']

    hass.states.async_set("sensor.minutes", "3")
    await tick(hass, freezer, 2)
    assert publisher.payloads == ['{"text":"4 min"}', '{"text":"3 min"}']
    await app.async_shutdown()


async def test_bursts_are_throttled(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Rapid changes collapse into one publication per cooldown."""
    hass.states.async_set("sensor.value", "0")
    publisher = FakePublisher()
    app = make_app(hass, '{"text": "{{ states(\'sensor.value\') }}"}', publisher)
    await app.async_enable()
    await hass.async_block_till_done()

    for value in range(1, 6):
        hass.states.async_set("sensor.value", str(value))
        await hass.async_block_till_done()
    await tick(hass, freezer, 2)

    assert publisher.payloads == ['{"text":"0"}', '{"text":"5"}']
    await app.async_shutdown()


async def test_pages_alternate_only_on_screen(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Pages alternate while the app is shown, page 1 is restored after."""
    publisher = FakePublisher()
    app = make_app(hass, TWO_PAGES, publisher)
    await app.async_enable()
    await hass.async_block_till_done()
    assert publisher.payloads == ['{"text":"a"}']

    # Not on screen: no cycling.
    await tick(hass, freezer, 5)
    assert publisher.payloads == ['{"text":"a"}']
    assert not app.is_cycling

    app.async_set_on_screen(True)
    await tick(hass, freezer, 1.6)
    await tick(hass, freezer, 1.6)
    assert publisher.payloads == ['{"text":"a"}', '{"text":"b"}', '{"text":"a"}']

    await tick(hass, freezer, 1.6)  # back on page b
    app.async_set_on_screen(False)
    await tick(hass, freezer, 2)
    assert not app.is_cycling
    assert publisher.payloads[-1] == '{"text":"a"}'

    count = len(publisher.payloads)
    await tick(hass, freezer, 10)
    assert len(publisher.payloads) == count
    await app.async_shutdown()


async def test_pages_alternate_always_when_configured(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """With cycle_only_on_screen off, pages alternate all the time."""
    publisher = FakePublisher()
    app = make_app(hass, TWO_PAGES, publisher, cycle_only_on_screen=False)
    await app.async_enable()
    await hass.async_block_till_done()

    await tick(hass, freezer, 1.6)
    assert publisher.payloads == ['{"text":"a"}', '{"text":"b"}']
    await app.async_shutdown()


async def test_single_page_never_cycles(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """One page means nothing to alternate."""
    publisher = FakePublisher()
    app = make_app(hass, '[{"text": "a"}, {}]', publisher)
    await app.async_enable()
    await hass.async_block_till_done()
    app.async_set_on_screen(True)
    await tick(hass, freezer, 5)

    assert publisher.payloads == ['{"text":"a"}']
    assert not app.is_cycling
    await app.async_shutdown()


async def test_empty_app_is_hidden(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """No page removes the app; pages coming back restore it."""
    hass.states.async_set("sensor.deps", "0")
    template = (
        "{% if states('sensor.deps') | int > 0 %}"
        '{"text": "{{ states(\'sensor.deps\') }}"}'
        "{% else %}[]{% endif %}"
    )
    publisher = FakePublisher()
    app = make_app(hass, template, publisher)
    await app.async_enable()
    await hass.async_block_till_done()
    assert publisher.payloads == [""]

    hass.states.async_set("sensor.deps", "2")
    await tick(hass, freezer, 2)
    assert publisher.payloads == ["", '{"text":"2"}']
    await app.async_shutdown()


async def test_empty_app_shows_blank_when_not_hidden(hass: HomeAssistant) -> None:
    """With hide_when_empty off, an empty app stays as a blank page."""
    publisher = FakePublisher()
    app = make_app(hass, "[]", publisher, hide_when_empty=False)
    await app.async_enable()
    await hass.async_block_till_done()

    assert publisher.payloads == ["{}"]
    await app.async_shutdown()


async def test_invalid_render_keeps_last_pages(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, caplog
) -> None:
    """A broken render is logged once and the last good page stays."""
    hass.states.async_set("sensor.mode", "ok")
    template = (
        "{% if is_state('sensor.mode', 'ok') %}"
        '{"text": "ok"}'
        "{% else %}oops {{ states('sensor.mode') }}{% endif %}"
    )
    publisher = FakePublisher()
    app = make_app(hass, template, publisher)
    await app.async_enable()
    await hass.async_block_till_done()

    hass.states.async_set("sensor.mode", "bad")
    await tick(hass, freezer, 2)
    hass.states.async_set("sensor.mode", "bad")  # same error, no new log
    await tick(hass, freezer, 2)

    assert publisher.payloads == ['{"text":"ok"}']
    assert caplog.text.count("invalid pages") == 1
    await app.async_shutdown()


async def test_lifetime_is_added_and_kept_alive(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """The lifetime field is injected and the app refreshed before expiry."""
    publisher = FakePublisher()
    app = make_app(hass, '{"text": "a"}', publisher, lifetime=60)
    await app.async_enable()
    await hass.async_block_till_done()
    assert publisher.payloads == ['{"text":"a","lifetime":60}']

    await tick(hass, freezer, 31)
    assert publisher.payloads == ['{"text":"a","lifetime":60}'] * 2
    await app.async_shutdown()


async def test_disable_removes_from_clock(hass: HomeAssistant) -> None:
    """Disabling with remove publishes the removal payload."""
    publisher = FakePublisher()
    app = make_app(hass, '{"text": "a"}', publisher)
    await app.async_enable()
    await hass.async_block_till_done()

    await app.async_disable(remove=True)
    assert publisher.payloads == ['{"text":"a"}', ""]
    assert not app.enabled

    # Re-enabling publishes again even though the content is unchanged.
    await app.async_enable()
    await hass.async_block_till_done()
    assert publisher.payloads == ['{"text":"a"}', "", '{"text":"a"}']
    await app.async_shutdown()


async def test_shutdown_leaves_clock_alone(hass: HomeAssistant) -> None:
    """A shutdown (restart, reload) does not remove the app."""
    publisher = FakePublisher()
    app = make_app(hass, '{"text": "a"}', publisher)
    await app.async_enable()
    await hass.async_block_till_done()

    await app.async_shutdown()
    assert publisher.payloads == ['{"text":"a"}']
