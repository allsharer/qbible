// qbible browser interface. No framework, no third-party code.
// All scripture text is inserted with textContent / DOM nodes, never innerHTML.

import { api, ApiError } from "./api.js";
import { applyPrefs, DEFAULTS, FONT_MAX, FONT_MIN, FONT_STEP, loadPrefs, savePrefs } from "./prefs.js";
import { LocalStore, ServerStore } from "./store.js";

const $ = (id) => document.getElementById(id);

const state = {
  info: null,
  translation: "kjv",
  translationInfo: null,
  books: [],
  byId: new Map(),
  bySlug: new Map(),
  store: null,
  prefs: loadPrefs(),
  passage: null, // last passage payload
  flatVerses: [], // [{chapter, verse, text, el}]
  selection: null, // {anchor, start, end} indices into flatVerses
  bookmarks: [],
  search: null, // {params, offset, total}
  pendingNotice: null,
  pendingBookmark: null, // {key, display}
  firstRoute: true,
};

// ---------------------------------------------------------------- helpers

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === undefined || v === null || v === false) continue;
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (k.startsWith("data-")) node.setAttribute(k, v === true ? "" : v);
    else if (k in node) node[k] = v;
    else node.setAttribute(k, v);
  }
  for (const c of children) if (c !== null && c !== undefined) node.append(c);
  return node;
}

let toastTimer = null;
function toast(message) {
  const t = $("toast");
  t.textContent = message;
  t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), 2200);
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch (e) {
    const ta = el("textarea", { value: text, readOnly: true });
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.append(ta);
    ta.select();
    let ok = false;
    try { ok = document.execCommand("copy"); } catch (e2) { ok = false; }
    ta.remove();
    return ok;
  }
}

function chapterName(book, chapter) {
  return `${book.id === "PSA" ? "Psalm" : book.name} ${chapter}`;
}

const KEY_RE = /^([0-9A-Z]{3})(?:\.(\d+)(?:\.(\d+))?)?(?:-([0-9A-Z]{3})\.(\d+)(?:\.(\d+))?)?$/;

/** Stable URL for a reference key, e.g. JHN.3.16-JHN.3.21 -> /bible/kjv/john/3/16-21 */
export function pathForKey(t, key) {
  const m = KEY_RE.exec(key || "");
  const book = m && state.byId.get(m[1]);
  if (!book) return "/";
  const base = `/bible/${encodeURIComponent(t)}/${book.slug}`;
  const [c1, v1, c2, v2] = [m[2], m[3], m[5], m[6]];
  if (!c1) return base;
  if (!v1) return c2 && c2 !== c1 ? `${base}/${c1}-${c2}` : `${base}/${c1}`;
  if (!c2) return `${base}/${c1}/${v1}`;
  if (c2 === c1) return `${base}/${c1}/${v1}-${v2}`;
  return `${base}/${c1}/${v1}-${c2}:${v2}`;
}

function navigate(path, { replace = false, notice = null } = {}) {
  state.pendingNotice = notice;
  if (replace) history.replaceState({}, "", path);
  else history.pushState({}, "", path);
  route();
}

function showView(id) {
  for (const v of ["view-passage", "view-search", "view-message"]) $(v).hidden = v !== id;
  const sel = document.querySelector(".selectors");
  sel.hidden = id === "view-search";
}

function focusHeading(id) {
  if (state.firstRoute) return;
  const h = $(id);
  if (h) h.focus({ preventScroll: false });
}

function setTitle(text) {
  document.title = text ? `${text} – qbible` : "qbible";
}

function showNotice(node) {
  const n = $("notice");
  n.replaceChildren();
  if (!node) { n.hidden = true; return; }
  n.append(node);
  n.hidden = false;
}

function showMessage(title, message, actions = []) {
  showView("view-message");
  $("message-title").textContent = title;
  $("message-text").textContent = message;
  $("message-actions").replaceChildren(...actions.flatMap((a, i) => (i ? [" · ", a] : [a])));
  setTitle(title);
  focusHeading("message-title");
}

