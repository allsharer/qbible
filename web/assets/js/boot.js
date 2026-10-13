// Applies saved display preferences before the page is painted (avoids a flash
// of the wrong theme or text size). Kept tiny and dependency-free.
(function () {
  "use strict";
  var p = {};
  try { p = JSON.parse(localStorage.getItem("qbible.prefs.v1") || "{}") || {}; } catch (e) { p = {}; }
  var root = document.documentElement;
  var theme = p.theme === "light" || p.theme === "dark" ? p.theme : "system";
  root.setAttribute("data-theme", theme);
  var size = Number(p.fontSize);
  if (size >= 14 && size <= 32) root.style.setProperty("--reading-size", size + "px");
  var lh = Number(p.lineHeight);
  if (lh >= 1.3 && lh <= 2.4) root.style.setProperty("--reading-line", String(lh));
  root.setAttribute("data-font", p.fontFamily === "sans" ? "sans" : "serif");
})();
