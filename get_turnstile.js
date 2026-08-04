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
    const startTime = Date.now();

    await page.goto('https://wga.xyz/reward', { waitUntil: 'networkidle' });
    console.log(`Berhasil masuk ke: ${await page.title()}`);

    // Simulasi interaksi manusia dikit sebelum ambil token
    await page.mouse.move(100, 200);
    await page.waitForTimeout(500);
    await page.mouse.move(300, 400);
    await page.mouse.wheel(0, 300);

    // Tunggu Turnstile selesai jalan (managed/invisible mode) dan token keisi
    await page.waitForFunction(() => {
      const el = document.querySelector('input[name="cf-turnstile-response"]');
      return el && el.value && el.value.length > 20;
    }, { timeout: 30000 });

    const turnstileToken = await page.$eval(
      'input[name="cf-turnstile-response"]',
      el => el.value
    );

    const elapsedMs = Date.now() - startTime;

    const result = {
      success: true,
      turnstileToken,
      elapsedMs,
      interacted: true
    };

    // Print JSON di baris terakhir biar gampang di-parse dari python
    console.log('RESULT_JSON:' + JSON.stringify(result));
    // ----------------------------------------------------
  } catch (error) {
    console.error("Terjadi eror:", error.message);
    console.log('RESULT_JSON:' + JSON.stringify({ success: false, error: error.message }));
  } finally {
    await browser.close();
    console.log("Browser ditutup.");
  }
})();