function searchLink(q, label) {
  return el("a", { href: `/search?q=${encodeURIComponent(q)}`, "data-nav": true,
    text: label || `Search for “${q}” as words instead` });
}

// ---------------------------------------------------------------- routing

async function route() {
  const notice = state.pendingNotice;
  state.pendingNotice = null;
  clearSelection();
  hideBookmarkForm();
  const path = decodeURIComponent(location.pathname);
  try {
    if (path === "/" || path === "/index.html") {
      const hist = await state.store.history(1).catch(() => []);
      const target = hist.length ? pathForKey(hist[0].translation, hist[0].key)
        : `/bible/${state.translation}/genesis/1`;
      history.replaceState({}, "", target);
      return await route();
    }
    if (path === "/search") {
      showNotice(null);
      await showSearch(new URLSearchParams(location.search));
      return;
    }
    const m = /^\/bible\/([a-z0-9-]+)\/([a-z0-9-]+)(?:\/([0-9]+(?:-[0-9]+)?))?(?:\/([0-9]+(?:-[0-9]+(?::[0-9]+)?)?))?\/?$/.exec(path);
    if (m) {
      const [, t, slug, chapter, verses] = m;
      const book = state.bySlug.get(slug);
      if (t !== state.translation) {
        showMessage("Translation not available", `The translation “${t}” is not installed.`,
          [el("a", { href: `/bible/${state.translation}/${slug}/${chapter || 1}`, "data-nav": true, text: `Open in ${state.translationInfo.abbreviation}` })]);
        return;
      }
      if (!book) {
        showMessage("Book not found", `“${slug}” is not a book of the Bible.`, [searchLink(slug)]);
        return;
      }
      let ref = book.id;
      if (chapter) ref += ` ${chapter}`;
      if (verses) ref += `:${verses}`;
      await showPassage(ref, notice);
      return;
    }
    showMessage("Page not found", "That address does not match a passage or a search.",
      [el("a", { href: "/", "data-nav": true, text: "Go to your reading" })]);
  } finally {
    state.firstRoute = false;
    // Completion signal (used by automated browser tests).
    document.body.dataset.routes = String(Number(document.body.dataset.routes || 0) + 1);
  }
}

// ---------------------------------------------------------------- passage

async function showPassage(ref, notice) {
  let data;
  try {
    data = await api.passage(state.translation, ref);
  } catch (e) {
    if (e instanceof ApiError && e.status >= 400 && e.status < 500) {
      showMessage("Passage not found", e.message, [el("a", { href: "/", "data-nav": true, text: "Back to your reading" })]);
      return;
    }
    showMessage("Something went wrong", e.message || String(e));
    return;
  }
  state.passage = data;
  renderPassage(data);
  showView("view-passage");
  if (notice && notice.query) {
    showNotice(el("span", {}, `Opened ${data.reference.display} for “${notice.query}”. `, searchLink(notice.query)));
  } else {
    showNotice(null);
  }
  const display = data.reference.display;
  setTitle(`${display} (${data.translation.abbreviation})`);
  updateSelectors(data);
  updateBookmarkButton();
  // Scroll to the top of the passage on navigation.
  if (!state.firstRoute) window.scrollTo({ top: 0 });
  focusHeading("passage-title");
  try {
    await state.store.record(state.translation, data.reference.key, display);
  } catch (e) { /* history is best-effort */ }
  refreshHistory();
}

