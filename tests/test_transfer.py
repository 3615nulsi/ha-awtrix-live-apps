"""Tests for exporting and importing apps and indicators."""

from __future__ import annotations

import json
from typing import Any

from homeassistant.config_entries import ConfigSubentryDataWithId
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import (
    MqttMockHAClient,
    WebSocketGenerator,
)

from custom_components.awtrix_studio.const import DOMAIN

PREFIX = "awtrix_test"

TEMPLATE_APP = {
    "mode": "template",
    "app_name": "demo",
    "template": '{"text": "{{ states(\'sensor.temp\') }}"}',
    "page_interval": 1.5,
    "cycle_only_on_screen": True,
    "hide_when_empty": True,
    "lifetime": 0,
}
SIMPLE_APP = {
    "mode": "simple",
    "app_name": "co2",
    "entity_id": "sensor.co2",
    "label": "",
    "icon": "",
    "color": [255, 255, 255],
    "show_unit": True,
    "hide_when_zero": False,
    "color_mode": "gradient",
    "gradient": "high_bad",
    "gradient_min": 400.0,
    "gradient_max": 1500.0,
}
INDICATOR = {
    "mode": "simple",
    "indicator": "1",
    "entity_id": "input_boolean.mail",
    "color_mode": "state",
    "active_state": "on",
    "color": [211, 87, 254],
    "effect": "none",
    "effect_interval": 1000,
}


@pytest.fixture
def expected_lingering_timers() -> bool:
    """The mocked MQTT client leaves its periodic housekeeping timer behind."""
    return True


def _subentry(data: dict[str, Any], kind: str, sid: str) -> ConfigSubentryDataWithId:
    is_app = kind == "app"
    return ConfigSubentryDataWithId(
        data=data,
        subentry_id=sid,
        subentry_type=kind,
        title=data["app_name"] if is_app else f"Indicator {data['indicator']}",
        unique_id=data["app_name"] if is_app else f"indicator:{data['indicator']}",
    )


async def _clock(
    hass: HomeAssistant, prefix: str, subentries: list[ConfigSubentryDataWithId]
) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=prefix,
        unique_id=prefix,
        data={"firmware": "awtrix3", "prefix": prefix},
        subentries_data=subentries,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.fixture
async def source(hass: HomeAssistant, mqtt_mock: MqttMockHAClient) -> MockConfigEntry:
    """A clock with a template app, a simple app and an indicator."""
    hass.states.async_set("sensor.temp", "21")
    hass.states.async_set("sensor.co2", "950")
    hass.states.async_set("input_boolean.mail", "on")
    return await _clock(
        hass,
        PREFIX,
        [
            _subentry(TEMPLATE_APP, "app", "s_demo"),
            _subentry(SIMPLE_APP, "app", "s_co2"),
            _subentry(INDICATOR, "indicator", "s_ind1"),
        ],
    )


async def _ws(client: Any, message: dict[str, Any]) -> Any:
    await client.send_json_auto_id(message)
    response = await client.receive_json()
    assert response["success"], response
    return response["result"]


async def test_export(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, source: MockConfigEntry
) -> None:
    """Simple items are firmware-neutral; templates carry their firmware."""
    client = await hass_ws_client(hass)
    doc = await _ws(
        client, {"type": "awtrix_studio/export", "entry_id": source.entry_id}
    )
    assert doc["awtrix_studio"] == 1
    assert doc["items"] == [
        {"type": "app", **TEMPLATE_APP, "firmware": "awtrix3"},
        {"type": "app", **SIMPLE_APP},
        {"type": "indicator", **INDICATOR},
    ]
    # Round-trips through JSON as a file would.
    assert json.loads(json.dumps(doc)) == doc

    doc = await _ws(
        client,
        {
            "type": "awtrix_studio/export",
            "entry_id": source.entry_id,
            "subentry_ids": ["s_co2"],
        },
    )
    assert [item["app_name"] for item in doc["items"]] == ["co2"]


async def test_import_to_another_clock(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    source: MockConfigEntry,
    mqtt_mock: MqttMockHAClient,
) -> None:
    """Everything lands on an empty clock, under the same names."""
    client = await hass_ws_client(hass)
    doc = await _ws(
        client, {"type": "awtrix_studio/export", "entry_id": source.entry_id}
    )
    target = await _clock(hass, "awtrix_other", [])

    plan = await _ws(
        client,
        {
            "type": "awtrix_studio/import",
            "entry_id": target.entry_id,
            "document": doc,
            "dry_run": True,
        },
    )
    assert [(p["action"], p["target"], p["error"]) for p in plan["items"]] == [
        ("add", "demo", None),
        ("add", "co2", None),
        ("add", "1", None),
    ]
    assert plan["imported"] == 0
    assert not target.subentries

    result = await _ws(
        client,
        {
            "type": "awtrix_studio/import",
            "entry_id": target.entry_id,
            "document": doc,
        },
    )
    assert result["imported"] == 3
    await hass.async_block_till_done()
    imported = {s.title: dict(s.data) for s in target.subentries.values()}
    assert imported == {
        "demo": TEMPLATE_APP,
        "co2": SIMPLE_APP,
        "Indicator 1": INDICATOR,
    }
    payloads = [
        c.args[1]
        for c in mqtt_mock.async_publish.call_args_list
        if c.args[0] == "awtrix_other/custom/co2"
    ]
    assert payloads
    assert json.loads(payloads[-1]) == {"text": "950", "color": [255, 200, 0]}


