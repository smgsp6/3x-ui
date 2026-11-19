import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
import { join } from 'node:path';
import { chromium, devices } from 'playwright';
import { createServer, preview } from 'vite';

const serverOptions = { host: '127.0.0.1', port: 0 };
const dev = process.env.VELA_TEST_DEV === '1';
const server = dev
  ? await createServer({ server: serverOptions })
  : await preview({ preview: serverOptions });
if (dev) await server.listen();
const address = server.httpServer.address();
assert.ok(address && typeof address === 'object');
const origin = `http://127.0.0.1:${address.port}`;
const screenshots = process.env.VELA_TEST_SCREENSHOTS;
let browser;

async function checkVisibleTarget(target, page) {
  await target.scrollIntoViewIfNeeded();
  const box = await target.boundingBox();
  const viewport = page.viewportSize();
  assert.ok(box && box.x >= -1 && box.y >= -1 &&
    box.x + box.width <= viewport.width + 1 && box.y + box.height <= viewport.height + 1,
  'target must be within the viewport after scrolling');
  await target.click({ trial: true });
}

async function configurePage(page) {
  await page.addInitScript(() => {
    window.X_UI_BASE_PATH = '/';
    window.X_UI_TG_MINIAPP_MODE = true;
    let back;
    window.Telegram = { WebApp: {
      initData: 'synthetic-ui-test',
      BackButton: {
        show() {}, hide() {},
        onClick(callback) { back = callback; },
        offClick(callback) { if (back === callback) back = undefined; },
      },
    } };
    window.velaTestBack = () => back?.();
  });
  const state = { failProbe: true, probes: 0, saves: 0, failAuth: true, auth: 0, failLogout: true, logout: 0, sessionRevoked: false, statusChecks: 0 };
  await page.routeWebSocket('**/*', (socket) => socket.close());
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== origin) return route.abort();
    const path = url.pathname;
    if (route.request().isNavigationRequest()) {
      const document = await route.fetch({ url: origin + (path.startsWith('/panel') ? '/index.html' : '/miniapp.html') });
      const body = (await document.text()).replace(
        'content="width=device-width, initial-scale=1.0"',
        'content="width=device-width, initial-scale=1.0, viewport-fit=cover"',
      );
      return route.fulfill({ response: document, body });
    }
    const success = (obj) => route.fulfill({ json: { success: true, msg: '', obj } });
    if (path === '/csrf-token') return success('synthetic-csrf');
    if (path === '/logout') {
      state.logout++;
      if (state.failLogout) return route.abort('internetdisconnected');
      return success(null);
    }
    if (path === '/panel/api/tg-miniapp/status') {
      state.statusChecks++;
      if (state.sessionRevoked) return route.fulfill({ status: 401 });
      return success({ botRunning: true, launchConfigured: true, authConfigured: true });
    }
    if (path === '/tg-miniapp/auth') {
      state.auth++;
      if (state.failAuth) return route.abort('internetdisconnected');
      return success(null);
    }
    if (path === '/panel/api/nodes/test') {
      state.probes++;
      if (state.failProbe) return route.abort('internetdisconnected');
      return success({ status: 'online' });
    }
    if (path === '/panel/api/nodes/add') {
      state.saves++;
      return success(null);
    }
    if (path.startsWith('/panel/api/')) {
      return success(path.endsWith('/certificates/status') ? { certificates: [], alertsEnabled: false } : []);
    }
    return route.continue();
  });
  return state;
}

