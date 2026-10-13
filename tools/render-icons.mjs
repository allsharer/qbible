// Render packaging/icons/qbible.svg to the PNG sizes used by the freedesktop
// "hicolor" icon theme, using the locally installed Chrome (no image tools needed).
//   node tools/render-icons.mjs
import puppeteer from "puppeteer-core";
import { readFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const svg = readFileSync(join(ROOT, "packaging/icons/qbible.svg"), "utf8");
const SIZES = [16, 24, 32, 48, 64, 128, 256, 512];

const browser = await puppeteer.launch({
  executablePath: process.env.CHROME_PATH || "/usr/bin/google-chrome", headless: true, args: ["--no-sandbox"],
});
const page = await browser.newPage();
for (const size of SIZES) {
  await page.setViewport({ width: size, height: size, deviceScaleFactor: 1 });
  await page.setContent(
    `<html><body style="margin:0;background:transparent">${svg.replace("<svg ", `<svg style="display:block;width:${size}px;height:${size}px" `)}</body></html>`,
  );
  const out = join(ROOT, `packaging/icons/hicolor/${size}x${size}/apps/qbible.png`);
  mkdirSync(dirname(out), { recursive: true });
  await page.screenshot({ path: out, omitBackground: true, clip: { x: 0, y: 0, width: size, height: size } });
  console.log(out);
}
await browser.close();