function renderPassage(data) {
  const p = state.prefs;
  const ref = data.reference;
  const book = ref.book;
  $("passage-title").textContent = ref.display;
  $("passage-translation").textContent = data.translation.name;

  const whole = $("whole-chapter-link");
  const single = ref.start.chapter === ref.end.chapter;
  const isWhole = ref.whole_chapters || (single && ref.start.verse === 1 && ref.end.verse === ref.chapter_verse_count);
  whole.hidden = isWhole || !single;
  if (!whole.hidden) {
    whole.href = pathForKey(state.translation, `${book.id}.${ref.start.chapter}`);
    whole.textContent = `Show all of ${chapterName(book, ref.start.chapter)}`;
  }

  for (const [where, nav] of [["prev", data.previous], ["next", data.next]]) {
    for (const pos of ["top", "bottom"]) {
      const a = $(`${where}-${pos}`);
      if (nav) {
        a.hidden = false;
        a.href = pathForKey(state.translation, nav.key);
        a.querySelector(".t").textContent = nav.display;
        a.setAttribute("aria-label", `${where === "prev" ? "Previous" : "Next"} chapter: ${nav.display}`);
      } else {
        a.hidden = true;
      }
    }
  }

  const article = $("passage");
  article.className = `passage layout-${p.layout}${p.verseNumbers ? "" : " no-numbers"}`;
  article.dataset.supplied = p.supplied;
  article.setAttribute("aria-label", `${ref.display}, ${data.translation.name}`);
  article.replaceChildren();
  state.flatVerses = [];
  const multi = data.chapters.length > 1;
  for (const ch of data.chapters) {
    if (multi) article.append(el("h2", { text: chapterName(book, ch.chapter) }));
    let para = null;
    for (const v of ch.verses) {
      if (!para || (p.layout === "paragraphs" && v.paragraph)) {
        para = el("p");
        article.append(para);
      }
      const span = el("span", { class: "verse", id: `v${ch.chapter}-${v.verse}`,
        "data-chapter": String(ch.chapter), "data-verse": String(v.verse) });
      const idx = state.flatVerses.length;
      const btn = el("button", { type: "button", class: "vnum", text: String(v.verse),
        "aria-label": `Verse ${v.verse}: select`, "data-index": String(idx) });
      span.append(btn);
      for (const part of v.parts) {
        span.append(part.supplied ? el("i", { class: "supplied", text: part.text }) : document.createTextNode(part.text));
      }
      para.append(span, document.createTextNode(" "));
      state.flatVerses.push({ chapter: ch.chapter, verse: v.verse, text: v.text, parts: v.parts, el: span });
    }
  }
}

function plainOf(v) {
  if (state.prefs.supplied === "brackets") return v.parts.map((p) => (p.supplied ? `[${p.text}]` : p.text)).join("");
  return v.text;
}

function rangeInfo(start, end) {
  const book = state.passage.reference.book;
  const a = state.flatVerses[start];
  const b = state.flatVerses[end];
  let display;
  let key;
  if (start === end) {
    display = `${chapterName(book, a.chapter)}:${a.verse}`;
    key = `${book.id}.${a.chapter}.${a.verse}`;
  } else if (a.chapter === b.chapter) {
    display = `${chapterName(book, a.chapter)}:${a.verse}-${b.verse}`;
    key = `${book.id}.${a.chapter}.${a.verse}-${book.id}.${b.chapter}.${b.verse}`;
  } else {
    display = `${book.name} ${a.chapter}:${a.verse}-${b.chapter}:${b.verse}`;
    key = `${book.id}.${a.chapter}.${a.verse}-${book.id}.${b.chapter}.${b.verse}`;
  }
  return { display, key };
}

function passageText(start, end, label) {
  const verses = state.flatVerses.slice(start, end + 1);
  const display = label || rangeInfo(start, end).display;
  const abbr = state.passage.translation.abbreviation;
  if (verses.length === 1) return `${plainOf(verses[0])}\n— ${display} (${abbr})`;
  const lines = [];
  let lastChapter = null;
  const multiChapter = verses[0].chapter !== verses[verses.length - 1].chapter;
  for (const v of verses) {
    if (multiChapter && v.chapter !== lastChapter) lines.push(`[${v.chapter}]`);
    lastChapter = v.chapter;
    lines.push(`${v.verse} ${plainOf(v)}`);
  }
  return `${display} (${abbr})\n${lines.join("\n")}`;
}

