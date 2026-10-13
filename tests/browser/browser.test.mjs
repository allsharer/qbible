// End-to-end browser tests: real qbible server + headless Chrome (puppeteer-core).
//
//   npm install         (once; installs puppeteer-core only — no browser download)
//   npm run test:browser
//
// Chrome is found via $CHROME_PATH or common install locations. The server runs
// with temporary user-data/config directories, so real user data is never touched.

import { test, before, after, describe } from "node:test";
import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import { mkdtempSync, rmSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import puppeteer from "puppeteer-core";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const CHROME = process.env.CHROME_PATH ||
  ["/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/bin/chromium", "/usr/bin/chromium-browser"]
    .find((p) => existsSync(p));

async function startServer(extraArgs = [], { withTestTranslation = false, env: extraEnv = {} } = {}) {
  const home = mkdtempSync(join(tmpdir(), "qbible-browser-"));
  const env = { ...process.env, QBIBLE_DATA_HOME: join(home, "data"), QBIBLE_CONFIG_HOME: join(home, "config"),
    ...extraEnv };
  if (withTestTranslation) {
    const r = spawnSync("python3", ["-m", "qbible", "import", join(ROOT, "tests/browser/fixtures/test-translation.tsv"),
      "--id", "test", "--name", "Test Translation", "--abbreviation", "TST", "--licence", "Test fixture",
      "--attribution", "Synthetic test fixture."], { cwd: ROOT, env, encoding: "utf8" });
    if (r.status !== 0) throw new Error(`fixture import failed: ${r.stderr}`);
  }
  const proc = spawn("python3", ["-m", "qbible", "serve", "--port", "0", ...extraArgs], {
    cwd: ROOT,
    env,
    stdio: ["ignore", "pipe", "pipe"],
  });
  let buf = "";
  let exitCode = null;
  const exited = new Promise((resolve) => proc.on("exit", (code) => { exitCode = code; resolve(code); }));
  const url = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`server did not start: ${buf}`)), 15000);
    proc.stderr.on("data", (d) => {
      buf += d;
      const m = /running at (http:\/\/[^\s]+)/.exec(buf);
      if (m) { clearTimeout(timer); resolve(m[1].replace(/\/$/, "")); }
    });
    exited.then((code) => reject(new Error(`server exited ${code}: ${buf}`)));
  });
  return { url, proc, home, output: () => buf, exited, running: () => exitCode === null && proc.exitCode === null };
}

function stopServer(s) {
  if (!s) return;
  s.proc.kill("SIGINT");
  rmSync(s.home, { recursive: true, force: true });
}

async function routes(page) {
  return Number(await page.evaluate(() => document.body.dataset.routes || 0));
}
async function waitRoute(page, n) {
  await page.waitForFunction((n) => Number(document.body.dataset.routes || 0) > n, { timeout: 10000 }, n);
}
async function goto(page, url) {
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.body.dataset.ready === "true", { timeout: 10000 });
}
const text = (page, sel) => page.$eval(sel, (e) => e.textContent.trim());

