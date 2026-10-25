// Awtrix Studio — color gradients, mirrored from gradients.py.
// The server always recomputes and validates; this only drives the editor.

const GREEN = [0, 220, 0];
const YELLOW = [255, 200, 0];
const ORANGE = [255, 110, 0];
const RED = [255, 0, 0];
const BLUE = [0, 110, 255];
const WHITE = [255, 255, 255];

export const PRESETS = {
  high_bad: [GREEN, YELLOW, RED],
  low_bad: [RED, YELLOW, GREEN],
  middle_good: [RED, YELLOW, GREEN, YELLOW, RED],
  cold_hot: [BLUE, WHITE, ORANGE, RED],
};

export const MAX_STOPS = 5;

// A sensible starting point per device class: [preset, min, max].
const SUGGESTIONS = {
  temperature: ["cold_hot", 10, 30],
  humidity: ["middle_good", 20, 80],
  moisture: ["middle_good", 20, 80],
  carbon_dioxide: ["high_bad", 400, 1500],
  pm25: ["high_bad", 0, 50],
  pm10: ["high_bad", 0, 80],
  volatile_organic_compounds: ["high_bad", 0, 500],
  aqi: ["high_bad", 0, 150],
  battery: ["low_bad", 10, 100],
  power_factor: ["low_bad", 0, 100],
};

export function suggestion(stateObj) {
  const deviceClass = stateObj?.attributes?.device_class;
  if (SUGGESTIONS[deviceClass]) return SUGGESTIONS[deviceClass];
  if (stateObj?.attributes?.unit_of_measurement === "%") return ["high_bad", 0, 100];
  return null;
}

export function hexToRgb(hex) {
  const match = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex || "");
  return match ? match.slice(1).map((c) => parseInt(c, 16)) : null;
}

export function rgbToHex(rgb) {
  return "#" + rgb.map((c) => Math.max(0, Math.min(255, Math.round(c))).toString(16).padStart(2, "0")).join("");
}

/** Stops [[value, [r, g, b]], …] from the editor form, or null if incomplete. */
export function formStops(form) {
  if (form.gradient === "custom") {
    const stops = (form.gradient_stops || []).map((s) => [s.value === "" ? NaN : Number(s.value), hexToRgb(s.color)]);
    if (stops.length < 2 || stops.some(([v, c]) => notFinite(v) || !c)) return null;
    for (let i = 1; i < stops.length; i++) if (stops[i][0] <= stops[i - 1][0]) return null;
    return stops;
  }
  const colors = PRESETS[form.gradient];
  const low = Number(form.gradient_min);
  const high = Number(form.gradient_max);
  if (!colors || form.gradient_min === "" || form.gradient_max === "" || notFinite(low) || notFinite(high) || high <= low) return null;
  const step = (high - low) / (colors.length - 1);
  return colors.map((c, i) => [low + step * i, c]);
}

function notFinite(n) {
  return !Number.isFinite(n);
}

export function colorAt(stops, value) {
  let color = stops[0][1];
  for (let i = 0; i < stops.length - 1; i++) {
    const [low, a] = stops[i];
    const [high, b] = stops[i + 1];
    if (value > low) {
      const t = Math.min((value - low) / (high - low), 1);
      color = a.map((c, k) => c + (b[k] - c) * t);
    }
  }
  return color.map((c) => Math.round(c));
}

/** A CSS linear-gradient for stops; colors come from validated RGB lists only. */
export function cssGradient(stops) {
  const low = stops[0][0];
  const span = stops[stops.length - 1][0] - low || 1;
  return `linear-gradient(90deg, ${stops.map(([v, c]) => `${rgbToHex(c)} ${(((v - low) / span) * 100).toFixed(2)}%`).join(", ")})`;
}

/** CSS for a preset's swatch, colors evenly spread. */
export function presetCss(name) {
  const colors = PRESETS[name];
  return cssGradient(colors.map((c, i) => [i, c]));
}