// ---------------------------------------------------------------- selection

function selectVerse(index, extend) {
  const sel = state.selection;
  if (extend && sel) {
    const a = sel.anchor;
    state.selection = { anchor: a, start: Math.min(a, index), end: Math.max(a, index) };
  } else if (sel && sel.start === index && sel.end === index) {
    clearSelection();
    return;
  } else {
    state.selection = { anchor: index, start: index, end: index };
  }
  paintSelection();
}

function paintSelection() {
  const sel = state.selection;
  state.flatVerses.forEach((v, i) => {
    const on = !!sel && i >= sel.start && i <= sel.end;
    v.el.classList.toggle("selected", on);
    v.el.querySelector(".vnum").setAttribute("aria-pressed", on ? "true" : "false");
  });
  const bar = $("selection-bar");
  if (!sel) { bar.hidden = true; return; }
  const { display } = rangeInfo(sel.start, sel.end);
  $("selection-ref").textContent = `${display} selected`;
  bar.hidden = false;
}

function clearSelection() {
  state.selection = null;
  if (state.flatVerses.length) paintSelection();
  else $("selection-bar").hidden = true;
}

// ---------------------------------------------------------------- selectors

function fillSelect(select, items, value) {
  select.replaceChildren(...items.map(([v, label]) => el("option", { value: String(v), text: label })));
  if (value !== undefined) select.value = String(value);
}

function updateSelectors(data) {
  const ref = data.reference;
  const book = state.byId.get(ref.book.id);
  $("sel-book").value = book.id;
  fillSelect($("sel-chapter"), Array.from({ length: book.chapters }, (_, i) => [i + 1, String(i + 1)]), ref.start.chapter);
  const n = book.verses[ref.start.chapter - 1];
  const single = ref.start.chapter === ref.end.chapter;
  const partial = !ref.whole_chapters && single;
  fillSelect($("sel-verse"), [["", "All"], ...Array.from({ length: n }, (_, i) => [i + 1, String(i + 1)])],
    partial ? ref.start.verse : "");
  updateEndSelect(partial ? ref.start.verse : null, n, partial ? ref.end.verse : null);
}

function updateEndSelect(start, n, end) {
  const s = $("sel-verse-end");
  if (!start) {
    fillSelect(s, [["", "—"]], "");
    s.disabled = true;
    return;
  }
  s.disabled = false;
  fillSelect(s, Array.from({ length: n - start + 1 }, (_, i) => [start + i, String(start + i)]), end || start);
}

function bindSelectors() {
  $("sel-book").addEventListener("change", (e) => {
    const b = state.byId.get(e.target.value);
    navigate(`/bible/${state.translation}/${b.slug}/1`);
  });
  $("sel-chapter").addEventListener("change", (e) => {
    const b = state.byId.get($("sel-book").value);
    navigate(`/bible/${state.translation}/${b.slug}/${e.target.value}`);
  });
  $("sel-verse").addEventListener("change", (e) => {
    const b = state.byId.get($("sel-book").value);
    const c = $("sel-chapter").value;
    const v = e.target.value;
    navigate(`/bible/${state.translation}/${b.slug}/${c}` + (v ? `/${v}` : ""));
  });
  $("sel-verse-end").addEventListener("change", (e) => {
    const b = state.byId.get($("sel-book").value);
    const c = $("sel-chapter").value;
    const v = $("sel-verse").value;
    const end = e.target.value;
    navigate(`/bible/${state.translation}/${b.slug}/${c}/${v}` + (end && end !== v ? `-${end}` : ""));
  });
}

// ---------------------------------------------------------------- bookmarks & history

function isBookmarked(key) {
  return state.bookmarks.find((b) => b.translation === state.translation && b.key === key);
}

function updateBookmarkButton() {
  const btn = $("btn-bookmark-passage");
  if (!state.passage) return;
  const bm = isBookmarked(state.passage.reference.key);
  btn.setAttribute("aria-pressed", bm ? "true" : "false");
  btn.textContent = bm ? "Bookmarked" : "Bookmark";
  btn.title = bm ? "Remove this bookmark" : "Bookmark this passage";
}

