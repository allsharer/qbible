// Bookmark and reading-history storage.
//
// Two interchangeable adapters with the same interface:
//  * ServerStore — the local qbible server's per-user database (shared with the CLI).
//  * LocalStore  — this browser's localStorage, used when the server has user
//                  data disabled (e.g. a public deployment).
// A future sync backend would be a third adapter.

import { api } from "./api.js";

export class ServerStore {
  get description() { return "Bookmarks and history are stored on this computer and shared with the qbible command line."; }
  async bookmarks() { return (await api.user.bookmarks()).bookmarks; }
  async addBookmark(translation, key, display, label) {
    const r = await api.user.addBookmark(translation, key, label || "");
    return { bookmark: r.bookmark, created: r.created };
  }
  async removeBookmark(id) { await api.user.removeBookmark(id); }
  async history(limit = 30) { return (await api.user.history(limit)).history; }
  async record(translation, key) { await api.user.record(translation, key); }
  async clearHistory() { await api.user.clearHistory(); }
}

const BM_KEY = "qbible.bookmarks.v1";
const HIST_KEY = "qbible.history.v1";
const MAX_HISTORY = 100;

function read(key) {
  try {
    const v = JSON.parse(localStorage.getItem(key) || "[]");
    return Array.isArray(v) ? v : [];
  } catch (e) { return []; }
}
function write(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) { /* ignore */ }
}
const now = () => new Date().toISOString().replace(/\.\d+Z$/, "Z");

export class LocalStore {
  get description() { return "Bookmarks and history are stored in this browser only."; }
  async bookmarks() { return read(BM_KEY); }
  async addBookmark(translation, key, display, label) {
    const list = read(BM_KEY);
    const existing = list.find((b) => b.translation === translation && b.key === key);
    if (existing) {
      if (label) { existing.label = label; existing.updated_at = now(); write(BM_KEY, list); }
      return { bookmark: existing, created: false };
    }
    const id = list.reduce((m, b) => Math.max(m, b.id), 0) + 1;
    const bm = { id, translation, key, reference: display, label: label || "", created_at: now(), updated_at: now() };
    list.unshift(bm);
    write(BM_KEY, list);
    return { bookmark: bm, created: true };
  }
  async removeBookmark(id) { write(BM_KEY, read(BM_KEY).filter((b) => b.id !== Number(id))); }
  async history(limit = 30) { return read(HIST_KEY).slice(0, limit); }
  async record(translation, key, display) {
    const list = read(HIST_KEY).filter((h) => !(h.translation === translation && h.key === key));
    const id = list.reduce((m, h) => Math.max(m, h.id), 0) + 1;
    list.unshift({ id, translation, key, reference: display, opened_at: now() });
    write(HIST_KEY, list.slice(0, MAX_HISTORY));
  }
  async clearHistory() { write(HIST_KEY, []); }
}