describe("qbible browser interface", { skip: !CHROME && "Chrome/Chromium not found (set CHROME_PATH)" }, () => {
  let server;
  let browser;
  let page;
  const requests = [];

  before(async () => {
    server = await startServer();
    browser = await puppeteer.launch({ executablePath: CHROME, headless: true,
      args: ["--no-sandbox", "--disable-gpu", "--no-first-run", "--disable-extensions"] });
    page = await browser.newPage();
    await page.setViewport({ width: 1280, height: 900 });
    page.on("request", (r) => requests.push(r.url()));
    page.on("dialog", (d) => d.dismiss());
  });

  after(async () => {
    if (browser) await browser.close();
    stopServer(server);
  });

  test("home opens Genesis 1 when there is no history, with a meaningful title", async () => {
    await goto(page, server.url + "/");
    assert.equal(await text(page, "#passage-title"), "Genesis 1");
    assert.match(await page.title(), /^Genesis 1 \(KJV\) – qbible$/);
    assert.equal(new URL(page.url()).pathname, "/bible/kjv/genesis/1");
    const first = await text(page, "#v1-1");
    assert.match(first, /In the beginning God created the heaven and the earth\./);
    assert.equal(await text(page, "#translation-badge"), "KJV");
    // With only one translation installed, a badge is shown instead of the picker.
    assert.equal(await page.$eval("#translation-picker", (e) => e.hidden), true);
    assert.equal(await page.$eval("#translation-badge", (e) => e.hidden), false);
  });

  test("direct passage URLs: verse, range and chapter", async () => {
    await goto(page, server.url + "/bible/kjv/john/3/16");
    assert.equal(await text(page, "#passage-title"), "John 3:16");
    assert.equal((await page.$$("#passage .verse")).length, 1);
    assert.match(await text(page, "#v3-16"), /For God so loved the world/);
    assert.equal(await page.$eval("#whole-chapter-link", (e) => e.hidden), false);

    await goto(page, server.url + "/bible/kjv/1-corinthians/13/4-7");
    assert.equal(await text(page, "#passage-title"), "1 Corinthians 13:4-7");
    assert.equal((await page.$$("#passage .verse")).length, 4);

    await goto(page, server.url + "/bible/kjv/psalms/23");
    assert.equal(await text(page, "#passage-title"), "Psalm 23");
    assert.equal((await page.$$("#passage .verse")).length, 6);
  });

  test("invalid passage URLs are reported, not redirected", async () => {
    await goto(page, server.url + "/bible/kjv/john/22");
    assert.equal(await page.$eval("#view-message", (e) => e.hidden), false);
    assert.match(await text(page, "#message-text"), /John has 21 chapters; there is no chapter 22\./);
    await goto(page, server.url + "/bible/kjv/hezekiah/1");
    assert.match(await text(page, "#message-text"), /not a book/);
  });

  test("book and chapter selectors navigate; Back and Forward work", async () => {
    await goto(page, server.url + "/bible/kjv/genesis/1");
    let n = await routes(page);
    await page.select("#sel-book", "ROM");
    await waitRoute(page, n);
    assert.equal(new URL(page.url()).pathname, "/bible/kjv/romans/1");
    n = await routes(page);
    await page.select("#sel-chapter", "8");
    await waitRoute(page, n);
    assert.equal(await text(page, "#passage-title"), "Romans 8");
    n = await routes(page);
    await page.select("#sel-verse", "28");
    await waitRoute(page, n);
    assert.equal(await text(page, "#passage-title"), "Romans 8:28");
    n = await routes(page);
    await page.select("#sel-verse-end", "30");
    await waitRoute(page, n);
    assert.equal(await text(page, "#passage-title"), "Romans 8:28-30");

    n = await routes(page);
    await page.click("#next-top");
    await waitRoute(page, n);
    assert.equal(await text(page, "#passage-title"), "Romans 9");

    n = await routes(page);
    await page.goBack();
    await waitRoute(page, n);
    assert.equal(await text(page, "#passage-title"), "Romans 8:28-30");
    n = await routes(page);
    await page.goForward();
    await waitRoute(page, n);
    assert.equal(await text(page, "#passage-title"), "Romans 9");

    n = await routes(page);
    await page.click("#prev-bottom");
    await waitRoute(page, n);
    assert.equal(await text(page, "#passage-title"), "Romans 8");
  });

  test("chapter navigation crosses book boundaries", async () => {
    await goto(page, server.url + "/bible/kjv/malachi/4");
    assert.equal(await page.$eval("#next-top .t", (e) => e.textContent), "Matthew 1");
    await goto(page, server.url + "/bible/kjv/genesis/1");
    assert.equal(await page.$eval("#prev-top", (e) => e.hidden), true);
  });

  test("the navigation field opens references directly and searches otherwise", async () => {
    await goto(page, server.url + "/bible/kjv/genesis/1");
    let n = await routes(page);
    await page.type("#go-input", "rom 8:28");
    await page.keyboard.press("Enter");
    await waitRoute(page, n);
    assert.equal(await text(page, "#passage-title"), "Romans 8:28");
    assert.match(await text(page, "#notice"), /Search for “rom 8:28” as words instead/);

    n = await routes(page);
    await page.type("#go-input", '"faith without works"');
    await page.keyboard.press("Enter");
    await waitRoute(page, n);
    await page.waitForFunction(() => document.querySelectorAll("#search-results li").length > 0);
    assert.equal((await page.$$("#search-results li")).length, 2);
    assert.match(await text(page, "#search-status"), /^2 verses match "faith without works"/);
    const marks = await page.$$eval("#search-results mark", (ms) => ms.map((m) => m.textContent));
    assert.deepEqual(marks, ["faith without works", "faith without works"]);

    n = await routes(page);
    await page.click("#search-results li a");
    await waitRoute(page, n);
    assert.equal(await text(page, "#passage-title"), "James 2:20");
  });

  test("a nonexistent chapter typed in the field is reported", async () => {
    await page.type("#go-input", "John 22");
    await page.keyboard.press("Enter");
    await page.waitForFunction(() => !document.getElementById("view-message").hidden);
    assert.match(await text(page, "#message-text"), /John has 21 chapters/);
  });

  test("search: pagination, empty results, reference offers", async () => {
    await goto(page, server.url + "/search?q=love");
    await page.waitForFunction(() => document.querySelectorAll("#search-results li").length === 25);
    assert.match(await text(page, "#search-status"), /^\d+ verses match love/);
    await page.click("#search-more");
    await page.waitForFunction(() => document.querySelectorAll("#search-results li").length === 50);

    await goto(page, server.url + "/search?q=zzzqqq");
    await page.waitForFunction(() => /No verses match/.test(document.getElementById("search-status").textContent));

    await goto(page, server.url + "/search?q=" + encodeURIComponent("all things work together Romans 8:28"));
    await page.waitForFunction(() => !document.getElementById("search-refs").hidden);
    assert.match(await text(page, "#search-refs"), /Open Romans 8:28/);
  });

  test("search text is rendered safely (no HTML injection)", async () => {
    const payload = '<img src=x onerror="window.__pwned=1">';
    await goto(page, server.url + "/search?q=" + encodeURIComponent(payload));
    await page.waitForFunction(() => /match|No verses/.test(document.getElementById("search-status").textContent));
    assert.equal(await page.$("#view-search img"), null);
    assert.equal(await page.evaluate(() => window.__pwned), undefined);
    assert.equal(await page.$eval("#search-q", (e) => e.value), payload);
  });

  test("font size controls change, persist and reset", async () => {
    await goto(page, server.url + "/bible/kjv/john/1");
    const size = () => page.evaluate(() => getComputedStyle(document.getElementById("passage")).fontSize);
    assert.equal(await size(), "20px");
    await page.click("#btn-settings");
    assert.equal(await page.$eval("#settings-panel", (e) => e.hidden), false);
    await page.click("#font-larger");
    await page.click("#font-larger");
    assert.equal(await size(), "24px");
    assert.equal(await text(page, "#font-size-value"), "24 px");
    await goto(page, server.url + "/bible/kjv/john/1");
    assert.equal(await size(), "24px", "font size persists after reload");
    await page.click("#btn-settings");
    await page.click("#font-smaller");
    assert.equal(await size(), "22px");
    await page.click("#font-reset");
    assert.equal(await size(), "20px");
    for (let i = 0; i < 12; i++) await page.$eval("#font-larger", (b) => b.click());
    assert.equal(await size(), "32px", "maximum is 32px");
    assert.equal(await page.$eval("#font-larger", (b) => b.disabled), true);
    await page.click("#font-reset");
  });

  test("font family choice applies and persists", async () => {
    await page.click('input[name="fontFamily"][value="sans"]');
    const fam = () => page.evaluate(() => getComputedStyle(document.getElementById("passage")).fontFamily);
    assert.match(await fam(), /system-ui|sans/);
    await goto(page, server.url + "/bible/kjv/john/1");
    assert.match(await fam(), /system-ui|sans/);
    await page.click("#btn-settings");
    await page.click('input[name="fontFamily"][value="serif"]');
    assert.match(await fam(), /serif/);
    assert.doesNotMatch(await fam(), /^system-ui/);
  });

  test("theme switching (light, dark, system) persists", async () => {
    const bg = () => page.evaluate(() => getComputedStyle(document.body).backgroundColor);
    await page.click('input[name="theme"][value="dark"]');
    assert.equal(await page.evaluate(() => document.documentElement.dataset.theme), "dark");
    assert.equal(await bg(), "rgb(21, 23, 27)");
    await goto(page, server.url + "/bible/kjv/john/1");
    assert.equal(await bg(), "rgb(21, 23, 27)", "dark theme persists");
    await page.click("#btn-settings");
    await page.click('input[name="theme"][value="light"]');
    assert.equal(await bg(), "rgb(251, 250, 247)");
    await page.emulateMediaFeatures([{ name: "prefers-color-scheme", value: "dark" }]);
    await page.click('input[name="theme"][value="system"]');
    assert.equal(await bg(), "rgb(21, 23, 27)", "system theme follows the OS preference");
    await page.emulateMediaFeatures([{ name: "prefers-color-scheme", value: "light" }]);
    assert.equal(await bg(), "rgb(251, 250, 247)");
    await page.keyboard.press("Escape");
    assert.equal(await page.$eval("#settings-panel", (e) => e.hidden), true);
  });

  test("bookmarks: add with label, persist, open, remove", async () => {
    await goto(page, server.url + "/bible/kjv/john/3/16");
    await page.click("#btn-bookmark-passage");
    await page.type("#bookmark-label", "God's love");
    await page.click('#bookmark-form button[type="submit"]');
    await page.waitForFunction(() => document.querySelectorAll("#bookmark-list li").length === 1);
    assert.match(await text(page, "#bookmark-list li"), /John 3:16\s*God's love/);
    assert.equal(await page.$eval("#btn-bookmark-passage", (b) => b.getAttribute("aria-pressed")), "true");

    // Select verses via verse numbers and bookmark the selection.
    await goto(page, server.url + "/bible/kjv/psalms/23");
    await page.click("#v23-1 .vnum");
    await page.keyboard.down("Shift");
    await page.click("#v23-3 .vnum");
    await page.keyboard.up("Shift");
    assert.equal(await text(page, "#selection-ref"), "Psalm 23:1-3 selected");
    await page.click("#sel-bookmark");
    await page.click('#bookmark-form button[type="submit"]');
    await page.waitForFunction(() => document.querySelectorAll("#bookmark-list li").length === 2);

    await goto(page, server.url + "/bible/kjv/genesis/1");
    assert.equal((await page.$$("#bookmark-list li")).length, 2, "bookmarks persist");
    const n = await routes(page);
    await page.click("#bookmark-list li:last-child a");
    await waitRoute(page, n);
    assert.equal(await text(page, "#passage-title"), "John 3:16");

    await page.click('#bookmark-list li:last-child button.remove');
    await page.waitForFunction(() => document.querySelectorAll("#bookmark-list li").length === 1);
  });

  test("bookmarks made in the browser are visible to the CLI's store via the API", async () => {
    const res = await page.evaluate(() => fetch("/api/v1/user/bookmarks").then((r) => r.json()));
    assert.equal(res.bookmarks.length, 1);
    assert.equal(res.bookmarks[0].key, "PSA.23.1-PSA.23.3");
  });

  test("reading history lists recent passages and can be cleared", async () => {
    await goto(page, server.url + "/bible/kjv/ruth/1");
    await page.waitForFunction(() => /Ruth 1/.test(document.getElementById("history-list").textContent));
    const items = await page.$$eval("#history-list a", (as) => as.map((a) => a.textContent));
    assert.equal(items[0], "Ruth 1");
    assert.ok(items.includes("John 3:16"));
    await page.click("#history-clear");
    await page.waitForFunction(() => document.querySelectorAll("#history-list li").length === 0);
    assert.equal(await page.$eval("#history-empty", (e) => e.hidden), false);
  });

  test("copying a selected verse includes its reference", async () => {
    const ctx = browser.defaultBrowserContext();
    await ctx.overridePermissions(server.url, ["clipboard-read", "clipboard-write", "clipboard-sanitized-write"]);
    await goto(page, server.url + "/bible/kjv/john/11");
    await page.click("#v11-35 .vnum");
    await page.click("#sel-copy");
    await page.waitForFunction(() => /Copied/.test(document.getElementById("toast").textContent));
    const clip = await page.evaluate(() => navigator.clipboard.readText());
    assert.equal(clip, "Jesus wept.\n— John 11:35 (KJV)");
  });

  test("keyboard: arrow keys change chapter, / focuses search, verse numbers are focusable", async () => {
    await goto(page, server.url + "/bible/kjv/john/1");
    await page.evaluate(() => document.activeElement && document.activeElement.blur());
    let n = await routes(page);
    await page.keyboard.press("ArrowRight");
    await waitRoute(page, n);
    assert.equal(await text(page, "#passage-title"), "John 2");
    n = await routes(page);
    await page.keyboard.press("ArrowLeft");
    await waitRoute(page, n);
    assert.equal(await text(page, "#passage-title"), "John 1");
    // focus moved to the heading after navigation
    assert.equal(await page.evaluate(() => document.activeElement.id), "passage-title");
    await page.keyboard.press("/");
    assert.equal(await page.evaluate(() => document.activeElement.id), "go-input");
    await page.focus("#v1-1 .vnum");
    await page.keyboard.press("Enter");
    assert.equal(await text(page, "#selection-ref"), "John 1:1 selected");
    await page.keyboard.press("Escape");
    assert.equal(await page.$eval("#selection-bar", (e) => e.hidden), true);
  });

  test("responsive: no horizontal scrolling on a phone, even at the largest text size", async () => {
    await page.setViewport({ width: 360, height: 740, isMobile: true, hasTouch: true });
    await goto(page, server.url + "/bible/kjv/esther/8");
    const overflow = () => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    assert.ok((await overflow()) <= 0, "no horizontal overflow at default size");
    await page.evaluate(() => localStorage.setItem("qbible.prefs.v1", JSON.stringify({ fontSize: 32 })));
    await goto(page, server.url + "/bible/kjv/esther/8");
    assert.ok((await overflow()) <= 0, "no horizontal overflow at 32px");
    // The sidebar is collapsed on narrow screens and can be opened.
    assert.equal(await page.$eval("#sidebar", (e) => getComputedStyle(e).display), "none");
    await page.click("#btn-library");
    assert.equal(await page.$eval("#sidebar", (e) => getComputedStyle(e).display), "block");
    await page.evaluate(() => localStorage.clear());
    await page.setViewport({ width: 1280, height: 900 });
  });

  test("print stylesheet hides navigation and controls", async () => {
    await goto(page, server.url + "/bible/kjv/john/1");
    await page.emulateMediaType("print");
    const hidden = await page.$$eval(".topbar, .selectors, .chapter-nav, .sidebar",
      (els) => els.every((e) => getComputedStyle(e).display === "none"));
    await page.emulateMediaType(null);
    assert.ok(hidden);
  });

  test("works offline: every request goes to the local server", async () => {
    const external = requests.filter((u) => !u.startsWith(server.url) && !u.startsWith("data:"));
    assert.deepEqual(external, []);
  });
});

describe("browser-only storage mode (--no-user-data)", { skip: !CHROME && "Chrome/Chromium not found" }, () => {
  let server;
  let browser;
  let page;
  before(async () => {
    server = await startServer(["--no-user-data"]);
    browser = await puppeteer.launch({ executablePath: CHROME, headless: true, args: ["--no-sandbox"] });
    page = await browser.newPage();
    await page.setViewport({ width: 1280, height: 900 });
  });
  after(async () => {
    if (browser) await browser.close();
    stopServer(server);
  });

  test("bookmarks and history are kept in localStorage", async () => {
    await goto(page, server.url + "/bible/kjv/john/3/16");
    await page.click("#btn-bookmark-passage");
    await page.click('#bookmark-form button[type="submit"]');
    await page.waitForFunction(() => document.querySelectorAll("#bookmark-list li").length === 1);
    const stored = await page.evaluate(() => JSON.parse(localStorage.getItem("qbible.bookmarks.v1")));
    assert.equal(stored[0].key, "JHN.3.16");
    await goto(page, server.url + "/bible/kjv/john/4");
    assert.equal((await page.$$("#bookmark-list li")).length, 1);
    const hist = await page.evaluate(() => JSON.parse(localStorage.getItem("qbible.history.v1")));
    assert.equal(hist[0].key, "JHN.4");
    const status = await page.evaluate(() => fetch("/api/v1/user/bookmarks").then((r) => r.status));
    assert.equal(status, 404);
  });
});

describe("translation picker (two translations installed)", { skip: !CHROME && "Chrome/Chromium not found" }, () => {
  let server;
  let browser;
  let page;
  before(async () => {
    server = await startServer([], { withTestTranslation: true });
    browser = await puppeteer.launch({ executablePath: CHROME, headless: true, args: ["--no-sandbox"] });
    page = await browser.newPage();
    await page.setViewport({ width: 1280, height: 900 });
  });
  after(async () => {
    if (browser) await browser.close();
    stopServer(server);
  });

  const pickTranslation = async (id) => {
    const n = await routes(page);
    await page.select("#translation-select", id);
    await waitRoute(page, n);
  };

  test("picker lists installed translations, default first, with an accessible label", async () => {
    await goto(page, server.url + "/bible/kjv/john/3");
    assert.equal(await page.$eval("#translation-picker", (e) => e.hidden), false);
    assert.equal(await page.$eval("#translation-badge", (e) => e.hidden), true);
    const options = await page.$$eval("#translation-select option", (os) => os.map((o) => [o.value, o.textContent]));
    assert.deepEqual(options, [["kjv", "KJV"], ["test", "TST"]]);
    assert.equal(await page.$eval("#translation-select", (s) => s.value), "kjv");
    assert.equal(await page.$eval("#translation-picker", (l) => l.textContent.trim().startsWith("Translation")), true);
  });

  test("switching keeps the same passage, updates URL, books and attribution; Back restores", async () => {
    await goto(page, server.url + "/bible/kjv/john/3");
    await pickTranslation("test");
    assert.equal(new URL(page.url()).pathname, "/bible/test/john/3");
    assert.equal(await text(page, "#passage-title"), "John 3");
    assert.equal(await text(page, "#passage-translation"), "Test Translation");
    assert.match(await text(page, "#v3-1"), /Testword fixture text for John three verse one\./);
    assert.match(await page.title(), /John 3 \(TST\)/);
    const books = await page.$$eval("#sel-book option", (os) => os.map((o) => o.textContent));
    assert.deepEqual(books, ["Genesis", "John"]);
    assert.equal(await text(page, "#attribution"), "Synthetic test fixture.");
    const prefs = await page.evaluate(() => JSON.parse(localStorage.getItem("qbible.prefs.v1")));
    assert.equal(prefs.translation, "test");

    const n = await routes(page);
    await page.goBack();
    await waitRoute(page, n);
    assert.equal(await page.$eval("#translation-select", (s) => s.value), "kjv");
    assert.match(await text(page, "#v3-16"), /For God so loved/);
    assert.equal((await page.$$("#sel-book option")).length, 66);
  });

  test("a passage missing from the chosen translation is reported, not substituted", async () => {
    await goto(page, server.url + "/bible/kjv/john/3/16");
    await pickTranslation("test");
    assert.equal(new URL(page.url()).pathname, "/bible/test/john/3/16");
    assert.equal(await page.$eval("#view-message", (e) => e.hidden), false);
    assert.match(await text(page, "#message-text"), /John 3 has 3 verses; there is no verse 16\. \(Test Translation\)/);
    const n = await routes(page);
    await page.click("#message-actions a");
    await waitRoute(page, n);
    assert.equal(new URL(page.url()).pathname, "/bible/kjv/john/3/16");
    assert.equal(await text(page, "#passage-title"), "John 3:16");

    await goto(page, server.url + "/bible/test/romans/8");
    assert.match(await text(page, "#message-text"), /Romans is not included in the Test Translation\./);
    assert.match(await text(page, "#message-actions"), /Open in KJV/);
  });

  test("unknown translation in a URL is reported", async () => {
    await goto(page, server.url + "/bible/zzz/john/3");
    assert.equal(await text(page, "#message-title"), "Translation not installed");
    assert.match(await text(page, "#message-actions"), /Open in KJV.*Open in TST/s);
  });

  test("search follows the chosen translation", async () => {
    await goto(page, server.url + "/bible/test/john/3");
    let n = await routes(page);
    await page.type("#go-input", "testword");
    await page.keyboard.press("Enter");
    await waitRoute(page, n);
    assert.equal(new URL(page.url()).searchParams.get("t"), "test");
    await page.waitForFunction(() => document.querySelectorAll("#search-results li").length === 7);
    const href = await page.$eval("#search-results li a", (a) => a.getAttribute("href"));
    assert.equal(href, "/bible/test/genesis/1/1");

    await pickTranslation("kjv");
    assert.equal(new URL(page.url()).searchParams.get("t"), null);
    await page.waitForFunction(() => /No verses match/.test(document.getElementById("search-status").textContent));
  });

  test("bookmarks remember their translation", async () => {
    await goto(page, server.url + "/bible/test/john/3/2");
    await page.click("#btn-bookmark-passage");
    await page.click('#bookmark-form button[type="submit"]');
    await page.waitForFunction(() => document.querySelectorAll("#bookmark-list li").length === 1);
    assert.equal(await text(page, "#bookmark-list li a"), "John 3:2");
    await goto(page, server.url + "/bible/kjv/genesis/1");
    assert.equal(await text(page, "#bookmark-list li a"), "John 3:2 (TST)");
    const n = await routes(page);
    await page.click("#bookmark-list li a");
    await waitRoute(page, n);
    assert.equal(new URL(page.url()).pathname, "/bible/test/john/3/2");
    assert.equal(await page.$eval("#translation-select", (s) => s.value), "test");
  });
});

describe("server stops when its browser pages are closed", { skip: !CHROME && "Chrome/Chromium not found" }, () => {
  // Short timings (visible 2 s, hidden 4 s, closing grace 1 s) keep the test quick.
  const env = { QBIBLE_WATCHDOG_TIMEOUTS: "2,4,1" };
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const exitWithin = (s, ms) => Promise.race([s.exited, sleep(ms).then(() => "timeout")]);
  let browser;
  before(async () => {
    browser = await puppeteer.launch({ executablePath: CHROME, headless: true, args: ["--no-sandbox"] });
  });
  after(async () => { if (browser) await browser.close(); });

  test("open pages, reloads and navigation keep it running; closing the last page stops it", async () => {
    const server = await startServer([], { env });
    try {
      const page1 = await browser.newPage();
      await goto(page1, server.url + "/bible/kjv/john/1");
      const page2 = await browser.newPage();
      await goto(page2, server.url + "/bible/kjv/psalms/23");
      await sleep(3000); // longer than the visible timeout: pings keep it alive
      assert.ok(server.running(), "running while pages are open");

      await page1.reload({ waitUntil: "domcontentloaded" }); // reload = closing + new page
      // page1 is a background tab now: requestAnimationFrame polling never fires there.
      await page1.waitForFunction(() => document.body.dataset.ready === "true", { polling: 100 });
      await page1.bringToFront(); // the user switches back to this tab
      await page1.click("#next-top"); // in-app navigation
      await page2.close();
      await sleep(2500);
      assert.ok(server.running(), "one page still open after a reload and another page closing");

      await page1.close(); // last page
      assert.equal(await exitWithin(server, 6000), 0, "server exits cleanly after the last page closes");
      assert.match(server.output(), /All qbible browser pages were closed; the server has stopped\./);
    } finally {
      stopServer(server);
    }
  });

  test("--keep-running ignores closed pages", async () => {
    const server = await startServer(["--keep-running"], { env });
    try {
      const page = await browser.newPage();
      await goto(page, server.url + "/bible/kjv/john/1");
      await page.close();
      assert.equal(await exitWithin(server, 4000), "timeout");
      assert.ok(server.running());
    } finally {
      stopServer(server);
    }
  });

  test("an open page shows a banner when the server stops, and recovers", async () => {
    const server = await startServer([], { env });
    let restarted = null;
    try {
      const page = await browser.newPage();
      await goto(page, server.url + "/bible/kjv/john/1");
      assert.equal(await page.$eval("#connection-banner", (e) => e.hidden), true);
      server.proc.kill("SIGTERM"); // stopped some other way (e.g. Ctrl+C)
      await server.exited;
      await page.waitForFunction(() => !document.getElementById("connection-banner").hidden, { timeout: 5000 });
      assert.match(await text(page, "#connection-banner"), /qbible server has stopped/);
      // Start it again on the same port: the page reconnects and hides the banner.
      const port = new URL(server.url).port;
      restarted = await startServer(["--port", port], { env });
      await page.waitForFunction(() => document.getElementById("connection-banner").hidden, { timeout: 5000 });
      await page.close();
    } finally {
      stopServer(server);
      stopServer(restarted);
    }
  });
});
