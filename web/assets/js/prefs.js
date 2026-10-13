// Display preferences, persisted in localStorage (per browser).

const KEY = "qbible.prefs.v1";
export const FONT_MIN = 14;
export const FONT_MAX = 32;
export const FONT_STEP = 2;

export const DEFAULTS = Object.freeze({
  fontSize: 20,
  fontFamily: "serif",
  lineHeight: 1.7,
  theme: "system",
  layout: "paragraphs",
  supplied: "italic",
  verseNumbers: true,
  libraryOpen: null, // null = default for the screen size
});

const ALLOWED = {
  fontFamily: ["serif", "sans"],
  theme: ["system", "light", "dark"],
  layout: ["paragraphs", "verses"],
  supplied: ["italic", "brackets", "plain"],
};

function sanitise(p) {
  const out = { ...DEFAULTS };
  if (!p || typeof p !== "object") return out;
  const size = Number(p.fontSize);
  if (Number.isFinite(size)) out.fontSize = Math.min(FONT_MAX, Math.max(FONT_MIN, Math.round(size)));
  const lh = Number(p.lineHeight);
  if (Number.isFinite(lh) && lh >= 1.3 && lh <= 2.4) out.lineHeight = lh;
  for (const [k, values] of Object.entries(ALLOWED)) if (values.includes(p[k])) out[k] = p[k];
  if (typeof p.verseNumbers === "boolean") out.verseNumbers = p.verseNumbers;
  if (typeof p.libraryOpen === "boolean") out.libraryOpen = p.libraryOpen;
  return out;
}

export function loadPrefs() {
  try {
    return sanitise(JSON.parse(localStorage.getItem(KEY) || "{}"));
  } catch (e) {
    return { ...DEFAULTS };
  }
}

export function savePrefs(p) {
  try {
    localStorage.setItem(KEY, JSON.stringify(sanitise(p)));
  } catch (e) {
    /* storage unavailable (private mode): preferences last for this visit only */
  }
}

export function applyPrefs(p) {
  const root = document.documentElement;
  root.setAttribute("data-theme", p.theme);
  root.setAttribute("data-font", p.fontFamily);
  root.style.setProperty("--reading-size", `${p.fontSize}px`);
  root.style.setProperty("--reading-line", String(p.lineHeight));
}
