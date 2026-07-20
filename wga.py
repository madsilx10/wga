import asyncio
import sys
import time
import hashlib
import base64
import secrets
import httpx
from eth_account import Account
from eth_account.messages import encode_defunct
from pyrogram import Client

# ============================================================
# CONFIG
# ============================================================
BASE_URL     = 'https://api.wga.xyz'
INVITE_CODE  = 'Z0V0DL3T'
TG_API_ID    = 0       # isi API ID dari my.telegram.org
TG_API_HASH  = ''      # isi API HASH dari my.telegram.org
DELAY        = 3       # jeda antar akun (detik)

# ============================================================
# READ FILES
# ============================================================
def read_lines(path):
    return [l.strip() for l in open(path).read().strip().split('\n') if l.strip()]

def read_x_accounts(path):
    lines = read_lines(path)
    accounts = []
    for i in range(0, len(lines), 2):
        if i + 1 < len(lines):
            accounts.append({'auth_token': lines[i], 'ct0': lines[i+1]})
    return accounts

wallets   = read_lines('wallet.txt')
sessions  = read_lines('session.txt')
x_accounts = read_x_accounts('xakun.txt')

# ============================================================
# HELPERS
# ============================================================
def api_headers(token=''):
    return {
        'Accept': 'application/json, text/plain, */*',
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}',
        'Origin': 'https://wga.xyz',
        'Referer': 'https://wga.xyz/',
        'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 Chrome/140.0.0.0 Safari/537.36',
    }

def log(idx, msg):
    print(f'[Akun {idx+1}] {msg}')

# ============================================================
# STEP 1 — LOGIN
# ============================================================
def login(privkey):
    acct    = Account.from_key(privkey)
    address = acct.address

    # Nonce
    r = httpx.post(f'{BASE_URL}/users/nonce', json={'address': address}, headers=api_headers())
    message = r.json()['message']

    # Sign
    msg_hash  = encode_defunct(text=message)
    signed    = Account.sign_message(msg_hash, private_key=privkey)
    signature = signed.signature.hex()
    if not signature.startswith('0x'):
        signature = '0x' + signature

    # Login
    r = httpx.post(f'{BASE_URL}/users/login', headers=api_headers(), json={
        'address': address,
        'referrerInviteCode': INVITE_CODE,
        'signature': signature,
    })
    data = r.json()
    if 'accessToken' not in data:
        raise Exception(f'Login gagal: {data}')
    return address, data['accessToken']

# ============================================================
# STEP 2 — LINK TELEGRAM
# ============================================================
async def link_telegram(token, session_str, idx):
    app = Client(f'wga_{idx}', api_id=TG_API_ID, api_hash=TG_API_HASH, session_string=session_str)
    async with app:
        me = await app.get_me()
        telegram_id = str(me.id)

    log(idx, f'Telegram ID: {telegram_id}')

    r = httpx.post(f'{BASE_URL}/users/telegram/link', headers=api_headers(token), json={'telegramId': telegram_id})
    if r.status_code != 200:
        raise Exception(f'Link Telegram gagal: {r.status_code} {r.text}')
    log(idx, 'Telegram linked ✓')

# ============================================================
# STEP 3 — LINK X (PKCE OAUTH2)
# ============================================================
async def link_x(token, x_creds, idx):
    auth_token = x_creds['auth_token']
    ct0        = x_creds['ct0']

    # Generate PKCE
    code_verifier  = secrets.token_urlsafe(32)
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).rstrip(b'=').decode()
    state = secrets.token_urlsafe(16)

    CLIENT_ID    = 'NHV2cmdlek00UGpPNEM5TXlKcW46MTpjaQ'
    REDIRECT_URI = 'https://api.wga.xyz/users/social-link/x/callback'
    SCOPE        = 'tweet.read users.read follows.write follows.read'

    # Trigger authorize di WGA
    httpx.get(f'{BASE_URL}/users/social-link/x/authorize', headers=api_headers(token))

    # Build OAuth URL
    params = (
        f'response_type=code'
        f'&client_id={CLIENT_ID}'
        f'&redirect_uri={REDIRECT_URI}'
        f'&scope={SCOPE.replace(" ", "+")}'
        f'&state={state}'
        f'&code_challenge={code_challenge}'
        f'&code_challenge_method=S256'
    )
    oauth_url = f'https://x.com/i/oauth2/authorize?{params}'

    x_headers = {
        'Cookie': f'auth_token={auth_token}; ct0={ct0}',
        'Authorization': 'Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA',
        'x-csrf-token': ct0,
        'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 Chrome/140.0.0.0 Safari/537.36',
        'Referer': 'https://wga.xyz/',
    }

    # GET OAuth page
    r = httpx.get(oauth_url, headers=x_headers, follow_redirects=False)
    log(idx, f'[X] OAuth page status: {r.status_code} — TODO: approve flow')

    # TODO: parse + approve, lanjut setelah test

# ============================================================
# MAIN
# ============================================================
async def process_account(idx):
    privkey = wallets[idx]
    session = sessions[idx]
    x_creds = x_accounts[idx]

    if not privkey or not session or not x_creds:
        log(idx, 'Data tidak lengkap, skip.')
        return

    log(idx, 'Mulai...')
    try:
        address, token = login(privkey)
        log(idx, f'Login OK → {address}')

        await link_telegram(token, session, idx)
        await asyncio.sleep(1)

        await link_x(token, x_creds, idx)

        log(idx, 'Selesai ✓')
    except Exception as e:
        log(idx, f'ERROR: {e}')

async def main():
    total = len(wallets)
    print(f'\n=== WGA.xyz Bot | {total} akun terdeteksi ===')
    print(f'1. Jalankan 1 akun')
    print(f'2. Jalankan semua akun')
    print(f'3. Jalankan dari akun ke-N sampai akhir')
    pilihan = input('\nPilih [1/2/3]: ').strip()

    if pilihan == '1':
        idx = int(input(f'Akun ke berapa? (1-{total}): ').strip()) - 1
        await process_account(idx)

    elif pilihan == '2':
        for i in range(total):
            await process_account(i)
            if i < total - 1:
                await asyncio.sleep(DELAY)

    elif pilihan == '3':
        start = int(input(f'Mulai dari akun ke berapa? (1-{total}): ').strip()) - 1
        for i in range(start, total):
            await process_account(i)
            if i < total - 1:
                await asyncio.sleep(DELAY)

    else:
        print('Pilihan tidak valid.')

if __name__ == '__main__':
    asyncio.run(main())