async def test_import_conflicts(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, source: MockConfigEntry
) -> None:
    """On the same clock: free names by default, or replace on request."""
    client = await hass_ws_client(hass)
    doc = await _ws(
        client, {"type": "awtrix_studio/export", "entry_id": source.entry_id}
    )

    plan = await _ws(
        client,
        {
            "type": "awtrix_studio/import",
            "entry_id": source.entry_id,
            "document": doc,
            "dry_run": True,
        },
    )
    assert [(p["action"], p["target"]) for p in plan["items"]] == [
        ("add", "demo_2"),
        ("add", "co2_2"),
        ("add", "2"),
    ]

    choices = [
        {"action": "replace", "target": "demo"},
        {"action": "add", "target": "co2"},
        {"action": "skip"},
    ]
    modified = {**doc, "items": [dict(i) for i in doc["items"]]}
    modified["items"][0]["page_interval"] = 5
    plan = await _ws(
        client,
        {
            "type": "awtrix_studio/import",
            "entry_id": source.entry_id,
            "document": modified,
            "choices": choices,
        },
    )
    assert [(p["action"], p["error"]) for p in plan["items"]] == [
        ("replace", None),
        ("skip", "app_name_exists"),
        ("skip", None),
    ]
    assert plan["imported"] == 1
    await hass.async_block_till_done()
    assert len(source.subentries) == 3
    assert source.subentries["s_demo"].data["page_interval"] == 5


@pytest.mark.parametrize(
    ("document", "error"),
    [
        ({"items": []}, "not_an_export"),
        ({"awtrix_studio": "1", "items": [{}]}, "not_an_export"),
        ({"awtrix_studio": 99, "items": [{}]}, "newer_version"),
        ({"awtrix_studio": 1, "items": []}, "no_items"),
        ({"awtrix_studio": 1, "items": [{}] * 65}, "too_many_items"),
    ],
)
async def test_import_rejects_other_files(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    source: MockConfigEntry,
    document: dict[str, Any],
    error: str,
) -> None:
    """Only exports are accepted."""
    client = await hass_ws_client(hass)
    result = await _ws(
        client,
        {
            "type": "awtrix_studio/import",
            "entry_id": source.entry_id,
            "document": document,
        },
    )
    assert result["error"] == error


async def test_import_is_validated(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, source: MockConfigEntry
) -> None:
    """A crafted file is checked item by item like the editor's input."""
    client = await hass_ws_client(hass)
    doc = {
        "awtrix_studio": 1,
        "items": [
            {"type": "script", "sequence": []},
            {**SIMPLE_APP, "type": "app", "app_name": "x", "entity_id": "sensor.x')"},
            {**SIMPLE_APP, "type": "app", "app_name": "a/b #", "evil": "<script>"},
            {**TEMPLATE_APP, "type": "app", "app_name": "t", "firmware": "awtrix_ng"},
            {**INDICATOR, "type": "indicator", "indicator": "7"},
            {**SIMPLE_APP, "type": "app", "app_name": "dup"},
            {**SIMPLE_APP, "type": "app", "app_name": "dup"},
        ],
    }
    result = await _ws(
        client,
        {
            "type": "awtrix_studio/import",
            "entry_id": source.entry_id,
            "document": doc,
        },
    )
    items = result["items"]
    assert items[0]["error"] == "unknown_type"
    assert items[1]["error"] == "invalid_entity"
    assert (items[2]["action"], items[2]["target"]) == ("add", "a_b__")
    assert items[3]["warnings"] == ["other_firmware"]
    assert items[3]["template"] == TEMPLATE_APP["template"]
    assert items[4]["error"] == "invalid_value"
    assert (items[5]["target"], items[6]["target"]) == ("dup", "dup_2")
    assert result["imported"] == 4
    await hass.async_block_till_done()
    stored = {s.title: dict(s.data) for s in source.subentries.values()}
    assert "evil" not in stored["a_b__"]
    assert "firmware" not in stored["t"]
    assert set(stored) == {"demo", "co2", "Indicator 1", "a_b__", "t", "dup", "dup_2"}


async def test_missing_entities_are_reported(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, source: MockConfigEntry
) -> None:
    """Entities that do not exist on this installation are listed."""
    client = await hass_ws_client(hass)
    doc = {
        "awtrix_studio": 1,
        "items": [
            {**SIMPLE_APP, "type": "app", "app_name": "a", "entity_id": "sensor.nope"},
            {
                **TEMPLATE_APP,
                "type": "app",
                "app_name": "b",
                "template": "{{ {'text': states('sensor.gone')} | tojson }}",
                "firmware": "awtrix3",
            },
        ],
    }
    result = await _ws(
        client,
        {
            "type": "awtrix_studio/import",
            "entry_id": source.entry_id,
            "document": doc,
            "dry_run": True,
        },
    )
    assert [p["missing_entities"] for p in result["items"]] == [
        ["sensor.nope"],
        ["sensor.gone"],
    ]
    assert [p["warnings"] for p in result["items"]] == [[], []]


async def test_files_from_awtrix_studio_still_import(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, source: MockConfigEntry
) -> None:
    """Exports made before the rename keep working."""
    client = await hass_ws_client(hass)
    doc = {
        "awtrix_studio": 1,
        "items": [{**SIMPLE_APP, "type": "app", "app_name": "legacy"}],
    }
    result = await _ws(
        client,
        {
            "type": "awtrix_studio/import",
            "entry_id": source.entry_id,
            "document": doc,
            "dry_run": True,
        },
    )
    assert result["error"] is None
    assert [p["target"] for p in result["items"]] == ["legacy"]
