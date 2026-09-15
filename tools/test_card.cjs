// Run against an unmodified Flex Table Card downloaded into .qa.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

(async () => {
  const root = path.resolve(__dirname, '..');
  const config = JSON.parse(fs.readFileSync(path.join(root, '.qa/card.json'), 'utf8'));
  const browser = await chromium.launch({
    headless: true, executablePath: process.env.BROWSER_PATH || undefined
  });
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.setContent('<html><head><style>body{margin:0;background:#080e19;font-family:Arial,sans-serif}main{padding:12px;box-sizing:border-box}</style></head><body><main></main></body></html>');
    await page.evaluate(() => {
      customElements.define('ha-card', class extends HTMLElement {
        set header(text) {
          const h = document.createElement('div');
          h.className = 'card-header'; h.textContent = text; this.prepend(h);
        }
        connectedCallback() { this.style.display = 'block'; }
      });
      customElements.define('ha-icon', class extends HTMLElement {
        connectedCallback() { this.textContent = '↗'; }
      });
    });
    await page.addScriptTag({ path: path.join(root, '.qa/flex-table-card.js') });
    await page.evaluate(config => {
      const card = document.createElement('flex-table-card');
      card.setConfig(config);
      document.querySelector('main').append(card);
      window.demoRows = [
        {line:'R9',destination:'Central Hauptbahnhof',destination_short:'Central Hbf',platform:'2',
         stop_group:'North Station',departure_time:'2026-09-14T12:07:00+02:00',delay:2,countdown_minutes:7,icon:'mdi:train'},
        {line:'600',destination:'Town Centre',destination_short:'Town Centre',platform:'A',
         stop_group:'North Station',departure_time:'2026-09-14T12:12:00+02:00',delay:0,countdown_minutes:12,icon:'mdi:bus'},
        {line:'R8',destination:'Airport',destination_short:'Airport',platform:'1',
         stop_group:'South Station',departure_time:'2026-09-14T12:17:00+02:00',delay:8,countdown_minutes:17,icon:'mdi:train'},
        {line:'<img src=x onerror=alert(1)>',destination:'<script>alert(1)</script>',platform:'<b>1</b>',
         stop_group:'Test',departure_time:'2026-09-14T12:20:00+02:00',delay:null,countdown_minutes:20}
      ];
      let revision = 0;
      window.updateBoard = rows => {
        card.hass = {states:{'sensor.public_transport_dashboard':{
          entity_id:'sensor.public_transport_dashboard',state:String(rows.length),
          last_updated: new Date(1789380000000 + ++revision * 1000).toISOString(),
          attributes:{departures:rows}}},locale:{language:'de'},config:{language:'de'}};
      };
      window.updateBoard(window.demoRows);
    }, config);
    for (const width of [320, 360, 768, 1200]) {
      await page.setViewportSize({ width, height: 600 });
      await page.waitForFunction(() => document.querySelector('flex-table-card')
        .shadowRoot.querySelectorAll('tbody tr').length === 4);
      const measurements = await page.evaluate(() => {
        const root = document.querySelector('flex-table-card').shadowRoot;
        const table = root.querySelector('table');
        return {
          rows:root.querySelectorAll('tbody tr').length,
          injected:root.querySelectorAll('tbody img, tbody script, tbody b').length,
          overflow:document.documentElement.scrollWidth > window.innerWidth,
          tableWidth:table.getBoundingClientRect().width,
          right:getComputedStyle(root.querySelector('tbody tr td:last-child')).textAlign,
          foreground:getComputedStyle(root.querySelector('.destination')).color,
          unknown:root.querySelector('.unknown')?.textContent
        };
      });
      assert.equal(measurements.rows, 4);
      assert.equal(measurements.injected, 0);
      assert.equal(measurements.overflow, false);
      assert.equal(measurements.right, 'right');
      assert.equal(measurements.foreground, 'rgb(229, 237, 249)');
      assert.equal(measurements.unknown, 'k. A.');
      assert.ok(measurements.tableWidth <= width);
      console.log(width + 'px: layout, escaping and alignment OK');
      if (width === 360 || width === 768) {
        await page.evaluate(() => window.updateBoard(window.demoRows.slice(0, 3)));
        await page.waitForFunction(() => document.querySelector('flex-table-card')
          .shadowRoot.querySelectorAll('tbody tr').length === 3);
        await page.screenshot({path:path.join(root,'.qa/board-' + width + '.png')});
        await page.evaluate(() => window.updateBoard(window.demoRows));
      }
    }
    await page.evaluate(() => window.updateBoard([]));
    await page.waitForFunction(() => document.querySelector('flex-table-card')
      .shadowRoot.querySelectorAll('tbody tr').length === 0);
    assert.equal(await page.locator('flex-table-card').evaluate(card =>
      card.shadowRoot.querySelectorAll('tbody tr').length), 0);
    assert.deepEqual(errors, []);
    console.log('Empty state and browser error checks OK');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
