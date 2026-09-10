const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const http = require('node:http'), fs = require('node:fs'), path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../dist');
const server = http.createServer((req, res) => {
  const name = new URL(req.url, 'http://localhost').pathname.replace(/^\/ui\//, '/');
  const file = path.resolve(root, name === '/' ? 'index.html' : '.' + name);
  if (!file.startsWith(root + path.sep)) { res.writeHead(403); return res.end(); }
  res.setHeader('Content-Type', file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : 'text/html');
  try { res.end(fs.readFileSync(file)); } catch { res.writeHead(404); res.end(); }
});
(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', error => { errors.push(error.message); console.error('PAGE_ERROR', error.message); });
    await page.route('**/v1/**', route => {
      const url = new URL(route.request().url());
      let body = { status: 'ready' };
      if (url.pathname === '/v1/config') body = { kit_stream: {
        signaling_host: 'localhost', signaling_port: 49100, signaling_secure: false,
        signaling_path: '/kit-stream', media_port: 15865, media_host: 'example.test', configuration_warnings: []
      }, capabilities: {} };
      if (url.pathname === '/v1/workflows') body = [{ workflow_id: 'test-run', active_model: 'output.brep', events: [], status: 'complete' }];
      if (url.pathname === '/v1/stream/healthz') body = {
        status: 'offline', probe_host: '127.0.0.1', signaling_port: 49100,
        latency_ms: 0, detail: 'Kit server is stopped', boundary: 'kit_listener'
      };
      return route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
    });
    await page.route('**/ovrtx/**', route => route.fulfill({ contentType: 'text/html', body: '<p>OVRTX fixture</p>' }));
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    await page.locator('iframe').waitFor();
    const selector = page.getByLabel('Review renderer', { exact: true });
    page.once('dialog', dialog => dialog.dismiss());
    await selector.selectOption('kit');
    assert.equal(await selector.inputValue(), 'ovrtx');
    page.once('dialog', dialog => dialog.accept());
    await selector.selectOption('kit');
    await page.locator('#kit-remote-video').waitFor({ state: 'attached' });
    assert.equal(await page.locator('iframe').count(), 0);
    await page.getByRole('button', { name: 'Connect stream', exact: true }).click();
    await page.getByText('Kit is not listening', { exact: false }).waitFor();
    page.once('dialog', dialog => dialog.accept());
    await selector.selectOption('ovrtx');
    await page.locator('iframe').waitFor();
    assert.equal(await page.locator('#kit-remote-video').count(), 0);
    assert.deepEqual(errors, []);
    console.log('PASS: default OVRTX, cancelled switch, exclusive Kit mount, offline guard, return to OVRTX');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; }).finally(() => server.close());
