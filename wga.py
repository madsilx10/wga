import asyncio
import hashlib
import base64
import secrets
import requests
from eth_account import Account
from eth_account.messages import encode_defunct
from pyrogram import Client

# ============================================================
# CONFIG
# ============================================================
BASE_URL    = 'https://api.wga.xyz'
INVITE_CODE = 'Z0V0DL3T'
TG_API_ID   = 0       # isi API ID dari my.telegram.org
TG_API_HASH = ''      # isi API HASH dari my.telegram.org
WGA_BOT     = 'WgaAgentBot'
DELAY       = 3

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
# CEK STATUS SOCIAL LINK
# ============================================================
def is_x_linked(token):
    r = requests.get(f'{BASE_URL}/users/social-link/status', headers=api_headers(token))
    if r.status_code != 200:
        return False
    data = r.json()
    # cek field x / twitter linked
    return data.get('x') or data.get('twitter') or data.get('xLinked') or False

# ============================================================
# STEP 2 — LINK X (PKCE OAUTH2)
# ============================================================
async def link_x(token, x_creds, idx):
    from curl_cffi import requests as cf_requests
    from urllib.parse import urlparse, parse_qs

    auth_token = x_creds['auth_token']
    ct0        = x_creds['ct0']

    # Generate PKCE
    code_verifier  = secrets.token_urlsafe(32)
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).rstrip(b'=').decode()

    # Hit authorize WGA
    r = requests.get(
        f'{BASE_URL}/users/social-link/x/authorize',
        headers={**api_headers(token), 'x-code-challenge': code_challenge},
    )
    data = r.json()
    auth_url = data.get('authorizationUrl')
    if not auth_url:
        raise Exception(f'Authorize gagal: {data}')

    # Parse params dari auth_url
    parsed_auth = urlparse(auth_url)
    qs    = parse_qs(parsed_auth.query)
    state = qs.get('state', [''])[0]

    x_api_headers = {
        'Cookie': f'auth_token={auth_token}; ct0={ct0}',
        'Authorization': 'Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA',
        'x-csrf-token': ct0,
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 Chrome/140.0.0.0 Safari/537.36',
        'Referer': auth_url,
        'Origin': 'https://x.com',
    }

    # GET ke X internal API → dapet auth_code dari JSON
    r = cf_requests.get(
        'https://x.com/i/api/2/oauth2/authorize',
        params={
            'response_type':         qs.get('response_type', ['code'])[0],
            'client_id':             qs.get('client_id', [''])[0],
            'redirect_uri':          qs.get('redirect_uri', [''])[0],
            'scope':                 qs.get('scope', [''])[0],
            'state':                 state,
            'code_challenge':        qs.get('code_challenge', [''])[0],
            'code_challenge_method': qs.get('code_challenge_method', ['S256'])[0],
        },
        headers=x_api_headers,
        impersonate='chrome110'
    )

    resp_json = r.json()
    auth_code = resp_json.get('auth_code')
    if not auth_code:
        raise Exception(f'auth_code tidak ditemukan: {resp_json}')

    # Approve
    r2 = cf_requests.post(
        'https://x.com/i/api/2/oauth2/authorize',
        headers={
            'Cookie': f'auth_token={auth_token}; ct0={ct0}',
            'Authorization': 'Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA',
            'x-csrf-token': ct0,
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 Chrome/140.0.0.0 Safari/537.36',
            'Referer': auth_url,
            'Origin': 'https://x.com',
        },
        data={'approval': 'true', 'code': auth_code},
        allow_redirects=False,
        impersonate='chrome110'
    )

    approve_data = r2.json()
    redirect_uri = approve_data.get('redirect_uri')
    if not redirect_uri:
        raise Exception(f'redirect_uri tidak ada: {approve_data}')

    r3 = requests.get(redirect_uri, headers=api_headers(token), allow_redirects=True)
    if r3.status_code != 200:
        raise Exception(f'WGA callback gagal: {r3.status_code} {r3.text}')
    log(idx, '[X] X linked ✓')

# ============================================================
# STEP 3 — CHECK (total XYZ)
# ============================================================
def do_check(token, idx):
    r = requests.get(f"{BASE_URL}/users/random-boxes", headers=api_headers(token))
    if r.status_code != 200:
        log(idx, f"[Check] Gagal: {r.status_code}")
        return
    data = r.json()
    total_xyz = data.get("totalEarnedXyz", 0)
    unopened  = data.get("unopenedCount", 0)
    log(idx, f"[Check] Total XYZ: {total_xyz} | Box belum dibuka: {unopened}")

