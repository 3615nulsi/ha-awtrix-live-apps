// Awtrix Studio — sidebar panel.
//
// Plain Web Component, no build step and no dependency. Security rules:
// - the DOM is built with createElement/textContent only, never innerHTML;
// - user and clock data are only ever set as text, attribute values or canvas
//   colors (parsed into strict #RRGGBB first);
// - every action goes through admin-only WebSocket commands validated on the
//   server side.

import { addIndicators, drawMatrix, parseColor, renderPage, screenToPixels, WIDTH, HEIGHT } from "./matrix.js";
import { translator } from "./i18n.js";
import { MAX_STOPS, PRESETS, colorAt, cssGradient, formStops, presetCss, rgbToHex, suggestion } from "./gradients.js";

const PREVIEW_DEBOUNCE = 350;
const MIRROR_STALE_MS = 5000;

const STARTER_APP_TEMPLATE = `{#- Render a JSON object (one page) or a list of objects
    (pages that alternate). Any key of the AWTRIX custom app API works. -#}
{{ [
  {"text": now().strftime('%H:%M'), "color": "#FFFFFF"},
  {"text": states('sun.sun'), "color": "#FFB74D"}
] | tojson }}`;

const STARTER_INDICATOR_TEMPLATE = `{#- Render {"color": ...} to light the indicator
    (optionally with "blink" or "fade" in ms), or {} to turn it off. -#}
{%- if is_state('sun.sun', 'below_horizon') -%}
{"color": "#FF8C00", "fade": 2000}
{%- else -%}
{}
{%- endif -%}`;

// ------------------------------------------------------------------ helpers

