import asyncio
from pyrogram import Client

TG_API_ID   = 0    # isi API ID dari my.telegram.org
TG_API_HASH = ''   # isi API HASH dari my.telegram.org

sessions = [l.strip() for l in open('session.txt').read().strip().split('\n') if l.strip()]

async def get_id(session_str, idx):
    app = Client(f'tmp_{idx}', api_id=TG_API_ID, api_hash=TG_API_HASH, session_string=session_str)
    async with app:
        me = await app.get_me()
        return str(me.id)

async def main():
    ids = []
    for i, s in enumerate(sessions):
        try:
            tg_id = await get_id(s, i)
            ids.append(tg_id)
            print(f'[{i+1}] ID: {tg_id}')
        except Exception as e:
            print(f'[{i+1}] ERROR: {e}')
            ids.append('')
    open('tgid.txt', 'w').write('\n'.join(ids))
    print(f'\nSimpan ke tgid.txt ✓')

asyncio.run(main())
