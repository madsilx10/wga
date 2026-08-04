// ============================================================================
// TEMPLATE UTAMA PLAYWRIGHT NODE.JS UNTUK TERMUX (GLOBAL + STEALTH)
// ============================================================================

// 1. Trik manipulasi platform agar lolos pengecekan di Android
Object.defineProperty(process, 'platform', { get: () => 'linux' });

const { chromium } = require('playwright-extra');
const stealthPlugin = require('puppeteer-extra-plugin-stealth')();
chromium.use(stealthPlugin);

(async () => {
  console.log("Memulai browser Chromium Termux...");
  
  // 2. Konfigurasi wajib biner Chromium lokal Termux
  const browser = await chromium.launch({
    executablePath: '/data/data/com.termux/files/usr/bin/chromium-browser',
    headless: true, // Wajib true di Termux standar
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',
      '--disable-gpu',
      '--single-process'
    ]
  });

  const context = await browser.newContext({
    userAgent: 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36'
  });
  const page = await context.newPage();

  try {
    // ----------------------------------------------------
    // [KODE SCRAPING / BOT SAYA AKAN DIMASUKKAN DI SINI]
    await page.goto('https://wga.xyz/reward', { waitUntil: 'networkidle' });
    console.log(`Berhasil masuk ke: ${await page.title()}`);

    await page.waitForTimeout(2000);

    // Klik tombol Connect Wallet
    await page.getByText('Connect Wallet', { exact: true }).click();
    await page.waitForTimeout(2000);

    // Cek apakah ada elemen/iframe terkait turnstile di DOM
    const info = await page.evaluate(() => {
      const inputEl = document.querySelector('input[name="cf-turnstile-response"]');
      const turnstileDivs = Array.from(document.querySelectorAll('[class*="turnstile"], [id*="turnstile"], div.cf-turnstile'))
        .map(el => ({ tag: el.tagName, cls: el.className, id: el.id }));
      const iframes = Array.from(document.querySelectorAll('iframe'))
        .map(f => f.src);
      const scripts = Array.from(document.querySelectorAll('script'))
        .map(s => s.src).filter(s => s.includes('turnstile') || s.includes('challenges.cloudflare'));
      const buttons = Array.from(document.querySelectorAll('button, [role="button"], a, li, div[class*="wallet"]'))
        .map(el => ({ tag: el.tagName, text: el.innerText.trim().slice(0, 40), cls: el.className }))
        .filter(b => b.text);
      return {
        hasInput: !!inputEl,
        inputValue: inputEl ? inputEl.value : null,
        turnstileDivs,
        iframes,
        turnstileScripts: scripts,
        buttons,
        bodySnippet: document.body.innerHTML.slice(0, 3000)
      };
    });

    console.log('RESULT_JSON:' + JSON.stringify(info, null, 2));

    await page.screenshot({ path: 'debug_screenshot.png', fullPage: true });
    console.log('Screenshot disimpan ke debug_screenshot.png');
    // ----------------------------------------------------
  } catch (error) {
    console.error("Terjadi eror:", error.message);
  } finally {
    await browser.close();
    console.log("Browser ditutup.");
  }
})();