function h(tag, props, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") el.className = value;
    else if (key.startsWith("on") && typeof value === "function") el.addEventListener(key.slice(2).toLowerCase(), value);
    else if (key === "value") el.value = value;
    else if (key === "checked") el.checked = Boolean(value);
    else el.setAttribute(key, value === true ? "" : String(value));
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

const SVG_NS = "http://www.w3.org/2000/svg";
const ICON_PATHS = {
  menu: "M3 6h18M3 12h18M3 18h18",
  back: "M15 18l-6-6 6-6",
  plus: "M12 5v14M5 12h14",
  prev: "M15 18l-6-6 6-6",
  next: "M9 6l6 6-6 6",
  refresh: "M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7",
};
function icon(name) {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("class", "icon");
  const path = document.createElementNS(SVG_NS, "path");
  path.setAttribute("d", ICON_PATHS[name]);
  svg.append(path);
  return svg;
}

function clear(el) {
  while (el.firstChild) el.firstChild.remove();
}

function toHex(value, fallback) {
  return parseColor(value, fallback).toLowerCase();
}

function numberOrEmpty(value) {
  if (value === "" || value === null || value === undefined) return "";
  const n = Number(value);
  return Number.isFinite(n) ? n : "";
}

function unsubscribe(promise) {
  if (promise) promise.then((unsub) => unsub()).catch(() => {});
}

const STYLE = `
[hidden] { display: none !important; }
:host { display: block; min-height: 100%; background: var(--primary-background-color, #f4f5f7);
  color: var(--primary-text-color, #1f2328); font-family: var(--ha-font-family-body, Roboto, system-ui, sans-serif); }
* { box-sizing: border-box; }
.toolbar { height: 56px; display: flex; align-items: center; gap: 8px; padding: 0 12px;
  background: var(--app-header-background-color, var(--primary-color, #03a9f4));
  color: var(--app-header-text-color, #fff); position: sticky; top: 0; z-index: 2; }
.toolbar h1 { margin: 0 8px; font-size: 20px; font-weight: 400; flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.toolbar select { font: inherit; font-size: 14px; padding: 6px 10px; border-radius: 8px; border: none; max-width: 50vw; }
.icon { width: 22px; height: 22px; fill: none; stroke: currentColor; stroke-width: 2.2; stroke-linecap: round; stroke-linejoin: round; }
.icon-btn { width: 44px; height: 44px; border: none; background: none; color: inherit; border-radius: 50%; display: inline-flex;
  align-items: center; justify-content: center; cursor: pointer; }
.icon-btn:hover { background: rgba(127,127,127,.15); }
main { max-width: 1240px; margin: 0 auto; padding: 20px 16px 48px; display: flex; flex-direction: column; gap: 20px; }
.card { background: var(--card-background-color, #fff); border: 1px solid var(--divider-color, #e3e5e8);
  border-radius: var(--ha-card-border-radius, 12px); }
.pad { padding: 18px; }
h2 { margin: 0; font-size: 17px; font-weight: 500; }
.muted { color: var(--secondary-text-color, #5f6368); font-size: 13px; }
.row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.between { justify-content: space-between; }
.btn { font: inherit; font-size: 14px; font-weight: 500; padding: 8px 14px; min-height: 40px; border-radius: 20px; cursor: pointer;
  border: 1px solid var(--divider-color, #c4c7cc); background: var(--card-background-color, #fff); color: var(--primary-text-color, #1f2328);
  display: inline-flex; align-items: center; gap: 6px; }
.btn:hover { filter: brightness(.96); }
.btn.primary { background: var(--primary-color, #0277bd); border-color: transparent; color: var(--text-primary-color, #fff); }
.btn.danger { color: var(--error-color, #db4437); }
.btn.small { min-height: 34px; padding: 6px 12px; font-size: 13px; }
.btn[disabled] { opacity: .5; cursor: default; }
.screen { background: #0b0b0d; border-radius: 12px; padding: 12px; display: inline-flex; box-shadow: inset 0 0 0 2px #26262b; max-width: 100%; overflow: hidden; }
.screen canvas { display: block; max-width: 100%; height: auto !important; image-rendering: pixelated; }
.live { display: flex; flex-wrap: wrap; gap: 24px; align-items: center; }
.live-info { flex: 1 1 260px; display: flex; flex-direction: column; gap: 12px; }
dl { margin: 0; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px 20px; }
dt { color: var(--secondary-text-color, #5f6368); font-size: 13px; }
dd { margin: 2px 0 0; font-weight: 500; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 14px; }
.app { padding: 12px; display: flex; flex-direction: column; gap: 10px; }
.app.current { border-color: var(--primary-color, #0277bd); }
.app .screen { padding: 8px; justify-content: center; }
.app.dim .screen { opacity: .45; }
.name { font-family: var(--ha-font-family-code, "Roboto Mono", monospace); font-weight: 500; }
.chip { font-size: 12px; padding: 3px 9px; border-radius: 10px; background: rgba(127,127,127,.15); }
.chip.simple { background: rgba(46,125,50,.15); }
.chip.template { background: rgba(94,53,177,.15); }
.status { font-size: 13px; font-weight: 500; }
.status.ok { color: var(--success-color, #2e7d32); }
.status.screen-on { color: var(--primary-color, #0277bd); }
.status.error { color: var(--error-color, #db4437); }
.switch { width: 40px; height: 24px; border-radius: 12px; border: none; padding: 3px; cursor: pointer; flex: none;
  background: var(--disabled-color, #9aa0a6); display: flex; justify-content: flex-start; }
.switch[aria-checked="true"] { background: var(--primary-color, #0277bd); justify-content: flex-end; }
.switch span { width: 18px; height: 18px; border-radius: 50%; background: #fff; display: block; }
.indicators { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 12px; }
.indicator { padding: 14px; display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
.indicator .grow { flex: 1 1 140px; min-width: 0; }
.indicator.free { border-style: dashed; }
.swatch { width: 26px; height: 26px; border-radius: 6px; flex: none; background: #26262b; }
.editor { display: flex; flex-wrap: wrap; gap: 20px; align-items: flex-start; }
.editor > .form { flex: 1 1 520px; min-width: 0; display: flex; flex-direction: column; gap: 16px; }
.editor > .preview { flex: 1 1 420px; min-width: 0; display: flex; flex-direction: column; gap: 16px; }
.tabs { display: inline-flex; border: 1px solid var(--divider-color, #c4c7cc); border-radius: 20px; overflow: hidden; align-self: flex-start; }
.tabs button { font: inherit; font-size: 14px; font-weight: 500; padding: 8px 18px; border: none; background: none; color: inherit; cursor: pointer; min-height: 40px; }
.tabs button[aria-selected="true"] { background: rgba(3,169,244,.18); color: var(--primary-color, #0277bd); }
.fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px 18px; }
.field { display: flex; flex-direction: column; gap: 5px; min-width: 0; }
.field.wide { grid-column: 1 / -1; }
.field label, .field .label { font-size: 14px; font-weight: 500; }
.field input[type=text], .field input[type=number], .field select, .field textarea {
  font: inherit; font-size: 15px; padding: 9px 11px; border-radius: 8px; width: 100%;
  border: 1px solid var(--divider-color, #c4c7cc); background: var(--card-background-color, #fff); color: var(--primary-text-color, #1f2328); }
.field textarea { font-family: var(--ha-font-family-code, "Roboto Mono", monospace); font-size: 13px; line-height: 1.55; min-height: 280px; resize: vertical; }
.field input[type=color] { width: 56px; height: 38px; padding: 2px; border-radius: 8px; border: 1px solid var(--divider-color, #c4c7cc); background: none; }
.check { display: flex; gap: 10px; align-items: flex-start; font-size: 15px; }
.check input { width: 20px; height: 20px; margin: 1px 0 0; flex: none; }
.error-text { color: var(--error-color, #db4437); font-size: 13px; min-height: 0; }
fieldset { border: 1px solid var(--divider-color, #e3e5e8); border-radius: 10px; padding: 12px 14px; margin: 0; display: flex; flex-direction: column; gap: 10px; }
legend { font-size: 14px; font-weight: 500; padding: 0 6px; }
pre { margin: 0; padding: 12px; border-radius: 8px; font-family: var(--ha-font-family-code, "Roboto Mono", monospace); font-size: 12px; line-height: 1.5;
  white-space: pre-wrap; word-break: break-word; max-height: 260px; overflow: auto; background: rgba(127,127,127,.1); }
.pills { display: flex; gap: 6px; flex-wrap: wrap; }
.pill { font-size: 12px; padding: 4px 10px; border-radius: 12px; background: rgba(127,127,127,.15); }
.pill.active { background: var(--primary-color, #0277bd); color: var(--text-primary-color, #fff); }
.banner { padding: 12px 16px; border-radius: 10px; background: rgba(219,68,55,.12); color: var(--error-color, #db4437); }
.feedback { font-size: 13px; color: var(--secondary-text-color, #5f6368); min-height: 18px; }
.color-body { display: flex; flex-direction: column; gap: 12px; }
.gradient-editor { display: flex; flex-direction: column; gap: 12px; }
.presets { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 8px; }
.preset { font: inherit; font-size: 13px; text-align: left; display: flex; flex-direction: column; gap: 6px; padding: 8px; cursor: pointer;
  border-radius: 10px; border: 1px solid var(--divider-color, #c4c7cc); background: var(--card-background-color, #fff); color: inherit; }
.preset[aria-checked="true"] { border-color: var(--primary-color, #0277bd); box-shadow: 0 0 0 1px var(--primary-color, #0277bd); }
.preset-swatch { height: 14px; border-radius: 7px; display: block; }
.preset-swatch.custom { background: repeating-linear-gradient(45deg, rgba(127,127,127,.25) 0 6px, rgba(127,127,127,.08) 6px 12px); }
.stops { display: flex; flex-direction: column; gap: 8px; }
.stop { flex-wrap: nowrap; }
.field .stop input.stop-value { width: 120px; flex: 0 0 120px; font: inherit; font-size: 15px; padding: 8px 10px; border-radius: 8px;
  border: 1px solid var(--divider-color, #c4c7cc); background: var(--card-background-color, #fff); color: inherit; }
.field .stop input[type=color] { width: 56px; height: 38px; padding: 2px; border-radius: 8px; border: 1px solid var(--divider-color, #c4c7cc); background: none; }
.gradient-track { position: relative; height: 22px; margin: 4px 11px 0; }
.gradient-bar { position: absolute; inset: 4px 0; border-radius: 7px; }
.gradient-bar.empty { background: rgba(127,127,127,.15); }
.gradient-marker { position: absolute; top: 0; width: 22px; height: 22px; margin-left: -11px; border-radius: 50%;
  border: 3px solid var(--card-background-color, #fff); box-shadow: 0 0 0 1px rgba(0,0,0,.35); }
@media (max-width: 600px) { .fields { grid-template-columns: minmax(0, 1fr); } dl { grid-template-columns: minmax(0, 1fr); } }
`;

// -------------------------------------------------------------------- panel

class AwtrixStudioPanel extends HTMLElement {
  constructor() {
    super();
    this._hass = null;
    this._ready = false;
    this._clocks = [];
    this._entryId = null;
    this._snapshot = null;
    this._view = { name: "overview" };
    this._cards = new Map();
    this._structure = "";
    this._screen = { pixels: null, at: 0 };
    this._subs = {};
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first && this.isConnected) this._init();
  }

  get hass() {
    return this._hass;
  }

  set narrow(value) {
    this._narrow = value;
    if (this._menuButton) this._menuButton.hidden = !value;
  }

  set route(_value) {}
  set panel(_value) {}

  connectedCallback() {
    if (!this._hass) return;
    if (!this._ready) this._init();
    else this._resume();
  }

  disconnectedCallback() {
    Object.keys(this._subs).forEach((key) => this._stop(key));
    clearInterval(this._cycleTimer);
    clearTimeout(this._previewTimer);
  }

  // ---------------------------------------------------------------- setup

  async _init() {
    this._ready = true;
    this.t = translator(this._hass.locale?.language || this._hass.language);
    const root = this.shadowRoot || this.attachShadow({ mode: "open" });
    clear(root);
    root.append(h("style", {}, STYLE));

    this._menuButton = h("button", { class: "icon-btn", "aria-label": this.t("menu"), onClick: () => this._toggleMenu() }, icon("menu"));
    this._menuButton.hidden = !this._narrow;
    this._backButton = h("button", { class: "icon-btn", "aria-label": this.t("back"), onClick: () => this._showOverview() }, icon("back"));
    this._backButton.hidden = true;
    this._title = h("h1", {}, this.t("title"));
    this._clockSelect = h("select", { "aria-label": this.t("clock"), onChange: (e) => this._selectClock(e.target.value) });
    root.append(h("div", { class: "toolbar" }, this._menuButton, this._backButton, this._title, this._clockSelect));
    this._main = h("main");
    root.append(this._main);

    try {
      this._clocks = await this._hass.callWS({ type: "awtrix_studio/clocks" });
    } catch (err) {
      this._clocks = [];
      this._banner(this.t("errors.request_failed", { detail: err.message || err.code || "" }));
    }
    clear(this._clockSelect);
    this._clocks.forEach((clock) => this._clockSelect.append(h("option", { value: clock.entry_id }, `${clock.title} · ${clock.firmware.toUpperCase()}`)));
    this._clockSelect.hidden = this._clocks.length < 2;

    if (!this._clocks.length) {
      clear(this._main);
      this._main.append(h("div", { class: "card pad" }, this.t("no_clock")));
      return;
    }
    let saved = null;
    try { saved = window.localStorage.getItem("awtrix_studio.clock"); } catch (_err) { saved = null; }
    const initial = this._clocks.find((c) => c.entry_id === saved) || this._clocks.find((c) => c.loaded) || this._clocks[0];
    this._selectClock(initial.entry_id);
  }

  _resume() {
    if (this._entryId) {
      this._subscribeSnapshot();
      if (this._view.name === "overview") this._subscribeScreen();
      else this._refreshPreview();
    }
  }

  _toggleMenu() {
    this.dispatchEvent(new Event("hass-toggle-menu", { bubbles: true, composed: true }));
  }

  _selectClock(entryId) {
    this._entryId = entryId;
    this._clockSelect.value = entryId;
    try { window.localStorage.setItem("awtrix_studio.clock", entryId); } catch (_err) { /* private mode */ }
    this._snapshot = null;
    this._structure = "";
    this._screen = { pixels: null, at: 0 };
    this._showOverview();
    this._subscribeSnapshot();
  }

  // -------------------------------------------------------- subscriptions

  _stop(key) {
    unsubscribe(this._subs[key]);
    delete this._subs[key];
  }

  _subscribe(key, message, callback) {
    this._stop(key);
    this._subs[key] = this._hass.connection.subscribeMessage(callback, message);
    this._subs[key].catch((err) => {
      if (key !== "screen") this._banner(this.t("errors.request_failed", { detail: err.message || err.code || "" }));
    });
  }

  _subscribeSnapshot() {
    this._subscribe("snapshot", { type: "awtrix_studio/subscribe", entry_id: this._entryId }, (snapshot) => {
      this._snapshot = snapshot;
      if (this._view.name === "overview") this._updateOverview();
    });
  }

  _subscribeScreen() {
    if (!this._snapshot?.features?.screen) return;
    this._subscribe("screen", { type: "awtrix_studio/screen", entry_id: this._entryId }, (event) => {
      this._screen = { pixels: screenToPixels(event.pixels), at: Date.now() };
      this._drawMirror();
      if (this._view.name === "edit" && this._previewTab === "real") this._drawPreview();
    });
  }

  async _call(message) {
    try {
      return await this._hass.callWS({ entry_id: this._entryId, ...message });
    } catch (err) {
      this._banner(this.t("errors.request_failed", { detail: err.message || err.code || "" }));
      return null;
    }
  }

  _banner(text) {
    if (!this._main) return;
    const banner = h("div", { class: "banner", role: "alert" }, text);
    this._main.prepend(banner);
    setTimeout(() => banner.remove(), 8000);
  }

  // ------------------------------------------------------------- overview

  _showOverview() {
    this._view = { name: "overview" };
    this._stop("preview");
    clearInterval(this._cycleTimer);
    this._backButton.hidden = true;
    this._title.textContent = this.t("title");
    this._clockSelect.hidden = this._clocks.length < 2;
    this._structure = "";
    this._cards = new Map();
    clear(this._main);

    this._mirrorCanvas = h("canvas", { role: "img", "aria-label": this.t("live_mirror") });
    this._mirrorCaption = h("span", { class: "muted" }, this.t("live_waiting"));
    this._currentApp = h("dd", {}, "—");
    this._rotation = h("dd", {}, "—");
    this._navRow = h("div", { class: "row" },
      h("button", { class: "btn", onClick: () => this._call({ type: "awtrix_studio/navigate", forward: false }) }, icon("prev"), this.t("previous_app")),
      h("button", { class: "btn", onClick: () => this._call({ type: "awtrix_studio/navigate", forward: true }) }, this.t("next_app"), icon("next")),
      h("button", { class: "btn", onClick: () => this._call({ type: "awtrix_studio/republish" }) }, icon("refresh"), this.t("republish")),
    );
    this._notLoaded = h("div", { class: "banner" }, this.t("not_loaded"));
    this._notLoaded.hidden = true;

    this._grid = h("div", { class: "grid" });
    this._indicatorRow = h("div", { class: "indicators" });

    this._main.append(
      this._notLoaded,
      h("section", { class: "card pad live", "aria-label": this.t("live_title") },
        h("div", { class: "row", style: "flex-direction:column;align-items:flex-start;gap:8px" },
          h("div", { class: "screen" }, this._mirrorCanvas), this._mirrorCaption),
        h("div", { class: "live-info" },
          h("h2", {}, this.t("live_title")),
          h("dl", {}, h("div", {}, h("dt", {}, this.t("current_app")), this._currentApp),
            h("div", {}, h("dt", {}, this.t("in_rotation")), this._rotation)),
          this._navRow)),
      h("section", { class: "row between" },
        h("h2", {}, this.t("apps")),
        h("button", { class: "btn primary", onClick: () => this._openEditor("app", null) }, icon("plus"), this.t("add_app"))),
      this._grid,
      h("h2", {}, this.t("indicators")),
      this._indicatorRow,
    );
    this._drawMirror();
    if (this._snapshot) this._updateOverview();
  }

  _items(kind) {
    return (this._snapshot?.items || []).filter((item) => item.kind === kind);
  }

  _indicatorPages() {
    const pages = {};
    this._items("indicator").forEach((item) => {
      if (item.enabled && item.pages.length) pages[item.data.indicator] = item.pages[0];
    });
    return pages;
  }

  _updateOverview() {
    const snapshot = this._snapshot;
    if (!snapshot || this._view.name !== "overview") return;
    this._notLoaded.hidden = snapshot.loaded;
    this._navRow.hidden = !snapshot.features?.navigate;
    if (!this._subs.screen && snapshot.features?.screen) this._subscribeScreen();

    const apps = this._items("app");
    this._currentApp.textContent = snapshot.current_app || this.t("unknown");
    this._rotation.textContent = `${apps.filter((a) => a.enabled && a.pages.length).length} / ${apps.length}`;

    const structure = snapshot.items.map((i) => `${i.subentry_id}:${i.kind}:${i.data.mode}`).join("|");
    if (structure !== this._structure) {
      this._structure = structure;
      this._buildCards(apps);
      this._buildIndicators();
    }
    apps.forEach((item) => this._updateCard(item));
    this._updateIndicators();
    this._drawMirror();
  }

  _buildCards(apps) {
    clear(this._grid);
    this._cards = new Map();
    apps
      .slice()
      .sort((a, b) => a.data.app_name.localeCompare(b.data.app_name))
      .forEach((item) => {
        const name = item.data.app_name;
        const canvas = h("canvas", { role: "img", "aria-label": this.t("thumbnail", { name }) });
        const toggle = h("button", { class: "switch", role: "switch", "aria-label": this.t("enable", { name }),
          onClick: () => this._call({ type: "awtrix_studio/enable", subentry_id: item.subentry_id, enabled: !this._findItem(item.subentry_id)?.enabled }) },
          h("span"));
        const status = h("span", { class: "status" });
        const show = h("button", { class: "btn small", onClick: () => this._call({ type: "awtrix_studio/show", app_name: name }) }, this.t("show_now"));
        const root = h("article", { class: "card app" },
          h("div", { class: "screen" }, canvas),
          h("div", { class: "row between" },
            h("div", { class: "row" }, h("span", { class: "name" }, name),
              h("span", { class: `chip ${item.data.mode}` }, this.t(item.data.mode))),
            toggle),
          h("div", { class: "row between" }, status,
            h("div", { class: "row" }, show,
              h("button", { class: "btn small", onClick: () => this._openEditor("app", item.subentry_id) }, this.t("edit")))));
        this._cards.set(item.subentry_id, { root, canvas, toggle, status, show });
        this._grid.append(root);
      });
  }

  _updateCard(item) {
    const card = this._cards.get(item.subentry_id);
    if (!card) return;
    const page = item.pages[item.page_index] || item.pages[0];
    const rendered = renderPage(page);
    drawMatrix(card.canvas, rendered.pixels, { cell: 6, gap: 1, icon: rendered.icon });
    card.toggle.setAttribute("aria-checked", item.enabled ? "true" : "false");
    const visible = item.enabled && item.pages.length > 0;
    card.root.classList.toggle("dim", !visible);
    card.root.classList.toggle("current", item.on_screen);
    card.show.disabled = !visible;
    let text, kind = "";
    if (!item.enabled) text = this.t("disabled");
    else if (item.error) { text = this.t("failing"); kind = "error"; }
    else if (!item.pages.length) text = this.t("hidden");
    else if (item.on_screen) { text = `${this.t("on_screen")}${item.pages.length > 1 ? " · " + this.t("pages_n", { n: item.pages.length }) : ""}`; kind = "screen-on"; }
    else { text = `${this.t("visible")}${item.pages.length > 1 ? " · " + this.t("pages_n", { n: item.pages.length }) : ""}`; kind = "ok"; }
    card.status.textContent = text;
    card.status.className = `status ${kind}`;
    if (item.error) card.status.title = item.error; else card.status.removeAttribute("title");
  }

  _buildIndicators() {
    clear(this._indicatorRow);
    this._indicatorCards = new Map();
    ["1", "2", "3"].forEach((n) => {
      const item = this._items("indicator").find((i) => i.data.indicator === n);
      if (!item) {
        this._indicatorRow.append(h("div", { class: "card indicator free" }, h("span", { class: "swatch" }),
          h("div", { class: "row between grow" },
            h("div", {}, h("strong", {}, this.t("indicator_n", { n })), h("div", { class: "muted" }, this.t("indicator_free"))),
            h("button", { class: "btn small", onClick: () => this._openEditor("indicator", null, n) }, this.t("configure")))));
        return;
      }
      const swatch = h("span", { class: "swatch" });
      const state = h("div", { class: "muted" });
      const toggle = h("button", { class: "switch", role: "switch", "aria-label": this.t("enable", { name: this.t("indicator_n", { n }) }),
        onClick: () => this._call({ type: "awtrix_studio/enable", subentry_id: item.subentry_id, enabled: !this._findItem(item.subentry_id)?.enabled }) }, h("span"));
      this._indicatorRow.append(h("div", { class: "card indicator" }, swatch,
        h("div", { class: "grow" }, h("strong", {}, this.t("indicator_n", { n })), state),
        toggle,
        h("button", { class: "btn small", onClick: () => this._openEditor("indicator", item.subentry_id) }, this.t("edit"))));
      this._indicatorCards.set(item.subentry_id, { swatch, state, toggle });
    });
  }

  _updateIndicators() {
    this._items("indicator").forEach((item) => {
      const card = this._indicatorCards?.get(item.subentry_id);
      if (!card) return;
      const page = item.pages[0];
      const lit = item.enabled && page && page.color !== undefined && parseColor(page.color, "#000000") !== "#000000";
      card.swatch.style.background = lit ? parseColor(page.color) : "";
      card.state.textContent = `${this.t(item.data.mode)} · ${!item.enabled ? this.t("disabled") : lit ? this.t("lit") : this.t("off")}`;
      card.toggle.setAttribute("aria-checked", item.enabled ? "true" : "false");
    });
  }

  _findItem(subentryId) {
    return (this._snapshot?.items || []).find((i) => i.subentry_id === subentryId);
  }

  _simulatedScreen() {
    const snapshot = this._snapshot;
    const current = this._items("app").find((a) => a.on_screen && a.pages.length);
    const rendered = renderPage(current ? current.pages[current.page_index] || current.pages[0] : null);
    addIndicators(rendered.pixels, this._indicatorPages());
    return snapshot ? rendered : { pixels: new Array(WIDTH * HEIGHT).fill(null), icon: null };
  }

  _drawMirror() {
    if (!this._mirrorCanvas) return;
    const fresh = this._screen.pixels && Date.now() - this._screen.at < MIRROR_STALE_MS;
    if (fresh) {
      drawMatrix(this._mirrorCanvas, this._screen.pixels, { cell: 12, gap: 2, glow: true });
      this._mirrorCaption.textContent = this.t("live_mirror");
    } else {
      const rendered = this._simulatedScreen();
      drawMatrix(this._mirrorCanvas, rendered.pixels, { cell: 12, gap: 2, icon: rendered.icon, glow: true });
      this._mirrorCaption.textContent = this._snapshot?.features?.screen ? this.t("live_waiting") : this.t("simulated_note");
    }
  }

  // --------------------------------------------------------------- editor

  _openEditor(kind, subentryId, presetIndicator) {
    const item = subentryId ? this._findItem(subentryId) : null;
    this._view = { name: "edit", kind, subentryId, item };
    this._previewTab = "sim";
    this._preview = { pages: [], error: null, template: null };
    this._pageIndex = 0;
    this._stop("screen");
    this._backButton.hidden = false;
    this._clockSelect.hidden = true;
    this._form = this._initialForm(kind, item, presetIndicator);
    if (kind === "app") this._title.textContent = item ? `${this.t("edit_app")} ${item.data.app_name}` : this.t("new_app");
    else this._title.textContent = item ? this.t("edit_indicator", { n: item.data.indicator }) : this.t("new_indicator");
    this._renderEditor();
    this._refreshPreview();
  }

  _initialForm(kind, item, presetIndicator) {
    const d = item ? item.data : {};
    if (kind === "app") {
      return {
        mode: d.mode || "simple",
        app_name: d.app_name || "",
        entity_id: d.entity_id || "",
        label: d.label || "",
        icon: d.icon || "",
        color: toHex(d.color, "#FFFFFF"),
        decimals: d.decimals ?? "",
        show_unit: d.show_unit ?? true,
        hide_when_zero: d.hide_when_zero ?? false,
        threshold_1: d.threshold_1 ?? "",
        color_1: toHex(d.color_1, "#FFB74D"),
        threshold_2: d.threshold_2 ?? "",
        color_2: toHex(d.color_2, "#FF6B5B"),
        color_mode: d.color_mode || (d.threshold_1 != null || d.threshold_2 != null ? "steps" : "fixed"),
        ...this._gradientForm(d),
        template: d.template || STARTER_APP_TEMPLATE,
        page_interval: d.page_interval ?? 1.5,
        cycle_only_on_screen: d.cycle_only_on_screen ?? true,
        hide_when_empty: d.hide_when_empty ?? true,
        lifetime: d.lifetime ?? 0,
      };
    }
    const used = this._items("indicator").map((i) => i.data.indicator);
    const free = ["1", "2", "3"].filter((n) => !used.includes(n));
    return {
      mode: d.mode || "simple",
      indicator: d.indicator || presetIndicator || free[0] || "1",
      entity_id: d.entity_id || "",
      active_state: d.active_state || "on",
      color: toHex(d.color, "#FF8C00"),
      effect: d.effect || "none",
      effect_interval: d.effect_interval ?? 1000,
      color_mode: d.color_mode || "state",
      ...this._gradientForm(d),
      template: d.template || STARTER_INDICATOR_TEMPLATE,
    };
  }

  _gradientForm(d) {
    return {
      gradient: d.gradient || "high_bad",
      _presetTouched: Boolean(d.gradient),
      gradient_min: d.gradient_min ?? "",
      gradient_max: d.gradient_max ?? "",
      gradient_stops: (d.gradient_stops || []).map((stop) => ({ value: stop.value, color: toHex(stop.color, "#FFFFFF") })),
    };
  }

  _gradientPayload() {
    const f = this._form;
    if (f.color_mode !== "gradient") return { color_mode: f.color_mode };
    if (f.gradient === "custom") {
      return { color_mode: "gradient", gradient: "custom",
        gradient_stops: f.gradient_stops.map((stop) => ({ value: numberOrEmpty(stop.value), color: stop.color })) };
    }
    return { color_mode: "gradient", gradient: f.gradient, gradient_min: numberOrEmpty(f.gradient_min), gradient_max: numberOrEmpty(f.gradient_max) };
  }

  _payload() {
    const f = this._form;
    const { kind } = this._view;
    if (kind === "app" && f.mode === "simple") {
      return { mode: "simple", app_name: f.app_name, entity_id: f.entity_id, label: f.label, icon: f.icon, color: f.color,
        decimals: numberOrEmpty(f.decimals), show_unit: f.show_unit, hide_when_zero: f.hide_when_zero,
        threshold_1: numberOrEmpty(f.threshold_1), color_1: f.color_1, threshold_2: numberOrEmpty(f.threshold_2), color_2: f.color_2,
        ...this._gradientPayload() };
    }
    if (kind === "app") {
      return { mode: "template", app_name: f.app_name, template: f.template, page_interval: numberOrEmpty(f.page_interval),
        cycle_only_on_screen: f.cycle_only_on_screen, hide_when_empty: f.hide_when_empty, lifetime: numberOrEmpty(f.lifetime) };
    }
    if (f.mode === "simple") {
      return { mode: "simple", indicator: f.indicator, entity_id: f.entity_id, active_state: f.active_state, color: f.color,
        effect: f.effect, effect_interval: numberOrEmpty(f.effect_interval), ...this._gradientPayload() };
    }
    return { mode: "template", indicator: f.indicator, template: f.template };
  }

  _renderEditor() {
    clear(this._main);
    const { kind, item } = this._view;
    this._errors = {};
    this._fieldsBox = h("div", { class: "fields" });
    this._modeTabs = h("div", { class: "tabs", role: "tablist", "aria-label": this.t("mode") });
    ["simple", "template"].forEach((mode) => this._modeTabs.append(
      h("button", { role: "tab", "aria-selected": this._form.mode === mode ? "true" : "false", onClick: () => this._setMode(mode) }, this.t(mode))));
    this._saveFeedback = h("div", { class: "feedback", role: "status" });

    const actions = h("div", { class: "row" },
      h("button", { class: "btn primary", onClick: () => this._save() }, this.t("save")),
      h("button", { class: "btn", onClick: () => this._showOverview() }, this.t("cancel")),
      item ? h("button", { class: "btn danger", onClick: () => this._delete() }, this.t("delete")) : null);

    // Preview column
    this._previewCanvas = h("canvas", { role: "img", "aria-label": this.t("preview") });
    this._previewTabs = h("div", { class: "tabs", role: "tablist", "aria-label": this.t("preview") });
    [["sim", "simulated"], ["real", "real_screen"]].forEach(([id, label]) => this._previewTabs.append(
      h("button", { role: "tab", "aria-selected": this._previewTab === id ? "true" : "false", onClick: () => this._setPreviewTab(id) }, this.t(label))));
    this._previewTabs.hidden = !this._snapshot?.features?.screen;
    this._pills = h("div", { class: "pills" });
    this._previewNote = h("div", { class: "muted" });
    this._previewStatus = h("div", { class: "status" });
    this._previewDetail = h("div", { class: "muted" });
    this._json = h("pre", { "aria-label": this.t("json_title") });
    this._generated = h("pre", { "aria-label": this.t("generated_title") });
    this._generatedBox = h("div", { class: "card pad", style: "display:flex;flex-direction:column;gap:10px" },
      h("div", { class: "row between" }, h("h2", {}, this.t("generated_title")),
        h("button", { class: "btn small", onClick: () => this._convert() }, this.t("convert"))),
      this._generated);
    this._testFeedback = h("div", { class: "feedback", role: "status" });

    this._main.append(
      h("div", { class: "row between" }, this._modeTabs, actions),
      this._saveFeedback,
      h("div", { class: "editor" },
        h("section", { class: "card pad form", "aria-label": kind === "app" ? this.t("edit_app") : this.t("indicator") }, this._fieldsBox),
        h("section", { class: "preview" },
          h("div", { class: "card pad", style: "display:flex;flex-direction:column;gap:12px" },
            h("div", { class: "row between" }, h("h2", {}, this.t("preview")), this._previewTabs),
            h("div", { class: "screen", style: "align-self:center" }, this._previewCanvas),
            this._pills, this._previewNote, this._previewStatus, this._previewDetail,
            h("div", { class: "row" }, h("button", { class: "btn", onClick: () => this._test() }, this.t("test")),
              h("span", { class: "muted" }, this.t("test_note"))),
            this._testFeedback),
          h("div", { class: "card pad", style: "display:flex;flex-direction:column;gap:10px" }, h("h2", {}, this.t("json_title")), this._json),
          this._generatedBox)));
    this._renderFields();
    this._drawPreview();
  }

  _field(key, label, control, help, wide) {
    const error = h("div", { class: "error-text", role: "alert" });
    this._errors[key] = error;
    return h("div", { class: `field${wide ? " wide" : ""}` },
      h("label", { for: `f-${key}` }, label), control, help ? h("div", { class: "muted" }, help) : null, error);
  }

  _input(key, type = "text", extra = {}) {
    return h("input", { id: `f-${key}`, type, value: this._form[key], ...extra,
      onInput: (e) => {
        this._form[key] = e.target.value;
        if (key === "entity_id") this._entityChanged();
        this._schedulePreview();
      } });
  }

  _entityChanged() {
    const f = this._form;
    if (f.color_mode !== "gradient" || f.gradient === "custom" || !this._hass.states[f.entity_id]) { this._updateGradientBar(); return; }
    const hadRange = f.gradient_min !== "" || f.gradient_max !== "";
    this._suggestRange();
    if (!hadRange && (f.gradient_min !== "" || f.gradient_max !== "")) {
      const body = this._fieldsBox.querySelector(".color-body");
      if (body) this._renderColorBody(body);
    } else {
      this._updateGradientBar();
    }
  }

  _check(key, label, help) {
    const error = h("div", { class: "error-text", role: "alert" });
    this._errors[key] = error;
    return h("div", { class: "field" },
      h("label", { class: "check" },
        h("input", { type: "checkbox", checked: this._form[key], onChange: (e) => { this._form[key] = e.target.checked; this._schedulePreview(); } }),
        h("span", {}, label, help ? h("span", { class: "muted", style: "display:block" }, help) : null)), error);
  }

  _entityInput() {
    const listId = "awtrix-studio-entities";
    const list = h("datalist", { id: listId });
    Object.keys(this._hass.states).sort().slice(0, 5000).forEach((id) => list.append(h("option", { value: id })));
    return h("div", {}, this._input("entity_id", "text", { list: listId, autocomplete: "off", spellcheck: "false",
      placeholder: this.t("entity_placeholder") }), list);
  }

  _renderFields() {
    clear(this._fieldsBox);
    this._errors = {};
    const { kind, item } = this._view;
    const f = this._form;
    const box = this._fieldsBox;
    Array.from(this._modeTabs.children).forEach((tab, i) => tab.setAttribute("aria-selected", ["simple", "template"][i] === f.mode ? "true" : "false"));

    if (kind === "app" && !item) box.append(this._field("app_name", this.t("app_name"), this._input("app_name", "text", { maxlength: 32, spellcheck: "false" }), this.t("app_name_help"), true));
    if (kind === "indicator" && !item) {
      const used = this._items("indicator").map((i) => i.data.indicator);
      const select = h("select", { id: "f-indicator", onChange: (e) => { f.indicator = e.target.value; this._schedulePreview(); } },
        ...["1", "2", "3"].filter((n) => !used.includes(n) || n === f.indicator).map((n) => h("option", { value: n }, this.t(`indicator_${n}`))));
      select.value = f.indicator;
      box.append(this._field("indicator", this.t("indicator"), select, null, true));
    }

    if (f.mode === "template") {
      const textarea = h("textarea", { id: "f-template", spellcheck: "false", rows: 16,
        onInput: (e) => { f.template = e.target.value; this._schedulePreview(); } });
      textarea.value = f.template;
      box.append(this._field("template", this.t("template_label"), textarea, kind === "app" ? this.t("template_help") : this.t("template_help_indicator"), true));
      if (kind === "app") {
        box.append(
          this._field("page_interval", this.t("page_interval"), this._input("page_interval", "number", { min: 0.5, max: 60, step: 0.1 })),
          this._field("lifetime", this.t("lifetime"), this._input("lifetime", "number", { min: 0, max: 86400, step: 1 })),
          this._check("cycle_only_on_screen", this.t("cycle_only_on_screen"), this.t("cycle_help")),
          this._check("hide_when_empty", this.t("hide_when_empty"), this.t("hide_help")));
      }
      return;
    }

    box.append(this._field("entity_id", this.t("entity"), this._entityInput(), null, true));
    if (kind === "app") {
      box.append(
        this._field("label", this.t("label"), this._input("label", "text", { maxlength: 64 }), this.t("label_help")),
        this._field("icon", this.t("icon"), this._input("icon", "text", { maxlength: 64, spellcheck: "false" }), this.t("icon_help")),
        this._field("color", this.t("text_color"), this._input("color", "color")),
        this._field("decimals", this.t("decimals"), this._input("decimals", "number", { min: 0, max: 4, step: 1 }), this.t("decimals_help")),
        this._check("show_unit", this.t("show_unit")),
        this._check("hide_when_zero", this.t("hide_when_zero")));
      box.append(this._colorSection(["fixed", "steps", "gradient"], "color_by_value"));
    } else {
      const effect = h("select", { id: "f-effect", onChange: (e) => { f.effect = e.target.value; this._schedulePreview(); } },
        ...["none", "blink", "fade"].map((v) => h("option", { value: v }, this.t(`effect_${v}`))));
      effect.value = f.effect;
      box.append(
        this._colorSection(["state", "gradient"], "indicator_lights"),
        this._field("effect", this.t("effect"), effect),
        this._field("effect_interval", this.t("effect_interval"), this._input("effect_interval", "number", { min: 100, max: 10000, step: 100 })));
    }
  }

  // ------------------------------------------------- color by value

  _colorSection(modes, legend) {
    const tabs = h("div", { class: "tabs", role: "tablist", "aria-label": this.t(legend) });
    const body = h("div", { class: "color-body" });
    const select = (mode) => {
      this._form.color_mode = mode;
      Array.from(tabs.children).forEach((tab, i) => tab.setAttribute("aria-selected", modes[i] === mode ? "true" : "false"));
      if (mode === "gradient") this._suggestRange();
      this._renderColorBody(body);
      this._schedulePreview();
    };
    modes.forEach((mode) => tabs.append(h("button", { role: "tab", "aria-selected": this._form.color_mode === mode ? "true" : "false",
      onClick: () => select(mode) }, this.t(`color_mode_${mode}`))));
    this._renderColorBody(body);
    return h("fieldset", { class: "field wide" }, h("legend", {}, this.t(legend)), tabs, body);
  }

  _renderColorBody(body) {
    clear(body);
    const f = this._form;
    const error = (key) => {
      const el = h("div", { class: "error-text", role: "alert" });
      this._errors[key] = el;
      return el;
    };
    if (f.color_mode === "fixed") {
      body.append(h("div", { class: "muted" }, this.t("color_fixed_help")));
    } else if (f.color_mode === "state") {
      body.append(h("div", { class: "fields" },
        this._field("active_state", this.t("active_state"), this._input("active_state", "text", { maxlength: 64 })),
        this._field("color", this.t("color"), this._input("color", "color"))));
    } else if (f.color_mode === "steps") {
      const row = (n, label) => {
        const err = error(`color_${n}`);
        this._errors[`threshold_${n}`] = err;
        return h("div", { class: "row" },
          h("label", { for: `f-threshold_${n}` }, label),
          h("div", { class: "field", style: "width:110px" }, this._input(`threshold_${n}`, "number", { step: "any" })),
          h("span", { "aria-hidden": "true" }, "→"),
          h("div", { class: "field" }, this._input(`color_${n}`, "color", { "aria-label": `${label} · ${this.t("color")}` })),
          err);
      };
      body.append(h("div", { class: "muted" }, this.t("color_steps_help")), row(1, this.t("above")), row(2, this.t("then_above")));
    } else {
      body.append(this._gradientEditor(error));
    }
  }

  _gradientEditor(error) {
    const f = this._form;
    const wrap = h("div", { class: "gradient-editor" });
    const presets = h("div", { class: "presets", role: "radiogroup", "aria-label": this.t("gradient") });
    [...Object.keys(PRESETS), "custom"].forEach((name) => {
      const swatch = h("span", { class: "preset-swatch" + (name === "custom" ? " custom" : "") });
      if (name !== "custom") swatch.style.background = presetCss(name);
      presets.append(h("button", { class: "preset", role: "radio", "aria-checked": f.gradient === name ? "true" : "false",
        onClick: () => this._pickGradient(name, wrap) }, swatch, h("span", {}, this.t(`gradient_${name}`))));
    });
    wrap.append(presets, error("gradient"));

    if (f.gradient === "custom") {
      const list = h("div", { class: "stops" });
      f.gradient_stops.forEach((stop, i) => {
        list.append(h("div", { class: "row stop" },
          h("input", { type: "number", step: "any", value: stop.value, "aria-label": this.t("stop_value", { n: i + 1 }), class: "stop-value",
            onInput: (e) => { stop.value = e.target.value; this._updateGradientBar(); this._schedulePreview(); } }),
          h("input", { type: "color", value: stop.color, "aria-label": this.t("stop_color", { n: i + 1 }),
            onInput: (e) => { stop.color = e.target.value; this._updateGradientBar(); this._schedulePreview(); } }),
          f.gradient_stops.length > 2 ? h("button", { class: "btn small", "aria-label": this.t("remove_stop", { n: i + 1 }),
            onClick: () => { f.gradient_stops.splice(i, 1); this._rerenderGradient(wrap); this._schedulePreview(); } }, "✕") : null));
      });
      wrap.append(h("div", { class: "muted" }, this.t("custom_help")), list,
        f.gradient_stops.length < MAX_STOPS ? h("button", { class: "btn small", style: "align-self:flex-start", onClick: () => this._addStop(wrap) },
          icon("plus"), this.t("add_stop")) : "",
        error("gradient_stops"));
    } else {
      wrap.append(h("div", { class: "fields" },
        this._field("gradient_min", this.t("gradient_min"), this._input("gradient_min", "number", { step: "any" }), this.t("gradient_min_help")),
        this._field("gradient_max", this.t("gradient_max"), this._input("gradient_max", "number", { step: "any" }), this.t("gradient_max_help"))));
    }

    this._gradientBar = h("div", { class: "gradient-bar" });
    this._gradientMarker = h("div", { class: "gradient-marker" });
    this._gradientLabels = h("div", { class: "row between muted" });
    this._gradientNow = h("div", { class: "muted" });
    wrap.append(h("div", { class: "gradient-track" }, this._gradientBar, this._gradientMarker), this._gradientLabels, this._gradientNow);
    // Inputs re-render the bar on every keystroke without rebuilding the form.
    wrap.addEventListener("input", () => this._updateGradientBar());
    this._updateGradientBar();
    return wrap;
  }

  _rerenderGradient(wrap) {
    const parent = wrap.parentNode;
    if (!parent) return;
    this._renderColorBody(parent);
  }

  _pickGradient(name, wrap) {
    const f = this._form;
    if (name === "custom" && f.gradient !== "custom" && !f.gradient_stops.length) {
      // Start from what is on screen: the current preset, or a simple range.
      const stops = formStops(f) || formStops({ ...f, gradient: f.gradient in PRESETS ? f.gradient : "high_bad", gradient_min: 0, gradient_max: 100 });
      f.gradient_stops = stops.map(([value, color]) => ({ value: Math.round(value * 1000) / 1000, color: rgbToHex(color) }));
    }
    f.gradient = name;
    f._presetTouched = true;
    if (name !== "custom") this._suggestRange();
    this._rerenderGradient(wrap);
    this._schedulePreview();
  }

  _addStop(wrap) {
    const stops = this._form.gradient_stops;
    const last = stops[stops.length - 1];
    const prev = stops[stops.length - 2];
    const step = last && prev ? Number(last.value) - Number(prev.value) : 10;
    stops.push({ value: last ? Number(last.value) + (Number.isFinite(step) && step > 0 ? step : 10) : 0, color: last ? last.color : "#ffffff" });
    this._rerenderGradient(wrap);
    this._schedulePreview();
  }

  /** Fill an empty range from the entity's kind (°C, ppm, %…). */
  _suggestRange() {
    const f = this._form;
    if (f.gradient_min !== "" || f.gradient_max !== "") return;
    const hint = suggestion(this._hass.states[f.entity_id]);
    if (!hint) return;
    const [preset, low, high] = hint;
    if (f.color_mode === "gradient" && !f._presetTouched) f.gradient = preset;
    f.gradient_min = low;
    f.gradient_max = high;
  }

  _updateGradientBar() {
    if (!this._gradientBar) return;
    const stops = formStops(this._form);
    if (!stops) {
      this._gradientBar.style.background = "";
      this._gradientBar.classList.add("empty");
      this._gradientMarker.hidden = true;
      clear(this._gradientLabels);
      this._gradientNow.textContent = this.t("gradient_incomplete");
      return;
    }
    this._gradientBar.classList.remove("empty");
    this._gradientBar.style.background = cssGradient(stops);
    clear(this._gradientLabels);
    const low = stops[0][0];
    const high = stops[stops.length - 1][0];
    this._gradientLabels.append(h("span", {}, String(+low.toFixed(3))), h("span", {}, String(+high.toFixed(3))));
    const state = this._hass.states[this._form.entity_id];
    const value = state ? Number(state.state) : NaN;
    if (!state || state.state === "" || !Number.isFinite(value)) {
      this._gradientMarker.hidden = true;
      this._gradientNow.textContent = state ? this.t("gradient_not_number") : "";
      return;
    }
    const ratio = Math.max(0, Math.min(1, (value - low) / (high - low)));
    this._gradientMarker.hidden = false;
    this._gradientMarker.style.left = `${(ratio * 100).toFixed(2)}%`;
    this._gradientMarker.style.background = rgbToHex(colorAt(stops, value));
    const unit = state.attributes?.unit_of_measurement || "";
    this._gradientNow.textContent = this.t("gradient_now", { value: `${state.state}${unit ? ` ${unit}` : ""}` });
  }

  _setMode(mode) {
    if (this._form.mode === mode) return;
    this._form.mode = mode;
    this._renderFields();
    this._refreshPreview();
  }

  _convert() {
    if (!this._preview.template) return;
    this._form.template = this._preview.template;
    this._setMode("template");
  }

  _schedulePreview() {
    clearTimeout(this._previewTimer);
    this._previewTimer = setTimeout(() => this._refreshPreview(), PREVIEW_DEBOUNCE);
  }

  _refreshPreview() {
    if (this._view.name !== "edit") return;
    const { kind, subentryId } = this._view;
    const message = { type: "awtrix_studio/preview", entry_id: this._entryId, kind, data: this._payload() };
    if (subentryId) message.subentry_id = subentryId;
    this._subscribe("preview", message, (event) => {
      this._preview = { pages: event.pages || [], error: event.error, detail: event.detail, template: event.template || null };
      if (this._pageIndex >= this._preview.pages.length) this._pageIndex = 0;
      this._restartCycle();
      this._drawPreview();
    });
  }

  _restartCycle() {
    clearInterval(this._cycleTimer);
    const count = this._preview.pages.length;
    if (count < 2) return;
    const seconds = this._view.kind === "app" && this._form.mode === "template" ? Number(this._form.page_interval) || 1.5 : 1.5;
    this._cycleTimer = setInterval(() => {
      this._pageIndex = (this._pageIndex + 1) % count;
      this._drawPreview();
    }, Math.max(500, seconds * 1000));
  }

  _setPreviewTab(id) {
    this._previewTab = id;
    Array.from(this._previewTabs.children).forEach((tab, i) => tab.setAttribute("aria-selected", ["sim", "real"][i] === id ? "true" : "false"));
    if (id === "real") this._subscribeScreen(); else this._stop("screen");
    this._drawPreview();
  }

  _drawPreview() {
    if (this._view.name !== "edit" || !this._previewCanvas) return;
    const { kind } = this._view;
    const pages = this._preview.pages;
    const page = pages[this._pageIndex] || pages[0];

    if (this._previewTab === "real") {
      const pixels = this._screen.pixels || new Array(WIDTH * HEIGHT).fill(null);
      drawMatrix(this._previewCanvas, pixels, { cell: 11, gap: 2, glow: true });
      this._previewNote.textContent = this._screen.pixels ? this.t("live_mirror") : this.t("live_waiting");
    } else if (kind === "indicator") {
      const pixels = addIndicators(new Array(WIDTH * HEIGHT).fill(null), page ? { [this._form.indicator]: page } : {});
      drawMatrix(this._previewCanvas, pixels, { cell: 11, gap: 2, glow: true });
      this._previewNote.textContent = this.t("simulated_note");
    } else {
      const rendered = renderPage(page);
      drawMatrix(this._previewCanvas, rendered.pixels, { cell: 11, gap: 2, icon: rendered.icon, glow: true });
      this._previewNote.textContent = rendered.overflow ? this.t("overflow_note") : this.t("simulated_note");
    }

    clear(this._pills);
    if (pages.length > 1) pages.forEach((_p, i) => this._pills.append(h("span", { class: `pill${i === this._pageIndex ? " active" : ""}` }, this.t("page_n", { n: i + 1 }))));

    if (this._preview.error) {
      this._previewStatus.textContent = this.t(`errors.${this._preview.error}`);
      this._previewStatus.className = "status error";
      this._previewDetail.textContent = this._preview.detail || "";
    } else {
      this._previewStatus.textContent = pages.length ? this.t("valid", { n: pages.length }) : this.t("valid_empty");
      this._previewStatus.className = "status ok";
      this._previewDetail.textContent = "";
    }
    this._json.textContent = page ? JSON.stringify(page, null, 2) : "—";
    this._generatedBox.hidden = !(this._form.mode === "simple" && this._preview.template);
    this._generated.textContent = this._preview.template || "";
  }

  _showErrors(errors, detail) {
    Object.values(this._errors).forEach((el) => { el.textContent = ""; });
    let shown = false;
    Object.entries(errors || {}).forEach(([field, key]) => {
      const target = this._errors[field];
      const text = this.t(`errors.${key}`) + (detail && (key === "invalid_template" || key === "invalid_pages") ? ` ${detail}` : "");
      if (target) { target.textContent = text; shown = true; } else { this._saveFeedback.textContent = text; }
    });
    if (shown) this._saveFeedback.textContent = "";
  }

  async _save() {
    const { kind, subentryId } = this._view;
    const message = { type: "awtrix_studio/save", kind, data: this._payload() };
    if (subentryId) message.subentry_id = subentryId;
    const result = await this._call(message);
    if (!result) return;
    if (result.errors) { this._showErrors(result.errors, result.detail); return; }
    this._showOverview();
  }

  async _delete() {
    const { item, kind } = this._view;
    const name = kind === "app" ? item.data.app_name : this.t("indicator_n", { n: item.data.indicator });
    if (!window.confirm(this.t("delete_confirm", { name }))) return;
    const result = await this._call({ type: "awtrix_studio/delete", subentry_id: item.subentry_id });
    if (result !== null) this._showOverview();
  }

  async _test() {
    const { kind, subentryId } = this._view;
    const data = this._payload();
    if (kind === "app" && !subentryId && !data.app_name) { this._showErrors({ app_name: "invalid_app_name" }); return; }
    const message = { type: "awtrix_studio/test", kind, data, page: this._pageIndex };
    if (subentryId) message.subentry_id = subentryId;
    const result = await this._call(message);
    if (!result) return;
    if (result.errors) { this._showErrors(result.errors, result.detail); return; }
    this._testFeedback.textContent = this.t("test_sent");
    setTimeout(() => { this._testFeedback.textContent = ""; }, 4000);
  }
}

if (!customElements.get("awtrix-studio-panel")) {
  customElements.define("awtrix-studio-panel", AwtrixStudioPanel);
}
