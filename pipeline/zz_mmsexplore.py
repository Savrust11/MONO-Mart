import os, time, json
from pathlib import Path
from playwright.sync_api import sync_playwright
SESS = Path(r"C:\Users\Administrator\Downloads\system\pipeline\scrapers\sessions")
STATE = SESS / "mms_state.json"
BASE = "https://mms.a-rg.work/"
print("セッションファイル:", STATE.exists(), f"{STATE.stat().st_size}バイト" if STATE.exists() else "")
try:
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(storage_state=str(STATE), locale="ja-JP")
        pg = ctx.new_page()
        pg.goto(BASE + "index.php", wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)
        url = pg.url
        loggedin = "login" not in url.lower()
        print("到達URL:", url)
        print("セッション:", "有効（ログイン済み）" if loggedin else "期限切れ（ログイン画面に飛ばされた）")
        if loggedin:
            # メニューのリンク（発注書一覧を探す）を読み取りのみで取得
            links = pg.evaluate(r"""() => [...document.querySelectorAll('a')].map(a=>({t:(a.textContent||'').trim(), h:a.getAttribute('href')})).filter(x=>x.t && x.h)""")
            print("\n--- 発注/order 関連のメニューリンク ---")
            for l in links:
                if any(k in (l['t']+str(l['h'])) for k in ['発注','order','order_list','注文','仕入']):
                    print(f"   {l['t']} -> {l['h']}")
        b.close()
except Exception as e:
    print("失敗:", str(e)[:200])
