"""End-to-end tests: config flows, MQTT, switch, reloads."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState, ConfigSubentryDataWithId
from homeassistant.const import ATTR_ENTITY_ID, SERVICE_TURN_OFF, SERVICE_TURN_ON
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, InvalidData
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_mqtt_message,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.typing import MqttMockHAClient

from custom_components.awtrix_studio.const import DOMAIN

PREFIX = "awtrix_test"
APP_TOPIC = f"{PREFIX}/custom/demo"
SWITCH = "switch.awtrix_test_studio_demo"

APP_DATA: dict[str, Any] = {
    "app_name": "demo",
    "template": '[{"text": "a"}, {"text": "b"}]',
    "page_interval": 1.5,
    "cycle_only_on_screen": True,
    "hide_when_empty": True,
    "lifetime": 0,
}


def published(mqtt_mock: MqttMockHAClient, topic: str = APP_TOPIC) -> list[str]:
    """Return the payloads published on a topic, in order."""
    return [
        call.args[1]
        for call in mqtt_mock.async_publish.call_args_list
        if call.args[0] == topic
    ]


@pytest.fixture
def mock_entry() -> MockConfigEntry:
    """A clock with one two-page app."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=PREFIX,
        unique_id=PREFIX,
        data={"firmware": "awtrix3", "prefix": PREFIX},
        subentries_data=[
            ConfigSubentryDataWithId(
                data=APP_DATA,
                subentry_id="app_demo",
                subentry_type="app",
                title="demo",
                unique_id="demo",
            )
        ],
    )


async def setup_entry(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Add and set up the entry."""
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def tick(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, seconds: float
) -> None:
    """Advance time and run what became due."""
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


# --------------------------------------------------------------- config flow


async def test_flow_requires_mqtt(hass: HomeAssistant) -> None:
    """Without MQTT there is nothing to talk through."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "mqtt_not_configured"


async def test_flow_creates_clock(
    hass: HomeAssistant, mqtt_mock: MqttMockHAClient
) -> None:
    """A clock is identified by its prefix."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"firmware": "awtrix3", "prefix": " bad prefix "}
    )
    assert result["errors"] == {"prefix": "invalid_prefix"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"firmware": "awtrix3", "prefix": f"/{PREFIX}/"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == PREFIX
    assert result["data"] == {"firmware": "awtrix3", "prefix": PREFIX}

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"firmware": "awtrix3", "prefix": PREFIX}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_subentry_flow_adds_app(
    hass: HomeAssistant, mqtt_mock: MqttMockHAClient
) -> None:
    """Adding an app validates it, then publishes it."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=PREFIX,
        unique_id=PREFIX,
        data={"firmware": "awtrix3", "prefix": PREFIX},
    )
    await setup_entry(hass, entry)

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "app"), context={"source": "user"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "app"

    bad = {**APP_DATA, "app_name": "no spaces"}
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], bad
    )
    assert result["errors"] == {"app_name": "invalid_app_name"}

    bad = {**APP_DATA, "template": "{{ 'not json' }}"}
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], bad
    )
    assert result["errors"] == {"template": "invalid_pages"}

    # Syntax errors are caught by the template selector itself.
    with pytest.raises(InvalidData):
        await hass.config_entries.subentries.async_configure(
            result["flow_id"], {**APP_DATA, "template": "{{ broken"}
        )

    # Errors that only show up when rendering are caught by the flow.
    bad = {**APP_DATA, "template": "{{ 'abc' | int }}"}
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], bad
    )
    assert result["errors"] == {"template": "invalid_template"}

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], APP_DATA
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    assert published(mqtt_mock) == ['{"text":"a"}']
    assert hass.states.get(SWITCH).state == "on"

    # Same name twice is refused.
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "app"), context={"source": "user"}
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], APP_DATA
    )
    assert result["errors"] == {"app_name": "app_name_exists"}


async def test_subentry_reconfigure_keeps_name(
    hass: HomeAssistant, mqtt_mock: MqttMockHAClient, mock_entry: MockConfigEntry
) -> None:
    """Editing an app changes its template, not its name."""
    await setup_entry(hass, mock_entry)

    result = await mock_entry.start_subentry_reconfigure_flow(hass, "app_demo")
    assert result["type"] is FlowResultType.FORM
    new_data = {k: v for k, v in APP_DATA.items() if k != "app_name"}
    new_data["template"] = '{"text": "edited"}'
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], new_data
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()

    subentry = mock_entry.subentries["app_demo"]
    assert subentry.data["app_name"] == "demo"
    assert published(mqtt_mock)[-1] == '{"text":"edited"}'


# ------------------------------------------------------------------- runtime