function showBookmarkForm(key, display) {
  state.pendingBookmark = { key, display };
  $("bookmark-form-ref").textContent = display;
  $("bookmark-label").value = "";
  $("bookmark-form").hidden = false;
  $("bookmark-label").focus();
}

function hideBookmarkForm() {
  state.pendingBookmark = null;
  $("bookmark-form").hidden = true;
}

async function saveBookmark(key, display, label) {
  try {
    const { created, bookmark } = await state.store.addBookmark(state.translation, key, display, label);
    toast(created ? `Bookmarked ${bookmark.reference}` : `${bookmark.reference} was already bookmarked`);
  } catch (e) {
    toast(e.message || "Could not save the bookmark");
  }
  await refreshBookmarks();
}

async function removeBookmark(bm) {
  try {
    await state.store.removeBookmark(bm.id);
    toast(`Removed bookmark ${bm.reference}`);
  } catch (e) {
    toast(e.message || "Could not remove the bookmark");
  }
  await refreshBookmarks();
}

async function refreshBookmarks() {
  try { state.bookmarks = await state.store.bookmarks(); } catch (e) { state.bookmarks = []; }
  const list = $("bookmark-list");
  list.replaceChildren(...state.bookmarks.map((b) => {
    const link = el("a", { href: pathForKey(b.translation, b.key), "data-nav": true },
      b.reference + (b.translation !== state.translation ? ` (${b.translation.toUpperCase()})` : ""),
      b.label ? el("span", { class: "lbl", text: b.label }) : null);
    const rm = el("button", { type: "button", class: "btn btn-quiet remove", text: "✕",
      "aria-label": `Remove bookmark ${b.reference}`, title: "Remove bookmark" });
    rm.addEventListener("click", () => removeBookmark(b));
    return el("li", {}, link, rm);
  }));
  $("bookmark-empty").hidden = state.bookmarks.length > 0;
  updateBookmarkButton();
}

async function refreshHistory() {
  let items = [];
  try { items = await state.store.history(15); } catch (e) { items = []; }
  $("history-list").replaceChildren(...items.map((h) =>
    el("li", {}, el("a", { href: pathForKey(h.translation, h.key), "data-nav": true, text: h.reference }))));
  $("history-empty").hidden = items.length > 0;
  $("history-clear").hidden = items.length === 0;
}

// ---------------------------------------------------------------- search

async function showSearch(params) {
  showView("view-search");
  const q = (params.get("q") || "").trim();
  const mode = ["auto", "phrase", "any"].includes(params.get("mode")) ? params.get("mode") : "auto";
  const testament = ["OT", "NT"].includes(params.get("testament")) ? params.get("testament") : "";
  const sort = params.get("sort") === "relevance" ? "relevance" : "canonical";
  $("search-q").value = q;
  $("search-mode").value = mode;
  $("search-testament").value = testament;
  $("search-sort").value = sort;
  $("search-results").replaceChildren();
  $("search-results").dataset.supplied = state.prefs.supplied;
  $("search-more").hidden = true;
  $("search-refs").hidden = true;
  setTitle(q ? `Search: ${q}` : "Search");
  if (!q) {
    $("search-status").textContent = "Enter a word or phrase to search the Bible.";
    focusHeading("search-title");
    if (!state.firstRoute) $("search-q").focus();
    return;
  }
  state.search = { params: { q, mode, testament, sort }, offset: 0, total: 0 };
  $("search-status").textContent = "Searching…";
  offerReferences(q);
  await loadSearchPage();
  focusHeading("search-title");
}

