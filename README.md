# Awtrix Studio

[![Validate](https://github.com/3615nulsi/ha-awtrix-studio/actions/workflows/validate.yml/badge.svg)](https://github.com/3615nulsi/ha-awtrix-studio/actions/workflows/validate.yml)
[![Tests](https://github.com/3615nulsi/ha-awtrix-studio/actions/workflows/tests.yml/badge.svg)](https://github.com/3615nulsi/ha-awtrix-studio/actions/workflows/tests.yml)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories)

Custom apps for your [AWTRIX 3](https://blueforcer.github.io/awtrix3/) clock that
**live on their own**: describe an app once with a Home Assistant template, and it
stays up to date on the clock. No automation, no blueprint, no `time_pattern`.

## Why

The usual way to show Home Assistant data on an AWTRIX clock is an automation that
publishes JSON over MQTT, often every few seconds. It works, but every run writes
to your database: the automation's state, an `automation_triggered` event, and a
`call_service` event per publication carrying the whole payload. An app that
alternates two pages every 1.5 seconds runs about 30,000 times a day and can grow
the recorder database by hundreds of megabytes, slowing down history and
statistics for the whole house.

Awtrix Studio does the same job without any of that:

- **Template-driven.** The template renders the app's JSON, exactly as AWTRIX
  expects it. Every firmware feature (`draw`, `icon`, `blinkText`, gradients…) is
  available as soon as the firmware supports it.
- **Publishes only what changes.** Entities used in the template are tracked; an
  identical render is never sent twice.
- **Multiple pages built in.** Render a list and the pages alternate, by default
  only while the app is on screen.
- **Leaves no trace in the recorder.** No automation runs, no service calls, no
  entity state changing on every update.
- **Self-healing.** Apps are sent again when the clock or Home Assistant restarts,
  or when MQTT reconnects.

## Requirements

- Home Assistant 2025.8 or newer.
- The [MQTT integration](https://www.home-assistant.io/integrations/mqtt/), connected
  to the broker your clock uses.
- A clock running AWTRIX 3 with MQTT enabled. AWTRIX NG support is planned.

## Installation

### HACS

1. In HACS, open the menu (⋮) → **Custom repositories**.
2. Add `https://github.com/3615nulsi/ha-awtrix-studio` with the type **Integration**.
3. Search for **Awtrix Studio**, download it, and restart Home Assistant.

### Manual

Copy `custom_components/awtrix_studio` into the `custom_components` folder of
your Home Assistant configuration, then restart Home Assistant.

## Setup

1. **Settings → Devices & services → Add integration → Awtrix Studio.**
2. Pick the firmware and enter the clock's **MQTT prefix**, as set in the clock's
   MQTT settings (for example `awtrix_1f1b94`).
3. On the integration's card, use **Add app** for each app you want on the clock.

### App options

| Option | Default | Description |
|---|---|---|
| App name | — | Name of the app on the clock (`tram` → `<prefix>/custom/tram`). Letters, digits, `-` and `_`. Cannot be changed later. |
| Template | — | Jinja template rendering a JSON object (one page) or a list of objects (several pages). |
| Time per page | 1.5 s | How long each page is shown when the app has several pages. |
| Alternate pages only while on screen | On | While another app is displayed, only the first page is kept up to date. Saves most of the MQTT traffic. |
| Hide when empty | On | Removes the app from the clock's rotation while the template renders no page. |
| Lifetime | 0 (off) | Sets AWTRIX's `lifetime` so the clock drops the app if Home Assistant stops refreshing it. The integration refreshes it in time while running. |

## Writing templates

The template must render **the AWTRIX custom app JSON**. See the
[AWTRIX 3 API documentation](https://blueforcer.github.io/awtrix3/#/api?id=custom-apps-and-notifications)
for every available key.

### One page

```jinja
{"text": "{{ states('sensor.outdoor_temperature') | round(1) }}°", "icon": "2355"}
```

### Several pages

Render a list; each object is a page. Using `tojson` keeps the output valid JSON:

```jinja
{{ [
  {"text": states('sensor.outdoor_temperature') ~ "°", "icon": "2355"},
  {"text": states('sensor.outdoor_humidity') ~ "%", "icon": "2423"}
] | tojson }}
```

### Nothing to show

Render `[]` (or `{}`): with **Hide when empty** on, the app leaves the rotation
until there is something to show again.

```jinja
{% set n = states('sensor.unread_mail') | int(0) %}
{{ ([{"text": n ~ " mails", "icon": "51"}] if n > 0 else []) | tojson }}
```

### Example: next two trams

Shows the next departure, then the following one, with one or two dots at the
bottom to tell them apart. The departures come from a sensor such as the one
provided by [ha-tam-montpellier](https://github.com/3615nulsi/ha-tam-montpellier).

```jinja
{%- set deps = state_attr('sensor.my_stop_next_tram', 'departures') or [] -%}
{%- set ns = namespace(pages=[]) -%}
{%- for d in deps[:2] -%}
  {%- set m = d.minutes | int -%}
  {%- set dots = [{"dp": [20, 7, "#EF7D00"]}] if loop.first
       else [{"dp": [19, 7, "#EF7D00"]}, {"dp": [21, 7, "#EF7D00"]}] -%}
  {%- set page = {"center": true, "draw": dots} -%}
  {%- if m == 0 -%}
    {%- set page = dict(page, text="Quai", blinkText=500) -%}
  {%- else -%}
    {%- set page = dict(page, text=m ~ " min") -%}
  {%- endif -%}
  {%- set ns.pages = ns.pages + [page] -%}
{%- endfor -%}
{{ ns.pages | tojson }}
```

With the defaults (1.5 s per page, alternate only on screen, hide when empty), the
two departures alternate while the app is displayed, and the app disappears at
night when no tram is scheduled.

## Entities and services

Each app gets one **switch**. Turning it off removes the app from the clock and
keeps its configuration; turning it on brings it back. Its state is restored after
a restart.

There is deliberately no "current page" or "last update" sensor: those would write
to the database on every page, which is exactly what this integration avoids.

| Service | Description |
|---|---|
| `awtrix_studio.refresh` | Publishes every enabled app again. |

## How it works

- Templates are tracked with Home Assistant's template engine; a new render only
  happens when an entity used by the template changes.
- Data changes are throttled to at most one publication per second per app.
- AWTRIX announces the app on screen on `<prefix>/stats/currentApp`; pages only
  alternate while that is the app.
- The clock's uptime, read from `<prefix>/stats`, reveals a reboot; the apps are
  then published again.
- Publications go straight to the MQTT client, so they create no events.

## Supported firmware

| Firmware | Status |
|---|---|
| AWTRIX 3 | Supported |
| AWTRIX NG | Planned. Its API is different, so templates will use NG's own JSON fields. |

## License

[MIT](LICENSE)