# ============================================================
# STEP 4 — FOLLOW
# ============================================================
def do_follow(token, idx):
    endpoints = [
        '/users/social-link/X/follow',
        '/users/social-link/X_WGA_XYZ/follow',
    ]
    for ep in endpoints:
        r = requests.post(f'{BASE_URL}{ep}', headers=api_headers(token))
        log(idx, f'[Follow] {ep.split("/")[-2]} → {r.status_code}')

# ============================================================
# STEP 4 — CHECK IN
# ============================================================
def do_checkin(token, idx):
    r = requests.post(f'{BASE_URL}/users/check-in', headers=api_headers(token))
    log(idx, f'[Check-in] status: {r.status_code}')
    if r.status_code == 200:
        data = r.json()
        log(idx, f'[Check-in] rewarded: {data.get("rewarded")} | box: {data.get("randomBoxIssued")}')
    else:
        log(idx, f'[Check-in] response: {r.text[:200]}')

# ============================================================
# STEP 5 — OPEN BOX
# ============================================================
def do_open_boxes(token, idx):
    r = requests.get(f'{BASE_URL}/users/random-boxes', headers=api_headers(token))
    if r.status_code != 200:
        log(idx, f'[Box] Gagal ambil boxes: {r.status_code}')
        return
    boxes = r.json().get('boxes', [])
    issued = [b for b in boxes if b.get('status') == 'ISSUED']
    if not issued:
        log(idx, '[Box] Tidak ada box yang perlu dibuka')
        return
    for box in issued:
        box_id = box['id']
        reason = box.get('reason', '')
        r2 = requests.post(f'{BASE_URL}/users/random-boxes/{box_id}/open', headers=api_headers(token))
        if r2.status_code == 200:
            data = r2.json()
            log(idx, f'[Box] {reason} (id:{box_id}) → reward: {data.get("rewardAmount")}')
        else:
            log(idx, f'[Box] {reason} (id:{box_id}) → gagal {r2.status_code}')

# ============================================================
# PROCESS AKUN
# ============================================================
async def process_account(idx, mode):
    privkey = wallets[idx]
    x_creds = x_accounts[idx] if idx < len(x_accounts) else None

    log(idx, f'Mulai [{mode}]...')
    try:
        address, token = login(privkey)
        log(idx, f'Login OK → {address}')

        if mode == 'all':
            # Cek X linked dulu
            if is_x_linked(token):
                log(idx, '[X] Sudah linked, skip konek X')
            else:
                if not x_creds:
                    log(idx, '[X] xakun.txt tidak ada untuk akun ini, skip konek X')
                else:
                    await link_x(token, x_creds, idx)
            await asyncio.sleep(1)
            do_follow(token, idx)
            await asyncio.sleep(1)
            do_checkin(token, idx)
            await asyncio.sleep(1)
            do_open_boxes(token, idx)

        elif mode == 'daily':
            do_checkin(token, idx)
            await asyncio.sleep(1)
            do_open_boxes(token, idx)

        elif mode == 'open box':
            do_open_boxes(token, idx)

        elif mode == 'check':
            do_check(token, idx)

        log(idx, 'Selesai ✓')
    except Exception as e:
        log(idx, f'ERROR: {e}')

# ============================================================
# RUN AKUN
# ============================================================
async def run_accounts(mode, indices):
    for i, idx in enumerate(indices):
        await process_account(idx, mode)
        if i < len(indices) - 1:
            await asyncio.sleep(DELAY)

# ============================================================
# MAIN
# ============================================================
async def main():
    total = len(wallets)
    print(f'\n=== WGA.xyz Bot | {total} akun ===')
    print('Mode:')
    print('  1. all      — link X + follow + check-in + open box')
    print('  2. daily    — check-in + open box')
    print('  3. open box — buka box aja')
    print('  4. check   — cek total XYZ')
    mode_map = {'1': 'all', '2': 'daily', '3': 'open box', '4': 'check'}
    pilihan = input('\nPilih mode [1/2/3/4]: ').strip()
    mode = mode_map.get(pilihan)
    if not mode:
        print('Pilihan tidak valid.')
        return

    print('\nAkun:')
    print('  1. Jalankan 1 akun')
    print('  2. Jalankan semua akun')
    print('  3. Jalankan dari akun ke-N sampai akhir')
    akun_pilihan = input('\nPilih [1/2/3]: ').strip()

    if akun_pilihan == '1':
        idx = int(input(f'Akun ke berapa? (1-{total}): ').strip()) - 1
        await run_accounts(mode, [idx])
    elif akun_pilihan == '2':
        await run_accounts(mode, list(range(total)))
    elif akun_pilihan == '3':
        start = int(input(f'Mulai dari akun ke berapa? (1-{total}): ').strip()) - 1
        await run_accounts(mode, list(range(start, total)))
    else:
        print('Pilihan tidak valid.')

if __name__ == '__main__':
    asyncio.run(main())
