import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { chromium, devices } from 'playwright';

const css = await readFile(new URL('../src/components/miniapp/MiniAppBottomNav.css', import.meta.url), 'utf8');
const browser = await chromium.launch({ executablePath: process.env.VELA_TEST_CHROMIUM });
try {
  for (const device of ['iPhone 14', 'iPhone 15', 'Pixel 7']) {
    const { defaultBrowserType: _, ...profile } = devices[device];
    for (const landscape of [false, true]) {
      const { width, height } = profile.viewport;
      const context = await browser.newContext({
        ...profile,
        viewport: landscape ? { width: height, height: width } : profile.viewport,
      });
      try {
        const page = await context.newPage();
        await page.setContent(`
          <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
          <style>${css}</style>
          <main id="content-layout">Panel</main>
          <nav class="tg-app-bottom-nav">
            ${['首页', '服务器', '客户端', '证书', '更多'].map((name) =>
              `<button type="button" class="tg-bottom-item">${name}</button>`).join('')}
          </nav>
        `);
        const nav = page.getByRole('navigation');
        assert.equal(await nav.isVisible(), true, `${device} navigation must be visible`);
        const box = await nav.boundingBox();
        assert.ok(box && box.height <= (landscape ? 55 : 75));
        for (const button of await nav.getByRole('button').all()) {
          const target = await button.boundingBox();
          assert.ok(target && target.width >= 44 && target.height >= 44, `${device} touch target is too small`);
        }
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
        await nav.evaluate((element) => element.setAttribute('data-keyboard-open', 'true'));
        assert.equal(await nav.isVisible(), false);
        console.info(`${device} ${landscape ? 'landscape' : 'portrait'} passed`);
      } finally {
        await context.close();
      }
    }
  }
} finally {
  await browser.close();
}
