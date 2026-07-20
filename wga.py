import asyncio
import hashlib
import base64
import secrets
import requests
from eth_account import Account
from eth_account.messages import encode_defunct
from pyrogram import Client
from pyrogram.raw.functions.messages import SendBotRequestedPeer

# ============================================================
# CONFIG
# ============================================================
BASE_URL     = 'https://api.wga.xyz'
INVITE_CODE  = 'Z0V0DL3T'
TG_API_ID    = 0       # isi API ID dari my.telegram.org
TG_API_HASH  = ''      # isi API HASH dari my.telegram.org
WGA_BOT      = 'WgaAgentBot'
DELAY        = 3

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

wallets    = read_lines('wallet.txt')
sessions   = read_lines('session.txt')
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
# STEP 1 — LOGIN WALLET
# ============================================================
def login(privkey):
    acct    = Account.from_key(privkey)
    address = acct.address

    r = requests.post(f'{BASE_URL}/users/nonce', json={'address': address}, headers=api_headers())
    message = r.json()['message']

    msg_hash  = encode_defunct(text=message)
    signed    = Account.sign_message(msg_hash, private_key=privkey)
    signature = signed.signature.hex()
    if not signature.startswith('0x'):
        signature = '0x' + signature

    r = requests.post(f'{BASE_URL}/users/login', headers=api_headers(), json={
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
    app = Client(
        f'wga_{idx}',
        api_id=TG_API_ID,
        api_hash=TG_API_HASH,
        session_string=session_str
    )
    async with app:
        me          = await app.get_me()
        telegram_id = str(me.id)
        log(idx, f'Telegram ID: {telegram_id}')

        # Kirim /start ke bot WGA buat trigger konfirmasi
        await app.send_message(WGA_BOT, '/start')
        await asyncio.sleep(2)

        # Ambil pesan terakhir dari bot, cari tombol konfirmasi
        async for msg in app.get_chat_history(WGA_BOT, limit=5):
            if msg.reply_markup:
                for row in msg.reply_markup.inline_keyboard:
                    for btn in row:
                        if btn.callback_data:
                            await app.request_callback_answer(
                                chat_id=WGA_BOT,
                                message_id=msg.id,
                                callback_data=btn.callback_data
                            )
                            log(idx, 'Konfirmasi bot ✓')
                            break
                break

    # POST telegramId ke WGA
    r = requests.post(f'{BASE_URL}/users/telegram/link', headers=api_headers(token), json={'telegramId': telegram_id})
    if r.status_code != 200:
        raise Exception(f'Link Telegram gagal: {r.status_code} {r.text}')
    log(idx, 'Telegram linked ✓')

# ============================================================
# STEP 3 — LINK X (PKCE OAUTH2)
# ============================================================
async def link_x(token, x_creds, idx):
    auth_token = x_creds['auth_token']
    ct0        = x_creds['ct0']

    # Generate PKCE dulu
    code_verifier  = secrets.token_urlsafe(32)
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).rstrip(b'=').decode()

    # Hit authorize WGA dengan code_challenge kita
    r = requests.get(
        f'{BASE_URL}/users/social-link/x/authorize',
        headers={**api_headers(token), 'x-code-challenge': code_challenge},
    )
    log(idx, f'[X] Authorize status: {r.status_code}')
    data = r.json()
    auth_url = data.get('authorizationUrl')
    if not auth_url:
        raise Exception(f'Authorize gagal: {data}')
    log(idx, f'[X] Auth URL: {auth_url[:80]}...')

    from curl_cffi import requests as cf_requests
    from urllib.parse import urlparse, parse_qs
    from bs4 import BeautifulSoup

    x_headers = {
        'Cookie': f'auth_token={auth_token}; ct0={ct0}',
        'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 Chrome/140.0.0.0 Safari/537.36',
        'Referer': 'https://wga.xyz/',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'cross-site',
        'Sec-Fetch-User': '?1',
        'Upgrade-Insecure-Requests': '1',
    }

    # GET halaman OAuth
    r = cf_requests.get(auth_url, headers=x_headers, allow_redirects=True, impersonate='chrome110')
    log(idx, f'[X] OAuth GET status: {r.status_code}')

    # Parse authenticity_token
    soup = BeautifulSoup(r.text, 'html.parser')
    auth_token_field = soup.find('input', {'name': 'authenticity_token'})
    if not auth_token_field:
        raise Exception('[X] authenticity_token tidak ditemukan')
    authenticity_token = auth_token_field['value']
    log(idx, f'[X] authenticity_token: {authenticity_token[:20]}...')

    # POST approve
    approve_headers = {
        **x_headers,
        'Content-Type': 'application/x-www-form-urlencoded',
        'Referer': auth_url,
        'Sec-Fetch-Site': 'same-origin',
        'x-csrf-token': ct0,
    }
    approve_data = {
        'authenticity_token': authenticity_token,
        'redirect_uri': 'https://api.wga.xyz/users/social-link/x/callback',
        'client_id': 'NHV2cmdlek00UGpPNEM5TXlKcW46MTpjaQ',
        'state': parse_qs(urlparse(auth_url).query).get('state', [''])[0],
        'code_challenge': parse_qs(urlparse(auth_url).query).get('code_challenge', [''])[0],
        'code_challenge_method': 'S256',
        'response_type': 'code',
        'scope': 'tweet.read users.read follows.write follows.read',
    }

    r2 = cf_requests.post(
        'https://x.com/i/oauth2/authorize',
        headers=approve_headers,
        data=approve_data,
        allow_redirects=False,
        impersonate='chrome110'
    )
    log(idx, f'[X] Approve status: {r2.status_code}')

    # Ambil code dari redirect
    location = r2.headers.get('location', '')
    log(idx, f'[X] Redirect: {location[:100]}')

    parsed = urlparse(location)
    code = parse_qs(parsed.query).get('code', [None])[0]
    if not code:
        raise Exception(f'[X] Code tidak ditemukan: {location}')

    # Hit callback WGA
    callback_url = f'https://api.wga.xyz/users/social-link/x/callback?state={approve_data["state"]}&code={code}'
    r3 = requests.get(callback_url, headers=api_headers(token), allow_redirects=False)
    log(idx, f'[X] Callback status: {r3.status_code}')
    log(idx, 'X linked ✓')

# ============================================================
# PROCESS AKUN
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

        # await link_telegram(token, session, idx)
        # await asyncio.sleep(1)

        await link_x(token, x_creds, idx)

        log(idx, 'Selesai ✓')
    except Exception as e:
        log(idx, f'ERROR: {e}')

# ============================================================
# MAIN
# ============================================================
async def main():
    total = len(wallets)
    print(f'\n=== WGA.xyz Bot | {total} akun ===')
    print('1. Jalankan 1 akun')
    print('2. Jalankan semua akun')
    print('3. Jalankan dari akun ke-N sampai akhir')
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
