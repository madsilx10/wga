import { ethers } from 'ethers';
import fs from 'fs';
import fetch from 'node-fetch';
import crypto from 'crypto';
import { TelegramClient } from 'telegram';
import { StringSession } from 'telegram/sessions/index.js';

// ============================================================
// CONFIG
// ============================================================
const BASE_URL     = 'https://api.wga.xyz';
const INVITE_CODE  = 'Z0V0DL3T';
const TG_API_ID    = 0;       // isi API ID dari my.telegram.org
const TG_API_HASH  = '';      // isi API HASH dari my.telegram.org
const DELAY_MS     = 3000;    // jeda antar akun (ms)

// ============================================================
// READ FILES
// ============================================================
function readLines(path) {
  return fs.readFileSync(path, 'utf8').trim().split('\n').map(l => l.trim()).filter(Boolean);
}

function readXAccounts(path) {
  const lines = readLines(path);
  const accounts = [];
  for (let i = 0; i < lines.length; i += 2) {
    if (lines[i] && lines[i + 1]) {
      accounts.push({ auth_token: lines[i], ct0: lines[i + 1] });
    }
  }
  return accounts;
}

const wallets    = readLines('wallet.txt');
const sessions   = readLines('session.txt');
const xAccounts  = readXAccounts('xakun.txt');

// ============================================================
// HELPERS
// ============================================================
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

function apiHeaders(token = '') {
  return {
    'Accept': 'application/json, text/plain, */*',
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`,
    'Origin': 'https://wga.xyz',
    'Referer': 'https://wga.xyz/',
    'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 Chrome/140.0.0.0 Safari/537.36',
  };
}

function log(idx, msg) {
  console.log(`[Akun ${idx + 1}] ${msg}`);
}

// ============================================================
// STEP 1 — LOGIN
// ============================================================
async function login(privkey) {
  const wallet  = new ethers.Wallet(privkey);
  const address = wallet.address;

  // Nonce
  const nonceRes = await fetch(`${BASE_URL}/users/nonce`, {
    method: 'POST',
    headers: apiHeaders(),
    body: JSON.stringify({ address }),
  });
  const { message } = await nonceRes.json();

  // Sign
  const signature = await wallet.signMessage(message);

  // Login
  const loginRes = await fetch(`${BASE_URL}/users/login`, {
    method: 'POST',
    headers: apiHeaders(),
    body: JSON.stringify({ address, referrerInviteCode: INVITE_CODE, signature }),
  });
  const data = await loginRes.json();

  if (!data.accessToken) throw new Error(`Login gagal: ${JSON.stringify(data)}`);
  return { address, token: data.accessToken };
}

// ============================================================
// STEP 2 — LINK TELEGRAM
// ============================================================
async function linkTelegram(token, sessionStr, idx) {
  // Ambil telegramId dari session
  const client = new TelegramClient(new StringSession(sessionStr), TG_API_ID, TG_API_HASH, {
    connectionRetries: 3,
  });
  await client.connect();
  const me = await client.getMe();
  const telegramId = me.id.toString();
  await client.disconnect();

  log(idx, `Telegram ID: ${telegramId}`);

  // Link ke WGA
  const res = await fetch(`${BASE_URL}/users/telegram/link`, {
    method: 'POST',
    headers: apiHeaders(token),
    body: JSON.stringify({ telegramId }),
  });

  if (!res.ok) throw new Error(`Link Telegram gagal: ${res.status}`);
  log(idx, 'Telegram linked ✓');
}

// ============================================================
// STEP 3 — LINK X (PKCE OAUTH2)
// ============================================================
async function linkX(token, xCreds, idx) {
  const { auth_token, ct0 } = xCreds;

  // Generate PKCE
  const codeVerifier  = crypto.randomBytes(32).toString('base64url');
  const codeChallenge = crypto.createHash('sha256').update(codeVerifier).digest('base64url');
  const state         = crypto.randomBytes(16).toString('base64url');

  const CLIENT_ID    = 'NHV2cmdlek00UGpPNEM5TXlKcW46MTpjaQ';
  const REDIRECT_URI = 'https://api.wga.xyz/users/social-link/x/callback';
  const SCOPE        = 'tweet.read users.read follows.write follows.read';

  // Trigger authorize di WGA (kosong, tapi tetap dihit)
  await fetch(`${BASE_URL}/users/social-link/x/authorize`, {
    headers: apiHeaders(token),
  });

  // Build OAuth URL
  const params = new URLSearchParams({
    response_type: 'code',
    client_id: CLIENT_ID,
    redirect_uri: REDIRECT_URI,
    scope: SCOPE,
    state,
    code_challenge: codeChallenge,
    code_challenge_method: 'S256',
  });
  const oauthUrl = `https://x.com/i/oauth2/authorize?${params}`;

  // Cookie X
  const xCookie = `auth_token=${auth_token}; ct0=${ct0}`;
  const xHeaders = {
    'Cookie': xCookie,
    'Authorization': `Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA`,
    'x-csrf-token': ct0,
    'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 Chrome/140.0.0.0 Safari/537.36',
    'Referer': 'https://wga.xyz/',
  };

  // GET OAuth page → ambil auth_code
  const oauthPage = await fetch(oauthUrl, {
    headers: { ...xHeaders, 'Accept': 'text/html,application/xhtml+xml' },
    redirect: 'manual',
  });

  // TODO: parse auth_code dari response / handle approve
  // Ini perlu di-test dulu untuk tau apakah langsung dapat code
  // atau perlu POST approve dulu
  log(idx, `[X] OAuth page status: ${oauthPage.status} — TODO: approve flow`);
}

// ============================================================
// MAIN — PROCESS AKUN
// ============================================================
async function processAccount(idx) {
  const privkey  = wallets[idx];
  const session  = sessions[idx];
  const xCreds   = xAccounts[idx];

  if (!privkey || !session || !xCreds) {
    log(idx, 'Data tidak lengkap, skip.');
    return;
  }

  log(idx, 'Mulai...');

  try {
    const { address, token } = await login(privkey);
    log(idx, `Login OK → ${address}`);

    await linkTelegram(token, session, idx);
    await sleep(1000);

    await linkX(token, xCreds, idx);

    log(idx, 'Selesai ✓');
  } catch (e) {
    log(idx, `ERROR: ${e.message}`);
  }
}

// ============================================================
// CLI
// ============================================================
const args  = process.argv.slice(2);
const mode  = args[0] || '1';
const total = wallets.length;

(async () => {
  if (mode === 'all') {
    // Semua akun
    for (let i = 0; i < total; i++) {
      await processAccount(i);
      if (i < total - 1) await sleep(DELAY_MS);
    }
  } else if (mode.startsWith('from')) {
    // Dari index N sampai akhir (from3 = mulai dari akun ke-3)
    const start = parseInt(mode.replace('from', '')) - 1;
    for (let i = start; i < total; i++) {
      await processAccount(i);
      if (i < total - 1) await sleep(DELAY_MS);
    }
  } else {
    // 1 akun (default akun ke-1, atau kasih angka: node wga.js 3)
    const idx = parseInt(mode) - 1;
    await processAccount(idx);
  }
})();
