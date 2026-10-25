<div align="center">

# Awtrix Studio

**Put anything from Home Assistant on your AWTRIX clock, and let it update itself.**
No automations, no blueprints, no YAML.

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=3615nulsi&repository=ha-awtrix-studio&category=integration)

[![Validate](https://github.com/3615nulsi/ha-awtrix-studio/actions/workflows/validate.yml/badge.svg)](https://github.com/3615nulsi/ha-awtrix-studio/actions/workflows/validate.yml)
[![Tests](https://github.com/3615nulsi/ha-awtrix-studio/actions/workflows/tests.yml/badge.svg)](https://github.com/3615nulsi/ha-awtrix-studio/actions/workflows/tests.yml)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories)

🇫🇷 [Lire en français](README.fr.md)

![The Awtrix Studio panel](https://raw.githubusercontent.com/3615nulsi/ha-awtrix-studio/main/docs/images/overview-en.png)

</div>

## ✨ What you get

- **A panel in your sidebar** that shows what your clock displays right now, every app with a live thumbnail, and a switch to turn each one on or off.
- **Apps in a few clicks.** Pick a sensor, an icon and a color. Want the color to slide from green to red as CO2 rises? Pick a gradient. A battery level? Add a progress bar.
- **Every LaMetric icon, nothing to upload.** Search the LaMetric gallery right from the editor: Awtrix Studio sends the icon along with the app, so you no longer have to load icons onto the clock first.
- **A live preview while you edit**, and a button to try your app on the real clock before saving.
- **Several pages per app** that alternate on their own, like "next tram" then "the one after".
- **The three colored indicators** of the clock, driven the same way.
- **A healthier Home Assistant.** Apps update only when their data changes and leave nothing in your history database. The usual "automation every few seconds" approach can write hundreds of thousands of entries a day.

## 🚀 Get started in 3 steps

You need Home Assistant 2025.8 or newer, the [MQTT integration](https://www.home-assistant.io/integrations/mqtt/), and an [AWTRIX 3](https://blueforcer.github.io/awtrix3/) clock (such as the Ulanzi TC001) connected to the same MQTT broker.

1. **Install.** Click the **Open in HACS** button above, then **Download**, and restart Home Assistant.
   <details><summary>Without the button</summary>

   In HACS, open the ⋮ menu → **Custom repositories**, add `https://github.com/3615nulsi/ha-awtrix-studio` as an **Integration**, then search for **Awtrix Studio** and download it. Or copy `custom_components/awtrix_studio` into your configuration folder by hand.
   </details>

2. **Add your clock.** Go to **Settings → Devices & services → Add integration → Awtrix Studio**, and enter the clock's MQTT prefix (you'll find it in the clock's MQTT settings, for example `awtrix_1f1b94`).

3. **Create your first app.** Open **Awtrix Studio** in the sidebar, click **Add app**, pick a sensor… and watch it appear on your clock. 🎉

## 🖼️ A quick tour

### The overview

The top of the panel mirrors the clock's real screen. Below, each app has its own card with what it currently shows and where it stands: on screen, in the rotation, hidden because there is nothing to show, or turned off.

### Simple mode: no code at all

Choose an entity, add a label, an icon and colors, and you're done. The preview updates as you type.

![Simple mode editor](https://raw.githubusercontent.com/3615nulsi/ha-awtrix-studio/main/docs/images/simple-en.png)

| Setting | What it does |
|---|---|
| **Entity** | The sensor (or any entity) to show. |
| **Label** | Optional text before the value, like `CO2`. |
| **Icon** | **Pick an icon** searches the [LaMetric gallery](https://developer.lametric.com/icons); Awtrix Studio sends it with the app (animated icons are stored on the clock automatically, so that they play). You can also type the name of an icon stored on the clock. |
| **Text color** | The default color. |
| **Decimals** | Round the value, or leave empty to show it as is. |
| **Show the unit** | Adds `°C`, `%`, `kW`… after the value. |
| **Hide when the value is 0** | Handy for solar production at night. |
| **Progress bar** | A bar at the bottom of the screen, from the app's entity or another one, empty and full at the values you choose. It can follow the text color. |
| **Color according to the value** | **Fixed**, **steps** (up to two thresholds, each with its color), or a **gradient**: pick a ready-made one (*the higher, the worse*, *the lower, the worse*, *best in the middle*, *cold → hot*) and set its range, or make your own with 2 to 5 points. For temperatures, CO2, humidity or batteries, a sensible range is suggested. |

The app also leaves the rotation by itself while its entity is unavailable.

### Template mode: full control

For anything more creative (drawings, progress bars, several pages), write a Home Assistant template that produces the clock's JSON. The preview shows each page, alternates them like the clock does, and tells you right away if something is wrong.

![Template mode editor](https://raw.githubusercontent.com/3615nulsi/ha-awtrix-studio/main/docs/images/editor-en.png)

Started in simple mode and want to go further? **Convert to template mode** opens the generated template, ready to be extended.

### Display options

Every app, in either mode, has a **Display** section for the rest of the AWTRIX app settings: how long it stays on screen, how many times a long text scrolls, scroll speed, what the icon does while the text scrolls, capitals, centering, text at the top, a rainbow or two-color gradient text, blinking or fading text, a background color, one of the clock's 19 background effects (with its speed, palette and blending), a weather overlay (snow, rain, storm…), and whether the clock keeps the app after it restarts. Leave a setting alone and the clock's own setting applies. In template mode they are defaults: a key your template sets itself wins.

### Order of the apps

**Order** lists the whole loop of the clock, its built-in apps (time, date, temperature…) and apps pushed by anything else included. Drag the apps or use the arrows, then save. The clock follows this order from then on: when an app comes back after being hidden, it goes back to its place instead of the end of the loop.

AWTRIX can only reorder apps through its web page, so this uses the address the clock reports over MQTT, like animated icons. If the web page cannot be reached (or is password protected), the order is kept and applied as soon as it can be.

### Indicators

The clock has three small colored lights on the right edge of its screen. Light one up while a door is open, show your solar surplus as a color, signal new mail… In simple mode, it's either "lit in this color while this entity is in this state", or "always lit, with a color that follows this value" using the same gradients as apps. Blink or fade are optional.

### Share and copy apps

**Export** saves the apps and indicators you pick to a small JSON file, or copies it so you can paste it in a forum post. **Import** reads such a file on another clock (or another Home Assistant) and shows you exactly what will happen before anything changes: names already taken get a free name or can replace the existing app, entities that don't exist on this installation are listed, and templates can be read before you accept them.

Simple apps describe *what* to show, not how a firmware draws it, so they also move between AWTRIX 3 and AWTRIX NG. Template apps contain AWTRIX 3 JSON and are flagged when imported on another firmware.

## 📝 Template examples

<details>
<summary><b>One page</b></summary>

```jinja
{"text": "{{ states('sensor.outdoor_temperature') | round(1) }}°", "icon": "2355"}
```
</details>

<details>
<summary><b>Several pages that alternate</b></summary>

Render a list: each item is a page.

```jinja
{{ [
  {"text": states('sensor.outdoor_temperature') ~ "°", "icon": "2355"},
  {"text": states('sensor.outdoor_humidity') ~ "%", "icon": "2423"}
] | tojson }}
```
</details>

<details>
<summary><b>Only when there is something to show</b></summary>

Render `[]` and the app leaves the rotation until there is something again.

```jinja
{% set n = states('sensor.unread_mail') | int(0) %}
{{ ([{"text": n ~ " mails", "icon": "51"}] if n > 0 else []) | tojson }}
```
</details>

<details>
<summary><b>The next two trams, with a pixel-drawn badge</b></summary>

Shows the next departure, then the following one, with one or two dots at the bottom to tell them apart. The departures come from a sensor such as the one provided by [ha-tam-montpellier](https://github.com/3615nulsi/ha-tam-montpellier).

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
</details>

<details>
<summary><b>An indicator showing your solar surplus</b></summary>

Blue while exporting, green to red while importing. Simple mode gets close with a custom gradient (blue at -2 kW, green at 0, yellow at 0.5, red at 3); this template gives finer control.

```jinja
{%- set w = states('sensor.grid_power') | float(0) * 1000 -%}
{%- if w < 0 -%}
  {"color": [0, 150, {{ (150 + [w | abs, 2000] | min / 2000 * 105) | int }}]}
{%- elif w <= 500 -%}
  {"color": [{{ (w / 500 * 255) | int }}, 255, 0]}
{%- else -%}
  {"color": [255, {{ (255 - ([w, 3000] | min - 500) / 2500 * 255) | int }}, 0]}
{%- endif -%}
```
</details>

Every key of the [AWTRIX custom app API](https://blueforcer.github.io/awtrix3/#/api?id=custom-apps-and-notifications) works: `text`, `color`, `icon`, `draw`, `progress`, `blinkText`, `effect`, and so on. Write `"icon": "lametric:2422"` to use an icon of the LaMetric gallery without uploading it to the clock.

## ❓ FAQ

<details>
<summary><b>Why not just use an automation?</b></summary>

You can, and that's how most people do it today. But an automation that refreshes the clock every few seconds runs tens of thousands of times a day, and each run is written to your history database: the automation's state, an event, and a copy of every message sent. Over time, this bloats the database and makes history and energy graphs slow to open. Awtrix Studio sends a message only when what's displayed actually changes, and writes nothing to the database.
</details>

<details>
<summary><b>Is the preview exactly what the clock shows?</b></summary>

The simulated preview is close but simplified (font, scrolling; background effects and weather overlays are only named). For the exact result, switch to the **Real screen** tab, or use **Send to the clock to test**.
</details>

<details>
<summary><b>Does the screen mirror slow anything down?</b></summary>

No. The clock is only asked for its screen once per second, and only while the panel is open. Nothing is written to the database.
</details>

<details>
<summary><b>Can I keep my existing automations or blueprints?</b></summary>

Yes. Awtrix Studio only touches the apps and indicators you create with it, so everything else keeps working.
</details>

<details>
<summary><b>Does it work with AWTRIX NG?</b></summary>

Yes, including the Ulanzi TC002, which runs AWTRIX NG. Pick **Detect automatically** when adding the clock. Simple apps, indicators and display options are written in NG's own JSON for you, the loop order is stored by the clock, and animated icons play. In template mode, write NG's JSON: the clock refuses unknown keys, and the panel shows what it refused. The simulated preview does not draw NG drawings or the TC002's larger screen yet; the **Real screen** tab does.
</details>

<details>
<summary><b>What happens when the clock or Home Assistant restarts?</b></summary>

Apps are sent again automatically, as well as when MQTT reconnects.
</details>

## 🔒 Security

- Only administrators can see the panel and use its features.
- Whatever you type in simple mode is always treated as text, never as code. Entities, colors and numbers are checked before use.
- App names that end up in MQTT topics are limited to letters, digits, `-` and `_`.
- The panel never inserts raw HTML: everything is displayed as plain text.
- Template mode runs regular Home Assistant templates, with the same safeguards as anywhere else in Home Assistant.

<details>
<summary><h2>🛠️ Under the hood</h2></summary>

- Each app's template is tracked by Home Assistant's template engine: it re-renders only when an entity it uses changes.
- Data changes are throttled to at most one message per second per app.
- AWTRIX announces the app on screen on `<prefix>/stats/currentApp`; by default, pages only alternate while that's the app being shown.
- The clock's uptime, read from `<prefix>/stats`, reveals a reboot; apps are then sent again.
- Messages go straight to the MQTT client: no service calls, no events.
- Each app and indicator has a **switch** entity: turning it off removes the app from the clock (or turns the indicator off) and keeps its settings. Its state survives restarts.
- The `awtrix_studio.refresh` action sends every enabled app and indicator again.
- There is deliberately no "current page" or "last update" sensor: those would write to the database constantly, which is exactly what this integration avoids.

| Template app option | Default | What it does |
|---|---|---|
| Time per page | 1.5 s | How long each page stays on screen. |
| Alternate pages only while on screen | On | Keeps only the first page up to date while another app is shown. |
| Hide when empty | On | Removes the app from the rotation while there is nothing to show. |
| Lifetime | 0 (off) | The clock drops the app if Home Assistant stops refreshing it. |

</details>

## 🤝 Contributing

Bug reports, ideas and pull requests are welcome in the [issues](https://github.com/3615nulsi/ha-awtrix-studio/issues). Released under the [MIT license](LICENSE).

---

<div align="center">

Fabriqué à Montpellier avec amour <3

</div>