async function offerReferences(q) {
  const box = $("search-refs");
  let found = [];
  try {
    const r = await api.resolve(state.translation, q);
    if (r.match) found = [r.match];
    else found = (await api.references(state.translation, q)).references;
  } catch (e) { found = []; }
  if (!found.length) return;
  box.replaceChildren(el("span", { text: found.length === 1 ? "Looking for a passage? " : "Passages mentioned: " }),
    ...found.flatMap((f, i) => [i ? ", " : "", el("a", { href: pathForKey(state.translation, f.key), "data-nav": true, text: `Open ${f.display}` })]));
  box.hidden = false;
}

async function loadSearchPage() {
  const s = state.search;
  const limit = 25;
  let data;
  try {
    data = await api.search(state.translation, { ...s.params, limit, offset: s.offset });
  } catch (e) {
    $("search-status").textContent = e.message;
    return;
  }
  s.total = data.total;
  s.offset += data.results.length;
  const list = $("search-results");
  for (const r of data.results) {
    const text = el("p", { class: "text" });
    for (const seg of r.segments) {
      let node = seg.supplied ? el("i", { class: "supplied", text: seg.text }) : document.createTextNode(seg.text);
      if (seg.match) node = el("mark", {}, node);
      text.append(node);
    }
    list.append(el("li", {},
      el("a", { class: "ref", href: pathForKey(state.translation, r.reference.key), "data-nav": true, text: r.reference.display }),
      text));
  }
  const terms = data.terms.join(" ");
  if (data.total === 0) {
    $("search-status").textContent = `No verses match ${terms}. Try fewer words, a different spelling, or “Any word”.`;
  } else {
    $("search-status").textContent =
      `${data.total} ${data.total === 1 ? "verse matches" : "verses match"} ${terms}. Showing 1–${s.offset}.`;
  }
  $("search-more").hidden = !data.has_more;
}

function submitSearchForm(e) {
  e.preventDefault();
  const q = $("search-q").value.trim();
  if (!q) { $("search-q").focus(); return; }
  const params = new URLSearchParams({ q });
  if ($("search-mode").value !== "auto") params.set("mode", $("search-mode").value);
  if ($("search-testament").value) params.set("testament", $("search-testament").value);
  if ($("search-sort").value !== "canonical") params.set("sort", $("search-sort").value);
  navigate(`/search?${params}`);
}

async function submitGoForm(e) {
  e.preventDefault();
  const q = $("go-input").value.trim();
  if (!q) { $("go-input").focus(); return; }
  let r = null;
  try { r = await api.resolve(state.translation, q); } catch (err) { r = null; }
  if (r && r.match) {
    $("go-input").value = "";
    navigate(pathForKey(state.translation, r.match.key), { notice: { query: q } });
    return;
  }
  if (r && r.error && (r.error.code === "invalid_chapter" || r.error.code === "invalid_verse")) {
    // Recognisable reference that does not exist: say so; never redirect elsewhere.
    showMessage("Passage not found", r.error.message, [searchLink(q)]);
    return;
  }
  $("go-input").value = "";
  navigate(`/search?q=${encodeURIComponent(q)}`);
}

// ---------------------------------------------------------------- settings & panels

function setPrefs(changes) {
  state.prefs = { ...state.prefs, ...changes };
  savePrefs(state.prefs);
  applyPrefs(state.prefs);
  syncSettingsForm();
  if (state.passage && ("layout" in changes || "verseNumbers" in changes || "supplied" in changes)) {
    const sel = state.selection;
    renderPassage(state.passage);
    if (sel) { state.selection = sel; paintSelection(); }
  }
  $("search-results").dataset.supplied = state.prefs.supplied;
}

function syncSettingsForm() {
  const p = state.prefs;
  $("font-size-value").textContent = `${p.fontSize} px`;
  $("font-smaller").disabled = p.fontSize <= FONT_MIN;
  $("font-larger").disabled = p.fontSize >= FONT_MAX;
  for (const r of document.querySelectorAll('input[name="fontFamily"]')) r.checked = r.value === p.fontFamily;
  for (const r of document.querySelectorAll('input[name="theme"]')) r.checked = r.value === p.theme;
  $("line-height").value = String(p.lineHeight);
  $("layout").value = p.layout;
  $("supplied").value = p.supplied;
  $("verse-numbers").checked = p.verseNumbers;
}

