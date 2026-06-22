"""一回だけの診断: StockAnalysis.asp に遷移したとき何が表示されるかを捕捉。
ログイン1回のみ・リトライなし。is_session_expired が誤判定か実セッション切れかを判別。"""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from playwright.sync_api import sync_playwright
from zozo_scraper import ZOZOScraper, SESSION_EXPIRED_MARKERS, BASE_URL

s = ZOZOScraper(
    basic_user=os.environ["ZOZO_BASIC_USER"], basic_pw=os.environ["ZOZO_BASIC_PASSWORD"],
    login_id=os.environ["ZOZO_LOGIN_ID"], password=os.environ["ZOZO_LOGIN_PASSWORD"],
    headless=True)

with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=[
        "--no-sandbox", "--disable-blink-features=AutomationControlled",
        "--disable-features=IsolateOrigins,site-per-process", "--disable-web-security"])
    ctx = s._new_context(b)
    page = ctx.new_page()
    s._login(page)
    print("after login URL:", page.url)
    # ログイン直後のヘッダーからログインユーザー名を取得（どのアカウントか確認）
    try:
        top = page.inner_text("body")[:400]
        print("--- ログイン直後ページ先頭 (ユーザー名を含む) ---")
        print(top)
        print("--- ここまで ---")
    except Exception as e:
        print("header capture failed:", e)
    page.goto(BASE_URL + "StockAnalysis.asp?c=init", wait_until="domcontentloaded", timeout=45000)
    import time; time.sleep(2)
    print("stockanalysis URL:", page.url)
    body = page.inner_text("body")
    print("body length:", len(body))
    print("\n--- どのマーカーが一致したか ---")
    for m in SESSION_EXPIRED_MARKERS:
        print(f"  {'HIT' if m in body else '   '}  {m}")
    print("\n--- form1 / ダウンロードボタンの有無 ---")
    print("  form[name=form1]:", page.locator("form[name='form1']").count())
    print("  ダウンロード btn:", page.locator("button:has-text('ダウンロード')").count())
    print("  StockAnalysis checkbox FavoriteList:", page.locator("input[name='FavoriteList']").count())
    print("\n--- body 先頭800字 ---")
    print(body[:800])
    page.screenshot(path=str(Path(__file__).resolve().parent / "diag_stockanalysis.png"))
    b.close()
