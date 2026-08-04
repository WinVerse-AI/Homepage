#!/usr/bin/env node
const fs = require('fs');
const { chromium } = require('/tmp/serotonix-playwright/node_modules/playwright-core');

const [pageUrl, desktopPath, mobilePath, reportPath] = process.argv.slice(2);
if (!pageUrl || !desktopPath || !mobilePath || !reportPath) {
  console.error('Usage: capture-serotonix.js PAGE_URL DESKTOP_PATH MOBILE_PATH REPORT_PATH');
  process.exit(2);
}
const candidates = ['/usr/bin/google-chrome', '/usr/bin/google-chrome-stable', '/usr/bin/chromium', '/usr/bin/chromium-browser'];
const executablePath = candidates.find(fs.existsSync);
if (!executablePath) {
  throw new Error(`No Chrome/Chromium executable found; checked ${candidates.join(', ')}`);
}

(async () => {
  const browser = await chromium.launch({ executablePath, headless: true, args: ['--no-sandbox'] });
  const report = { pageUrl, executablePath, generatedAt: new Date().toISOString(), viewports: {}, passed: true, failures: [] };
  for (const config of [
    { name: 'desktop', width: 1440, height: 1000, path: desktopPath },
    { name: 'mobile', width: 390, height: 844, path: mobilePath },
  ]) {
    const page = await browser.newPage({ viewport: { width: config.width, height: config.height }, deviceScaleFactor: 1 });
    const consoleErrors = [];
    const requestFailures = [];
    page.on('console', msg => { if (msg.type() === 'error') consoleErrors.push(msg.text()); });
    page.on('requestfailed', request => requestFailures.push({ url: request.url(), error: request.failure()?.errorText || 'unknown' }));
    const response = await page.goto(pageUrl, { waitUntil: 'networkidle', timeout: 120000 });
    if (!response || response.status() !== 200) report.failures.push(`${config.name}: page HTTP ${response ? response.status() : 'no response'}`);
    const images = page.locator('img[src*="serotonix-"]');
    for (let i = 0; i < await images.count(); i++) {
      await images.nth(i).scrollIntoViewIfNeeded();
      await page.waitForTimeout(150);
    }
    await page.waitForTimeout(1000);
    const imageState = await images.evaluateAll(nodes => nodes.map(img => ({
      src: img.currentSrc || img.src,
      complete: img.complete,
      naturalWidth: img.naturalWidth,
      naturalHeight: img.naturalHeight,
      renderedWidth: Math.round(img.getBoundingClientRect().width * 10) / 10,
      renderedHeight: Math.round(img.getBoundingClientRect().height * 10) / 10,
      alt: img.alt,
    })));
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
    const navigation = { headerPresent: await page.locator('[data-header]').count() === 1, languageControlPresent: await page.locator('[data-language-select]').count() === 1 };
    if (!navigation.headerPresent) report.failures.push(`${config.name}: site header did not initialise`);
    if (!navigation.languageControlPresent) report.failures.push(`${config.name}: language selector did not initialise`);
    if (navigation.languageControlPresent) {
      await page.locator('[data-language-select]').selectOption('zh');
      navigation.chineseLang = await page.locator('html').getAttribute('lang');
      navigation.chineseTitle = await page.locator('#page-title').textContent();
      if (navigation.chineseLang !== 'zh-CN') report.failures.push(`${config.name}: Chinese language switch failed`);
      await page.locator('[data-language-select]').selectOption('en');
      navigation.englishLang = await page.locator('html').getAttribute('lang');
      if (navigation.englishLang !== 'en') report.failures.push(`${config.name}: English language restore failed`);
    }
    if (config.name === 'mobile') {
      const menu = page.locator('[data-menu-toggle]');
      navigation.menuPresent = await menu.count() === 1;
      if (navigation.menuPresent) {
        await menu.click();
        navigation.menuExpanded = await menu.getAttribute('aria-expanded');
        if (navigation.menuExpanded !== 'true') report.failures.push('mobile: navigation menu did not open');
        await page.keyboard.press('Escape');
      } else report.failures.push('mobile: navigation menu toggle missing');
    }
    if (imageState.length !== 8) report.failures.push(`${config.name}: expected 8 SerotoniX images, found ${imageState.length}`);
    for (const image of imageState) {
      if (!image.complete || image.naturalWidth === 0 || image.naturalHeight === 0) report.failures.push(`${config.name}: image failed ${image.src}`);
    }
    if (overflow) report.failures.push(`${config.name}: horizontal overflow detected`);
    if (consoleErrors.length) report.failures.push(`${config.name}: console errors: ${consoleErrors.join(' | ')}`);
    if (requestFailures.length) report.failures.push(`${config.name}: request failures: ${JSON.stringify(requestFailures)}`);
    await page.screenshot({ path: config.path, fullPage: true });
    report.viewports[config.name] = { width: config.width, height: config.height, overflow, consoleErrors, requestFailures, navigation, images: imageState, screenshot: config.path };
    await page.close();
  }
  report.passed = report.failures.length === 0;
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2) + '\n');
  await browser.close();
  if (!report.passed) {
    console.error(report.failures.join('\n'));
    process.exit(1);
  }
  console.log(`Captured and verified desktop/mobile screenshots for ${pageUrl}`);
})().catch(error => { console.error(error); process.exit(1); });