function bindSettings() {
  $("font-smaller").addEventListener("click", () => setPrefs({ fontSize: Math.max(FONT_MIN, state.prefs.fontSize - FONT_STEP) }));
  $("font-larger").addEventListener("click", () => setPrefs({ fontSize: Math.min(FONT_MAX, state.prefs.fontSize + FONT_STEP) }));
  $("font-reset").addEventListener("click", () => setPrefs({ fontSize: DEFAULTS.fontSize }));
  for (const r of document.querySelectorAll('input[name="fontFamily"]')) r.addEventListener("change", () => setPrefs({ fontFamily: r.value }));
  for (const r of document.querySelectorAll('input[name="theme"]')) r.addEventListener("change", () => setPrefs({ theme: r.value }));
  $("line-height").addEventListener("change", (e) => setPrefs({ lineHeight: Number(e.target.value) }));
  $("layout").addEventListener("change", (e) => setPrefs({ layout: e.target.value }));
  $("supplied").addEventListener("change", (e) => setPrefs({ supplied: e.target.value }));
  $("verse-numbers").addEventListener("change", (e) => setPrefs({ verseNumbers: e.target.checked }));
  $("btn-settings").addEventListener("click", () => toggleSettings());
  $("settings-close").addEventListener("click", () => toggleSettings(false));
}

function toggleSettings(open) {
  const panel = $("settings-panel");
  const show = open === undefined ? panel.hidden : open;
  panel.hidden = !show;
  $("btn-settings").setAttribute("aria-expanded", String(show));
  if (show) panel.querySelector("button, input, select").focus();
  else if (panel.contains(document.activeElement) || open === false) $("btn-settings").focus();
}

const wide = () => window.matchMedia("(min-width: 1100px)").matches;

function libraryVisible() {
  const pref = state.prefs.libraryOpen;
  return pref === null ? wide() : pref;
}

function applyLibrary() {
  const visible = libraryVisible();
  document.body.classList.toggle("library-open", visible);
  document.body.classList.toggle("library-closed", !visible);
  $("btn-library").setAttribute("aria-expanded", String(visible));
}

function bindLibrary() {
  $("btn-library").addEventListener("click", () => {
    const visible = !libraryVisible();
    state.prefs = { ...state.prefs, libraryOpen: visible };
    savePrefs(state.prefs);
    applyLibrary();
    if (visible && !wide()) $("sidebar").scrollIntoView({ block: "start" });
  });
  $("history-clear").addEventListener("click", async () => {
    try { await state.store.clearHistory(); toast("Reading history cleared"); } catch (e) { toast(e.message); }
    refreshHistory();
  });
}

// ---------------------------------------------------------------- events