async def test_pages_follow_current_app(
    hass: HomeAssistant,
    mqtt_mock: MqttMockHAClient,
    mock_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Pages alternate only while the clock shows the app."""
    await setup_entry(hass, mock_entry)
    assert published(mqtt_mock) == ['{"text":"a"}']

    async_fire_mqtt_message(hass, f"{PREFIX}/stats/currentApp", "demo")
    await hass.async_block_till_done()
    await tick(hass, freezer, 1.6)
    assert published(mqtt_mock) == ['{"text":"a"}', '{"text":"b"}']

    async_fire_mqtt_message(hass, f"{PREFIX}/stats/currentApp", "Time")
    await hass.async_block_till_done()
    await tick(hass, freezer, 5)
    assert published(mqtt_mock) == ['{"text":"a"}', '{"text":"b"}', '{"text":"a"}']


async def test_clock_reboot_republishes(
    hass: HomeAssistant, mqtt_mock: MqttMockHAClient, mock_entry: MockConfigEntry
) -> None:
    """A lower uptime means the clock restarted and lost its apps."""
    await setup_entry(hass, mock_entry)

    async_fire_mqtt_message(hass, f"{PREFIX}/stats", '{"uptime": 500}')
    await hass.async_block_till_done()
    async_fire_mqtt_message(hass, f"{PREFIX}/stats", '{"uptime": 510}')
    await hass.async_block_till_done()
    assert published(mqtt_mock) == ['{"text":"a"}']

    async_fire_mqtt_message(hass, f"{PREFIX}/stats", '{"uptime": 3}')
    await hass.async_block_till_done()
    assert published(mqtt_mock) == ['{"text":"a"}', '{"text":"a"}']


async def test_switch_and_refresh_service(
    hass: HomeAssistant, mqtt_mock: MqttMockHAClient, mock_entry: MockConfigEntry
) -> None:
    """The switch removes and restores the app; refresh republishes."""
    await setup_entry(hass, mock_entry)

    await hass.services.async_call(
        "switch", SERVICE_TURN_OFF, {ATTR_ENTITY_ID: SWITCH}, blocking=True
    )
    assert hass.states.get(SWITCH).state == "off"
    assert published(mqtt_mock) == ['{"text":"a"}', ""]

    # Refresh ignores disabled apps.
    await hass.services.async_call(DOMAIN, "refresh", blocking=True)
    assert published(mqtt_mock) == ['{"text":"a"}', ""]

    await hass.services.async_call(
        "switch", SERVICE_TURN_ON, {ATTR_ENTITY_ID: SWITCH}, blocking=True
    )
    await hass.async_block_till_done()
    assert published(mqtt_mock) == ['{"text":"a"}', "", '{"text":"a"}']

    await hass.services.async_call(DOMAIN, "refresh", blocking=True)
    assert published(mqtt_mock)[-1] == '{"text":"a"}'
    assert len(published(mqtt_mock)) == 4


async def test_switch_state_survives_reload(
    hass: HomeAssistant, mqtt_mock: MqttMockHAClient, mock_entry: MockConfigEntry
) -> None:
    """A disabled app stays disabled (and off the clock) after a reload."""
    await setup_entry(hass, mock_entry)
    await hass.services.async_call(
        "switch", SERVICE_TURN_OFF, {ATTR_ENTITY_ID: SWITCH}, blocking=True
    )

    assert await hass.config_entries.async_reload(mock_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(SWITCH).state == "off"
    assert '{"text":"a"}' not in published(mqtt_mock)[2:]


async def test_removing_app_removes_it_from_clock(
    hass: HomeAssistant,
    mqtt_mock: MqttMockHAClient,
    mock_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Deleting the subentry deletes the app and its switch."""
    await setup_entry(hass, mock_entry)

    assert hass.config_entries.async_remove_subentry(mock_entry, "app_demo")
    await hass.async_block_till_done()

    assert published(mqtt_mock)[-1] == ""
    assert entity_registry.async_get(SWITCH) is None
    assert mock_entry.state is ConfigEntryState.LOADED


async def test_removing_clock_removes_apps(
    hass: HomeAssistant, mqtt_mock: MqttMockHAClient, mock_entry: MockConfigEntry
) -> None:
    """Deleting the clock clears its apps."""
    await setup_entry(hass, mock_entry)

    await hass.config_entries.async_remove(mock_entry.entry_id)
    await hass.async_block_till_done()

    assert published(mqtt_mock)[-1] == ""


async def test_unload_leaves_apps(
    hass: HomeAssistant, mqtt_mock: MqttMockHAClient, mock_entry: MockConfigEntry
) -> None:
    """Unloading (e.g. a restart) does not blank the clock."""
    await setup_entry(hass, mock_entry)

    assert await hass.config_entries.async_unload(mock_entry.entry_id)
    await hass.async_block_till_done()

    assert published(mqtt_mock) == ['{"text":"a"}']
    assert mock_entry.state is ConfigEntryState.NOT_LOADED
