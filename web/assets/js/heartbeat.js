// Tells a local `qbible serve` that this page is still open, so the server can
// stop by itself once every qbible page has been closed (see qbible/watchdog.py).
// Only started when the server reports that its watchdog is enabled.

import { api, ApiError } from "./api.js";

function newClientId() {
  if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

/**
 * @param {number} intervalMs  how often to ping while visible (from /api/v1/info)
 * @param {{onLost: Function, onRestored: Function}} handlers  connection status callbacks
 */
export function startHeartbeat(intervalMs, { onLost, onRestored }) {
  const client = newClientId();
  let lost = false;

  async function send(closing = false) {
    try {
      await api.heartbeat(client, document.visibilityState === "visible", closing);
      if (lost) { lost = false; onRestored(); }
    } catch (e) {
      // Only a failed connection means the server has gone; ignore errors while closing.
      if (!closing && !lost && e instanceof ApiError && e.status === 0) { lost = true; onLost(); }
    }
  }

  send();
  // Background tabs are throttled by the browser; the server allows for that.
  setInterval(() => send(), intervalMs);
  document.addEventListener("visibilitychange", () => send());
  // Closing or reloading: release this page's lease quickly (keepalive request).
  window.addEventListener("pagehide", () => send(true));
  // Restored from the back/forward cache: claim a lease again straight away.
  window.addEventListener("pageshow", (e) => { if (e.persisted) send(); });
}
