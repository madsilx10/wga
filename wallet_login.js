// ============================================================================
// TEMPLATE UTAMA PLAYWRIGHT NODE.JS UNTUK TERMUX (GLOBAL + STEALTH)
// ============================================================================

// 1. Trik manipulasi platform agar lolos pengecekan di Android
Object.defineProperty(process, 'platform', { get: () => 'linux' });

const { chromium } = require('playwright-extra');
const stealthPlugin = require('puppeteer-extra-plugin-stealth')();
chromium.use(stealthPlugin);
const { ethers } = require('ethers');

// Privkey dikirim sebagai argumen: node wallet_login.js 0xPRIVKEY
const PRIVKEY = process.argv[2];
if (!PRIVKEY) {
  console.log('RESULT_JSON:' + JSON.stringify({ success: false, error: 'Privkey gak dikasih (argv[2] kosong)' }));
  process.exit(1);
}
const wallet = new ethers.Wallet(PRIVKEY);
const ADDRESS = wallet.address;

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
    ]
  });

  const context = await browser.newContext({
    userAgent: 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36'
  });
  const page = await context.newPage();

  // Block resource berat yang gak perlu buat proses login (ngurangin beban RAM)
  await page.route('**/*', (route) => {
    const type = route.request().resourceType();
    if (['image', 'font', 'media'].includes(type)) {
      return route.abort();
    }
    return route.continue();
  });

  try {
    // ----------------------------------------------------
    // [KODE SCRAPING / BOT SAYA AKAN DIMASUKKAN DI SINI]

    // Expose fungsi signing asli (pake privkey) yang bisa dipanggil dari browser context
    await page.exposeFunction('__nodeSignMessage', async (message) => {
      // message dari personal_sign biasanya hex string (0x...) berisi bytes pesan asli
      let signature;
      if (typeof message === 'string' && message.startsWith('0x')) {
        const bytes = ethers.utils.arrayify(message);
        signature = await wallet.signMessage(bytes);
      } else {
        signature = await wallet.signMessage(message);
      }
      return signature;
    });

    // Inject fake EIP-1193 wallet provider (niruin MetaMask)
    await page.addInitScript((fakeAddress) => {
      const listeners = {};
      const on = (event, cb) => {
        if (!listeners[event]) listeners[event] = [];
        listeners[event].push(cb);
      };
      const emit = (event, ...args) => {
        (listeners[event] || []).forEach(cb => { try { cb(...args); } catch (e) {} });
      };
      const fakeProvider = {
        isMetaMask: true,
        isStatus: false,
        _metamask: { isUnlocked: () => Promise.resolve(true) },
        selectedAddress: fakeAddress,
        chainId: '0x38', // BSC mainnet, sesuaikan kalau perlu
        networkVersion: '56',
        request: async ({ method, params }) => {
          console.log('[PROVIDER]', method, JSON.stringify(params));
          if (method === 'eth_accounts') {
            // Belum pernah di-approve = kosong, biar dapp nampilin tombol "Connect Wallet" normal
            return window.__fakeConnected ? [fakeAddress] : [];
          }
          if (method === 'eth_requestAccounts') {
            window.__fakeConnected = true;
            console.log('[PROVIDER] -> return address', fakeAddress);
            setTimeout(() => {
              emit('connect', { chainId: '0x38' });
              emit('accountsChanged', [fakeAddress]);
              emit('chainChanged', '0x38');
            }, 50);
            return [fakeAddress];
          }
          if (method === 'eth_chainId') return '0x38';
          if (method === 'net_version') return '56';
          if (method === 'personal_sign') {
            console.log('[PROVIDER] personal_sign dipanggil, minta node buat sign...');
            const message = params[0];
            try {
              const sig = await window.__nodeSignMessage(message);
              console.log('[PROVIDER] sign sukses, sig=', sig ? sig.slice(0, 20) + '...' : sig);
              return sig;
            } catch (e) {
              console.log('[PROVIDER] sign GAGAL:', e.message);
              throw e;
            }
          }
          if (method === 'wallet_switchEthereumChain' || method === 'wallet_addEthereumChain') {
            return null;
          }
          return null;
        },
        on: on,
        removeListener: (event, cb) => {
          if (listeners[event]) listeners[event] = listeners[event].filter(l => l !== cb);
        },
        isConnected: () => true,
      };
      window.ethereum = fakeProvider;
      window.ethereum.providers = [fakeProvider];

      // EIP-6963: announce provider biar MetaMask SDK / wagmi detect sebagai extension asli
      // (kalau gak ada ini, banyak dapp modern langsung fallback ke QR/mobile connect)
      const providerDetail = {
        info: {
          uuid: '350670db-19fa-4704-a166-e52e178b59d2',
          name: 'MetaMask',
          icon: 'data:image/svg+xml;base64,',
          rdns: 'io.metamask',
        },
        provider: fakeProvider,
      };
      const announceProvider = () => {
        window.dispatchEvent(new CustomEvent('eip6963:announceProvider', { detail: providerDetail }));
      };
      window.addEventListener('eip6963:requestProvider', announceProvider);
      announceProvider();
    }, ADDRESS);

    page.on('console', msg => console.log('[BROWSER]', msg.type(), msg.text()));
    page.on('pageerror', err => console.log('[PAGEERROR]', err.message));
    page.on('request', req => {
      if (req.url().includes('/users/') || req.url().includes('turnstile') || req.url().includes('cloudflare')) {
        console.log('[NET->]', req.method(), req.url());
      }
    });
    page.on('response', res => {
      if (res.url().includes('/users/')) {
        console.log('[NET<-]', res.status(), res.url());
      }
    });

    // Siapkan listener buat nangkep response /users/login SEBELUM klik apapun
    const loginResponsePromise = page.waitForResponse(
      res => res.url().includes('/users/login') && res.request().method() === 'POST',
      { timeout: 120000 }
    );

    await page.goto('https://wga.xyz/reward', { waitUntil: 'domcontentloaded', timeout: 45000 });
    console.log(`Berhasil masuk ke: ${await page.title()}`);

    await page.getByText('Connect Wallet', { exact: true }).waitFor({ timeout: 30000 });
    await page.waitForTimeout(1000);
    await page.getByText('Connect Wallet', { exact: true }).click();
    await page.waitForTimeout(1500);

    console.log('[STEP] Mau klik Connect with MetaMask...');
    await page.getByRole('button', { name: 'Connect with MetaMask' }).click({ force: true });
    console.log('[STEP] Udah klik (role=button). Nunggu flow lanjut...');
    await page.waitForTimeout(4000);

    const modalHtml = await page.evaluate(() => {
      const modal = document.querySelector('[class*="modal"], [role="dialog"]');
      return modal ? modal.innerHTML.slice(0, 1500) : 'NO_MODAL_FOUND';
    });
    console.log('[STEP] modalHtml setelah klik:', modalHtml);

    await page.screenshot({ path: 'debug_after_connect.png', fullPage: true });
    console.log('[STEP] Screenshot debug_after_connect.png disimpan.');

    // Cek kalau ada tombol Sign/Login/Confirm tambahan yang perlu diklik
    const extraButtons = await page.evaluate(() => {
      return Array.from(document.querySelectorAll('button, [role="button"]'))
        .map(el => el.innerText.trim())
        .filter(t => t);
    });
    console.log('[STEP] Tombol yang kedetect setelah connect:', JSON.stringify(extraButtons));

    if (extraButtons.includes('Sign message')) {
      console.log('[STEP] Klik tombol "Sign message"...');
      await page.getByRole('button', { name: 'Sign message' }).click({ force: true });
      console.log('[STEP] Udah klik Sign message, nunggu login response...');
    }

    // Tunggu situsnya sendiri yang proses Turnstile + nonce + sign + login
    const loginResponse = await loginResponsePromise;
    const loginBody = await loginResponse.json();

    if (!loginBody.accessToken) {
      throw new Error('Login response gak ada accessToken: ' + JSON.stringify(loginBody));
    }

    const result = {
      success: true,
      address: ADDRESS,
      accessToken: loginBody.accessToken,
    };

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