function bindEvents() {
  // Internal links: client-side navigation (keeps middle-click / new-tab behaviour).
  document.addEventListener("click", (e) => {
    const a = e.target.closest("a[data-nav]");
    if (!a || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    const url = new URL(a.href, location.href);
    if (url.origin !== location.origin) return;
    e.preventDefault();
    navigate(url.pathname + url.search);
  });

  $("passage").addEventListener("click", (e) => {
    const btn = e.target.closest(".vnum");
    if (!btn) return;
    selectVerse(Number(btn.dataset.index), e.shiftKey);
  });

  $("btn-copy-passage").addEventListener("click", async () => {
    if (!state.flatVerses.length) return;
    const ok = await copyText(passageText(0, state.flatVerses.length - 1, state.passage.reference.display));
    toast(ok ? `Copied ${state.passage.reference.display}` : "Copy failed — select the text and copy it manually");
  });

  $("btn-bookmark-passage").addEventListener("click", () => {
    const r = state.passage.reference;
    const bm = isBookmarked(r.key);
    if (bm) removeBookmark(bm);
    else showBookmarkForm(r.key, r.display);
  });
  $("bookmark-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const pb = state.pendingBookmark;
    if (!pb) return;
    const label = $("bookmark-label").value.trim();
    hideBookmarkForm();
    await saveBookmark(pb.key, pb.display, label);
    $("btn-bookmark-passage").focus();
  });
  $("bookmark-cancel").addEventListener("click", () => { hideBookmarkForm(); $("btn-bookmark-passage").focus(); });

  $("sel-copy").addEventListener("click", async () => {
    const s = state.selection;
    if (!s) return;
    const ok = await copyText(passageText(s.start, s.end));
    toast(ok ? `Copied ${rangeInfo(s.start, s.end).display}` : "Copy failed");
  });
  $("sel-bookmark").addEventListener("click", () => {
    const s = state.selection;
    if (!s) return;
    const { key, display } = rangeInfo(s.start, s.end);
    window.scrollTo({ top: 0 });
    showBookmarkForm(key, display);
  });
  $("sel-link").addEventListener("click", async () => {
    const s = state.selection;
    if (!s) return;
    const { key, display } = rangeInfo(s.start, s.end);
    const ok = await copyText(location.origin + pathForKey(state.translation, key));
    toast(ok ? `Link to ${display} copied` : "Copy failed");
  });
  $("sel-clear").addEventListener("click", () => clearSelection());

  $("go-form").addEventListener("submit", submitGoForm);
  $("search-form").addEventListener("submit", submitSearchForm);
  $("search-more").addEventListener("click", () => loadSearchPage());

  window.addEventListener("popstate", () => route());
  window.matchMedia("(min-width: 1100px)").addEventListener("change", applyLibrary);

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      if (!$("settings-panel").hidden) { toggleSettings(false); return; }
      if (!$("bookmark-form").hidden) { hideBookmarkForm(); return; }
      if (state.selection) { clearSelection(); return; }
      return;
    }
    const t = e.target;
    if (e.altKey || e.ctrlKey || e.metaKey) return;
    if (t && (t.isContentEditable || ["INPUT", "SELECT", "TEXTAREA"].includes(t.tagName))) return;
    if (e.key === "/") { e.preventDefault(); $("go-input").focus(); return; }
    if ($("view-passage").hidden) return;
    if (e.key === "ArrowLeft" && !$("prev-top").hidden) { e.preventDefault(); $("prev-top").click(); }
    if (e.key === "ArrowRight" && !$("next-top").hidden) { e.preventDefault(); $("next-top").click(); }
  });
}

// ---------------------------------------------------------------- start-up

async function start() {
  applyPrefs(state.prefs);
  syncSettingsForm();
  bindSettings();
  bindLibrary();
  applyLibrary();
  bindSelectors();
  bindEvents();
  try {
    state.info = await api.info();
    state.store = state.info.user_data ? new ServerStore() : new LocalStore();
    state.translation = state.info.default_translation;
    const tr = await api.translations();
    state.translationInfo = tr.translations.find((t) => t.id === state.translation) || tr.translations[0];
    const books = await api.books(state.translation);
    state.books = books.books;
  } catch (e) {
    showMessage("qbible could not start", e.message || String(e));
    return;
  }
  for (const b of state.books) {
    state.byId.set(b.id, b);
    state.bySlug.set(b.slug, b);
  }
  const groups = [["OT", "Old Testament"], ["NT", "New Testament"]].map(([t, label]) =>
    el("optgroup", { label }, ...state.books.filter((b) => b.testament === t).map((b) => el("option", { value: b.id, text: b.name }))));
  $("sel-book").replaceChildren(...groups);
  $("translation-badge").textContent = state.translationInfo.abbreviation;
  $("translation-badge").title = state.translationInfo.name;
  $("attribution").textContent = state.translationInfo.attribution || state.translationInfo.name;
  $("storage-note").textContent = state.store.description;
  document.documentElement.dataset.ready = "true";
  await refreshBookmarks();
  refreshHistory();
  await route();
  document.body.dataset.ready = "true";
}

start();
