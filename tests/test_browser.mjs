// Frontier UI browser tests: rendering, external links under Open WebUI's sandbox, units, GPX download.
// Runs in the official Playwright image (Chromium, Firefox, WebKit), no install needed:
//   docker run --rm --network host -v "$PWD:/w" -w /w mcr.microsoft.com/playwright:v1.56.0-noble \
//     sh -c "npm i --no-save playwright@1.56.0 >/dev/null && node tests/test_browser.mjs card.html"
// card.html = the HTMLResponse body of a render_frontier_ui call with a map + weather block (see tests/README.md).
import http from 'node:http';
import fs from 'node:fs';
import { chromium, firefox, webkit } from 'playwright';

const card = fs.readFileSync(process.argv[2] || 'card.html', 'utf8');
const esc = s => s.replace(/&/g, '&amp;').replace(/"/g, '&quot;');
// Mirrors Open WebUI 0.12.x: srcdoc iframe; allow-same-origin only when the admin enables it.
const parent = so => `<!doctype html><html><body style="margin:0;background:#111">
<iframe id="f" style="width:900px;height:2600px;border:0" sandbox="allow-scripts allow-forms allow-popups allow-downloads${so ? ' allow-same-origin' : ''}"
 srcdoc="${esc(card)}"></iframe></body></html>`;
const A = http.createServer((q, r) => { r.setHeader('content-type', 'text/html; charset=utf-8'); r.end(parent(q.url.includes('so=1'))); }).listen(8711);
// stand-in for Google/Apple/OSM pages: all send Cross-Origin-Opener-Policy (checked with curl -I)
const B = http.createServer((q, r) => { r.setHeader('content-type', 'text/html'); r.setHeader('Cross-Origin-Opener-Policy', 'same-origin');
  r.end('<title>maps</title><h1 id=ok>maps page</h1>'); }).listen(8712);
const COOP = 'http://localhost:8712/maps?q=1';

let fails = 0;
const ok = (c, msg) => { console.log((c ? 'PASS ' : 'FAIL ') + msg); if (!c) fails++; };

for (const [name, type] of [['chromium', chromium], ['firefox', firefox], ['webkit', webkit]]) {
  const browser = await type.launch();
  for (const locale of ['en-US', 'sl-SI']) {
    const ctx = await browser.newContext({ locale, acceptDownloads: true, viewport: { width: 1000, height: 2700 } });
    const page = await ctx.newPage();
    const errors = [];
    page.on('pageerror', e => errors.push(String(e)));
    page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
    await page.goto('http://127.0.0.1:8711/');
    const f = page.frameLocator('#f');
    const blocks = await f.locator('.blk').count().catch(() => 0);
    await page.waitForTimeout(2500);
    const n = await f.locator('.blk').count();
    ok(n >= 5, `${name} ${locale}: card renders (${n} blocks)${errors.length ? ' errors: ' + errors.slice(0, 3).join(' | ') : ''}`);
    if (locale === 'en-US') ok(errors.filter(e => !/tile|Failed to load resource|net::|NetworkError|CORS/i.test(e)).length === 0, `${name}: no script errors`);
    const temp = await f.locator('.wx .big').first().textContent().catch(() => '');
    ok(locale === 'en-US' ? /°F/.test(temp) : /°C/.test(temp), `${name} ${locale}: weather units ${temp}`);
    // every map is either an interactive canvas or (no WebGL, e.g. headless Firefox) a static sketch with its route line
    const maps = await f.locator('.mapbox').evaluateAll(bs => bs.map(b => b.querySelector('.maplibregl-canvas') ? 'gl' : b.querySelector('.msketch polyline') ? 'sketch' : 'broken'));
    ok(maps.length === 2 && !maps.includes('broken'), `${name} ${locale}: maps drawn (${maps.join(', ')})`);
    if (locale === 'en-US') { const st = await f.locator('.mstat').first().textContent().catch(() => ''); ok(/mi\b/.test(st), `${name}: distances in miles for en-US (${st})`); }
    else { const st = await f.locator('.mstat').first().textContent().catch(() => ''); ok(/km\b/.test(st), `${name}: distances in km for ${locale} (${st})`); }
    if (locale === 'en-US') {
      // 1) default sandbox (no allow-same-origin): the link sheet must appear instead of a blocked tab
      const popups = [];
      ctx.on('page', p => popups.push(p));
      await f.locator('.mgrp .mbtn').first().click();
      await page.waitForTimeout(800);
      const sheet = await f.locator('.lsheet .lsi').inputValue().catch(() => '');
      ok(/google\.com\/maps/.test(sheet) && popups.length === 0, `${name}: sandboxed card shows copy-link sheet (${sheet.slice(0, 50)})`);
      // 2) map app menu + GPX download
      await f.locator('.lsheet .btn').last().click().catch(() => {});
      await f.locator('.mgrp .mbtn.ic').first().click();
      const dl = page.waitForEvent('download', { timeout: 5000 }).catch(() => null);
      await f.locator('.mmenu.on button', { hasText: 'GPX' }).click();
      const d = await dl;
      if (d) { const p = await d.path(); const x = fs.readFileSync(p, 'utf8'); ok(/<gpx[\s\S]*<rtept/.test(x), `${name}: GPX download (${d.suggestedFilename()})`); }
      else ok(name === 'webkit', `${name}: GPX download event${name === 'webkit' ? ' (WebKit headless has no download event for blob links; skipped)' : ''}`);
      // 3) what users hit before: a popup straight from the sandboxed frame to a COOP page
      const frame = page.frames().find(x => x !== page.mainFrame());
      const pp = ctx.waitForEvent('page', { timeout: 4000 }).catch(() => null);
      await frame.evaluate(u => { window.open(u, '_blank', 'noopener'); }, COOP).catch(() => {});
      const pop = await pp;
      if (pop) { await pop.waitForLoadState().catch(() => {}); const t = await pop.locator('#ok').count().catch(() => 0);
        console.log(`INFO ${name}: popup from sandboxed frame to COOP page -> ${t ? 'loaded' : 'blocked (' + pop.url().slice(0, 40) + ')'}`); await pop.close(); }
      else console.log(`INFO ${name}: popup from sandboxed frame was not opened`);
    }
    await ctx.close();
  }
  // 4) admin enabled "iframe Sandbox Allow Same Origin": links open a real tab via the parent window
  const ctx = await browser.newContext({ locale: 'en-US', viewport: { width: 1000, height: 2700 } });
  const page = await ctx.newPage();
  await page.goto('http://127.0.0.1:8711/?so=1');
  await page.waitForTimeout(2500);
  const f = page.frameLocator('#f');
  const pp = ctx.waitForEvent('page', { timeout: 5000 }).catch(() => null);
  await f.locator('.mgrp .mbtn').first().click();
  const pop = await pp;
  ok(!!pop && /google\.com\/maps/.test(pop.url() || (await pop.waitForURL(/./).then(() => pop.url()).catch(() => ''))), `${name}: same-origin mode opens the link in a new tab via parent`);
  // parent-opened popups are not sandboxed, so a COOP page loads
  const pp2 = ctx.waitForEvent('page', { timeout: 5000 }).catch(() => null);
  await page.frames()[1].evaluate(u => parent.window.open(u, '_blank', 'noopener'), COOP).catch(() => {});
  const p2 = await pp2; if (p2) { await p2.waitForLoadState().catch(() => {}); }
  ok(p2 && (await p2.locator('#ok').count().catch(() => 0)) === 1, `${name}: COOP page loads when opened by the parent window`);
  await ctx.close();
  await browser.close();
}
// 5) hostile-but-common setups: WebGL off / resistFingerprinting (Firefox privacy), blocked CDN and tile hosts (uBlock, NoScript).
// The map may degrade, but every other block must still render.
for (const [label, opts, block] of [
  ['firefox webgl.disabled + resistFingerprinting', { firefoxUserPrefs: { 'webgl.disabled': true, 'privacy.resistFingerprinting': true } }, null],
  ['firefox with CDN + tiles blocked', {}, /jsdelivr|unpkg|openfreemap|18262/],
  ['chromium with CDN + tiles blocked', null, /jsdelivr|unpkg|openfreemap|18262/]]) {
  const browser = await (opts ? firefox : chromium).launch(opts || {});
  const ctx = await browser.newContext({ locale: 'de-DE', viewport: { width: 1000, height: 2700 } });
  if (block) await ctx.route(block, r => r.abort());
  const page = await ctx.newPage(); const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  await page.goto('http://127.0.0.1:8711/'); await page.waitForTimeout(4000);
  const f = page.frameLocator('#f');
  const n = await f.locator('.blk').count(); const wx = await f.locator('.wx .big').first().textContent().catch(() => '');
  const pins = await f.locator('.mapbox').count();
  ok(n >= 5 && /°C/.test(wx), `${label}: other blocks still render (${n} blocks, map boxes ${pins}, ${wx})${errors.length ? ' errors: ' + errors.slice(0, 2).join(' | ') : ''}`);
  await browser.close();
}
A.close(); B.close();
console.log(fails ? `\n${fails} failed` : '\nall browser checks passed');
process.exit(fails ? 1 : 0);
