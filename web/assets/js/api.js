// Thin client for the qbible JSON API (v1). See docs/API.md.

export class ApiError extends Error {
  constructor(status, code, message) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

const BASE = "/api/v1/";

async function request(method, path, params, body, { keepalive = false } = {}) {
  const url = new URL(BASE + path, window.location.origin);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v));
    }
  }
  const init = { method, headers: { Accept: "application/json" }, credentials: "same-origin", keepalive };
  if (method !== "GET") {
    init.headers["X-QBible-Request"] = "1";
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body || {});
  }
  let res;
  try {
    res = await fetch(url, init);
  } catch (e) {
    throw new ApiError(0, "network", "qbible could not reach its local server. Is 'qbible serve' still running?");
  }
  let data = null;
  try { data = await res.json(); } catch (e) { data = null; }
  if (!res.ok) {
    const err = (data && data.error) || {};
    throw new ApiError(res.status, err.code || "error", err.message || `Request failed (${res.status}).`);
  }
  return data;
}

export const api = {
  info: () => request("GET", "info"),
  translations: () => request("GET", "translations"),
  books: (t) => request("GET", `translations/${encodeURIComponent(t)}/books`),
  passage: (t, ref) => request("GET", "passage", { t, ref }),
  resolve: (t, q) => request("GET", "resolve", { t, q }),
  references: (t, text) => request("GET", "references", { t, text }),
  search: (t, params) => request("GET", "search", { t, ...params }),
  random: (t) => request("GET", "random", { t }),
  heartbeat: (client, visible, closing) =>
    request("POST", "heartbeat", null, { client, visible, closing }, { keepalive: closing }),
  user: {
    bookmarks: () => request("GET", "user/bookmarks"),
    addBookmark: (translation, ref, label) => request("POST", "user/bookmarks", null, { translation, ref, label }),
    removeBookmark: (id) => request("DELETE", `user/bookmarks/${encodeURIComponent(id)}`),
    history: (limit) => request("GET", "user/history", { limit }),
    record: (translation, ref) => request("POST", "user/history", null, { translation, ref }),
    clearHistory: () => request("DELETE", "user/history"),
  },
};
