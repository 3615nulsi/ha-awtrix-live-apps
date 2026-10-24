# Awtrix Studio

[![Validate](https://github.com/3615nulsi/ha-awtrix-studio/actions/workflows/validate.yml/badge.svg)](https://github.com/3615nulsi/ha-awtrix-studio/actions/workflows/validate.yml)
[![Tests](https://github.com/3615nulsi/ha-awtrix-studio/actions/workflows/tests.yml/badge.svg)](https://github.com/3615nulsi/ha-awtrix-studio/actions/workflows/tests.yml)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories)

Custom apps and indicators for your [AWTRIX 3](https://blueforcer.github.io/awtrix3/)
clock that **live on their own**: describe them once, from a simple form or with a
Home Assistant template, and they stay up to date on the clock. No automation, no
blueprint, no `time_pattern`.

## Why

The usual way to show Home Assistant data on an AWTRIX clock is an automation that
publishes JSON over MQTT, often every few seconds. It works, but every run writes
to your database: the automation's state, an `automation_triggered` event, and a
`call_service` event per publication carrying the whole payload. An app that
alternates two pages every 1.5 seconds runs about 30,000 times a day and can grow
the recorder database by hundreds of megabytes, slowing down history and
statistics for the whole house.

Awtrix Studio does the same job without any of that:

- **Simple mode for everyday apps.** Pick an entity, an icon and colors, with
  optional color thresholds. No template to write.
- **Template mode for everything else.** The template renders the app's JSON,
  exactly as AWTRIX expects it. Every firmware feature (`draw`, `icon`,
  `blinkText`, gradients…) is available as soon as the firmware supports it.
- **Indicators too.** The three colored indicators get the same treatment.
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

## The panel

Awtrix Studio adds an **Awtrix Studio** entry to the sidebar (for
administrators):

- **Live mirror** of the clock's real screen, with previous / next app controls.
  The clock is only asked for its screen while the panel is open.
- **One card per app** with a live thumbnail of what it shows, its status (on
  screen, in the rotation, hidden, failing) and its on/off switch.
- **Indicators** at a glance.
- **Editor** for simple and template modes with a **live preview**: a simulated
  screen that updates as you type and alternates pages like the clock, a
  real-screen tab, the JSON sent for each page, and **Send to the clock to test**
  (the real content comes back after 15 seconds).

The simulated preview is an approximation (font, scrolling and effects are
simplified); the real-screen tab shows the exact result.

## Setup

1. **Settings → Devices & services → Add integration → Awtrix Studio.**
2. Pick the firmware and enter the clock's **MQTT prefix**, as set in the clock's
   MQTT settings (for example `awtrix_1f1b94`).
3. Open the **Awtrix Studio** panel in the sidebar and add apps and indicators
   from there. The same can be done from the integration's card with **Add app**
   or **Add indicator**.

Any app or indicator can be edited later. A simple one can also be **converted to
template mode**: the form opens with the generated template, ready to be extended.

### Simple apps

| Option | Description |
|---|---|
| App name | Name of the app on the clock. Letters, digits, `-` and `_`. Cannot be changed later. |
| Entity | The entity whose state is shown. |
| Label | Optional text before the value, for example `CO2`. |
| Icon | LaMetric icon ID (for example `2422`) or the name of an icon file on the clock. |
| Text color | Default color of the text. |
| Decimals | Optional rounding of numeric values. |
| Show the unit | Appends the entity's unit, with no space before `°` and `%`, like Home Assistant. |
| Hide when the value is 0 | Removes the app from the rotation at zero (solar production at night…). |
| Thresholds | Up to two values above which the text switches to another color. |

The app always leaves the rotation while the entity is unavailable or unknown.

For example, a CO2 monitor in green, orange above 800 ppm and red above 1200 ppm
is three colors and two thresholds: no template needed.

### Template apps

| Option | Default | Description |
|---|---|---|
| App name | — | Name of the app on the clock (`tram` → `<prefix>/custom/tram`). Letters, digits, `-` and `_`. Cannot be changed later. |
| Template | — | Jinja template rendering a JSON object (one page) or a list of objects (several pages). |
| Time per page | 1.5 s | How long each page is shown when the app has several pages. |
| Alternate pages only while on screen | On | While another app is displayed, only the first page is kept up to date. Saves most of the MQTT traffic. |
| Hide when empty | On | Removes the app from the clock's rotation while the template renders no page. |
| Lifetime | 0 (off) | Sets AWTRIX's `lifetime` so the clock drops the app if Home Assistant stops refreshing it. The integration refreshes it in time while running. |

## Indicators

AWTRIX 3 has three colored indicators on the right edge of the screen: 1 in the
top corner, 2 in the middle, 3 in the bottom corner.

- **Simple:** the indicator is lit, with a color and an optional blink or fade,
  while an entity is in a given state (`on`, `open`, `home`…), and off otherwise.
- **Template:** the template renders the indicator's JSON: `color` as a hex string
  or an RGB list, optionally `blink` or `fade` in milliseconds. Render `{}` to turn
  it off.

```jinja
{#- Blue while exporting, green to red while importing. -#}
{%- set w = states('sensor.grid_power') | float(0) * 1000 -%}
{%- if w < 0 -%}
  {"color": [0, 150, {{ (150 + [w | abs, 2000] | min / 2000 * 105) | int }}]}
{%- elif w <= 500 -%}
  {"color": [{{ (w / 500 * 255) | int }}, 255, 0]}
{%- else -%}
  {"color": [255, {{ (255 - ([w, 3000] | min - 500) / 2500 * 255) | int }}, 0]}
{%- endif -%}
```

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

Each app and indicator gets one **switch**. Turning it off removes the app from the
clock (or turns the indicator off) and keeps its configuration; turning it on brings
it back. Its state is restored after a restart.

There is deliberately no "current page" or "last update" sensor: those would write
to the database on every page, which is exactly what this integration avoids.

| Service | Description |
|---|---|
| `awtrix_studio.refresh` | Publishes every enabled app and indicator again. |

## How it works

- Templates are tracked with Home Assistant's template engine; a new render only
  happens when an entity used by the template changes.
- Data changes are throttled to at most one publication per second per app.
- AWTRIX announces the app on screen on `<prefix>/stats/currentApp`; pages only
  alternate while that is the app.
- The clock's uptime, read from `<prefix>/stats`, reveals a reboot; the apps are
  then published again.
- Publications go straight to the MQTT client, so they create no events.

## Security

- Everything typed in simple mode is inserted in the generated template as an
  escaped string, never as code; entity ids, colors and numbers are validated.
- Names that end up in MQTT topics are restricted to letters, digits, `-` and `_`.
- The panel and its WebSocket commands are for administrators only, and the panel
  never inserts HTML: every value is displayed as text.
- Template mode runs Home Assistant templates, with the same sandbox and rights as
  any other template.

## Supported firmware

| Firmware | Status |
|---|---|
| AWTRIX 3 | Supported |
| AWTRIX NG | Planned. Its API is different, so templates will use NG's own JSON fields. |

## License

[MIT](LICENSE)