try {
  browser = await chromium.launch({ executablePath: process.env.VELA_TEST_CHROMIUM });
  if (screenshots) await mkdir(screenshots, { recursive: true, mode: 0o700 });
  for (const device of ['iPhone 14', 'iPhone 15', 'Pixel 7']) {
    const { defaultBrowserType: _, ...profile } = devices[device];
    for (const landscape of [false, true]) {
      const { width, height } = profile.viewport;
      const context = await browser.newContext({
        ...profile, locale: 'en-US', serviceWorkers: 'block',
        viewport: landscape ? { width: height, height: width } : profile.viewport,
      });
      try {
        const page = await context.newPage();
        page.setDefaultTimeout(15_000);
        const state = await configurePage(page);
        await page.goto(`${origin}/panel/nodes`);
        const nav = page.getByRole('navigation', { name: 'Vela 小程序主导航' });
        const add = page.getByRole('button', { name: 'Add Node', exact: true });
        await checkVisibleTarget(add, page);
        const box = await nav.boundingBox();
        assert.ok(box && box.height <= (landscape ? 55 : 75));
        for (const button of await nav.getByRole('button').all()) {
          const target = await button.boundingBox();
          assert.ok(target && target.width >= 44 && target.height >= 44, `${device} touch target is too small`);
        }
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
        await add.click();
        const editor = page.getByRole('dialog', { name: 'Add Node' });
        const name = editor.getByRole('textbox', { name: 'Name', exact: true });
        await checkVisibleTarget(name, page);
        await name.fill('Synthetic review node');
        const label = `${device.replaceAll(' ', '-')}-${landscape ? 'landscape' : 'portrait'}`;
        if (screenshots) await page.screenshot({ animations: 'disabled', path: join(screenshots, `${label}-editor-top.png`) });

        if (device === 'iPhone 15' && landscape) {
          // Preserve the real DOM and emulate the smaller viewport reported by a soft keyboard.
          await name.focus();
          await page.evaluate(() => {
            const viewport = window.visualViewport;
            Object.defineProperty(viewport, 'height', { configurable: true, value: innerHeight - 220 });
            viewport.dispatchEvent(new Event('resize'));
          });
          await nav.waitFor({ state: 'hidden' });
          assert.ok(await editor.evaluate((dialog) =>
            Number.parseFloat(getComputedStyle(dialog.closest('.ant-modal-wrap')).bottom) > 0,
          ), 'keyboard must constrain the editor scroll area');
          if (screenshots) await page.screenshot({
            animations: 'disabled',
            path: join(screenshots, `${label}-keyboard-viewport.png`),
          });
          await page.evaluate(() => window.velaTestBack());
          await nav.waitFor();
          assert.equal(await name.evaluate((input) => input === document.activeElement), false);
          assert.equal(await name.inputValue(), 'Synthetic review node');
          await page.evaluate(() => Reflect.deleteProperty(window.visualViewport, 'height'));
        }

        const save = editor.getByRole('button', { name: /Save/i });
        await checkVisibleTarget(save, page);
        if (screenshots) await page.screenshot({ animations: 'disabled', path: join(screenshots, `${label}-editor-actions.png`) });
        await page.evaluate(() => window.velaTestBack());
        const confirmation = page.getByRole('dialog', { name: '关闭编辑？' });
        await confirmation.waitFor();
        await page.evaluate(() => window.velaTestBack());
        await confirmation.waitFor({ state: 'hidden' });
        assert.equal(await name.inputValue(), 'Synthetic review node');

        if (device === 'iPhone 15' && !landscape) {
          await editor.getByRole('textbox', { name: 'Address', exact: true }).fill('synthetic.example.test');
          await editor.getByLabel(/API Token/i).fill('synthetic-browser-test-token');
          await save.click();
          await editor.getByText('Connection failed', { exact: true }).waitFor();
          assert.equal(state.probes, 1);
          assert.equal(state.saves, 0);
          state.failProbe = false;
          await save.evaluate((button) => { button.click(); button.click(); });
          await editor.waitFor({ state: 'hidden' });
          assert.equal(state.probes, 2);
          assert.equal(state.saves, 1);
          await nav.getByRole('button', { name: '更多' }).click();
          const logout = page.getByRole('button', { name: /Log out|Logout/i });
          const stillAuthorized = page.waitForResponse((response) =>
            response.url().endsWith('/panel/api/tg-miniapp/status') && response.status() === 200,
          );
          await logout.click();
          await stillAuthorized;
          assert.equal(state.logout, 1);
          assert.ok(page.url().endsWith('/panel/nodes'));
          state.failLogout = false;
          await logout.click();
          await page.getByText(/会话已结束/).waitFor();
          assert.equal(state.logout, 2);
          assert.equal(state.auth, 0);
          await page.goto(origin);
          const retry = page.getByRole('button', { name: '重试' });
          await retry.waitFor();
          state.failAuth = false;
          await retry.click();
          await page.waitForURL('**/panel/');
          assert.equal(state.auth, 2);

          state.failLogout = true;
          state.sessionRevoked = true;
          await nav.getByRole('button', { name: '更多' }).click();
          await logout.click();
          await page.getByText(/会话已结束/).waitFor();
          assert.equal(state.logout, 3);
          assert.equal(state.statusChecks, 2);
          assert.equal(state.auth, 2);
        }
        console.info(`${device} ${landscape ? 'landscape' : 'portrait'} passed`);
      } finally {
        await context.close();
      }
    }
  }
} finally {
  await browser?.close();
  await server.close();
}
