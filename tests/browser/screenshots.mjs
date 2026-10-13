// Development helper: capture screenshots of the browser UI for visual review.
//   node tests/browser/screenshots.mjs http://127.0.0.1:8737  [outdir]
import puppeteer from "puppeteer-core";
import { mkdirSync } from "node:fs";

const base = process.argv[2] || "http://127.0.0.1:8737";
const out = process.argv[3] || "build/screenshots";
mkdirSync(out, { recursive: true });
const browser = await puppeteer.launch({
  executablePath: process.env.CHROME_PATH || "/usr/bin/google-chrome", headless: true, args: ["--no-sandbox"],
});
const page = await browser.newPage();

async function shot(name, url, { width = 1366, height = 900, mobile = false, dark = false, prep } = {}) {
  await page.setViewport({ width, height, isMobile: mobile, hasTouch: mobile, deviceScaleFactor: 1 });
  await page.emulateMediaFeatures([{ name: "prefers-color-scheme", value: dark ? "dark" : "light" }]);
  await page.goto(base + url, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.body.dataset.ready === "true");
  if (prep) await prep(page);
  await new Promise((r) => setTimeout(r, 300));
  await page.screenshot({ path: `${out}/${name}.png` });
  console.log(`${out}/${name}.png`);
}

await shot("desktop-light-john3", "/bible/kjv/john/3");
await shot("desktop-dark-psalm23", "/bible/kjv/psalms/23", {
  dark: true,
  prep: async (p) => { await p.click("#v23-1 .vnum"); },
});
await shot("desktop-search", "/search?q=%22fear%20not%22", {
  prep: (p) => p.waitForFunction(() => document.querySelectorAll("#search-results li").length > 0),
});
await shot("desktop-settings", "/bible/kjv/romans/8", { prep: (p) => p.click("#btn-settings") });
await shot("mobile-light-genesis1", "/bible/kjv/genesis/1", { width: 390, height: 844, mobile: true });
await shot("mobile-dark-verses", "/bible/kjv/john/1", {
  width: 390, height: 844, mobile: true, dark: true,
  prep: async (p) => {
    await p.click("#btn-settings");
    await p.select("#layout", "verses");
    await p.click("#settings-close");
  },
});
await browser.close();
