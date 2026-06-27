"""診断: ZOZO「商品別実績(新)」レポートが何日まで選択/表示できるかを確認。
ログイン→レポートを開く→スクリーンショット保存＋日付テキスト/日付inputを全フレームから抽出。
これで「ZOZOに06-22以降が有るのか/無いのか」を客観判定する。
"""
import os
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright
from zozo_scraper import ZOZOScraper, BASE_URL

OUT = Path(__file__).parent / "screenshots"
OUT.mkdir(exist_ok=True)

creds = {k: os.environ.get(k, "") for k in
         ("ZOZO_BASIC_USER", "ZOZO_BASIC_PASSWORD", "ZOZO_LOGIN_ID", "ZOZO_LOGIN_PASSWORD")}
if not all(creds.values()):
    print("Missing creds (source .zozo_env.sh)"); sys.exit(2)

scraper = ZOZOScraper(basic_user=creds["ZOZO_BASIC_USER"], basic_pw=creds["ZOZO_BASIC_PASSWORD"],
                      login_id=creds["ZOZO_LOGIN_ID"], password=creds["ZOZO_LOGIN_PASSWORD"], headless=True)

DATE_RE = re.compile(r"20\d\d[-/.]\d{1,2}[-/.]\d{1,2}")
found_dates_iframe = set()

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=[
        "--no-sandbox", "--disable-blink-features=AutomationControlled",
        "--disable-features=IsolateOrigins,site-per-process", "--disable-web-security"])
    ctx = browser.new_context(
        locale="ja-JP", viewport={"width": 1920, "height": 1200}, accept_downloads=True,
        user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
        http_credentials={"username": creds["ZOZO_BASIC_USER"], "password": creds["ZOZO_BASIC_PASSWORD"]})
    ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});window.chrome={runtime:{}};")
    page = ctx.new_page()

    print("[1] login..."); scraper._login(page)
    print("[2] open LookerDashboards.asp...")
    page.goto(BASE_URL + "LookerDashboards.asp", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(3000)
    try:
        page.get_by_role("link", name="商品別実績(新)").first.click(timeout=10000)
        print("[3] clicked link 商品別実績(新)")
    except Exception as e:
        print("[3] click failed:", e)
    page.wait_for_load_state("networkidle", timeout=60000)
    # Lookerダッシュボードiframe(embed/dashboards)が出るまで最大160s待つ
    import time
    dash = None
    for _ in range(32):
        time.sleep(5)
        for f in page.frames:
            if "embed/dashboards/" in (f.url or ""):
                dash = f; break
        if dash:
            print("[4] dashboard iframe attached:", dash.url[:70]); break
    if not dash:
        print("[4] dashboard iframe 出ず（レポート未描画）")
    time.sleep(15)
    page.screenshot(path=str(OUT / "diag_perf_report.png"), full_page=True)
    print("[5] screenshot saved")

    # 日付フィルタ「前週」を開いて選択肢を確認
    if dash:
        try:
            dash.get_by_text("前週", exact=True).first.click(timeout=8000)
            time.sleep(4)
            page.screenshot(path=str(OUT / "diag_date_dropdown.png"), full_page=True)
            print("[6] 日付フィルタを開いた→スクショ")
            opts = dash.locator('[role="option"], li, [role="menuitem"]').all()
            texts = []
            for o in opts[:40]:
                try:
                    t = o.inner_text(timeout=500).strip()
                    if t and len(t) < 20: texts.append(t)
                except Exception: pass
            print("[6] 日付の選択肢候補:", texts)
        except Exception as e:
            print("[6] 日付フィルタ展開失敗:", str(e)[:80])
    # iframe本文からも日付抽出を試す
    if dash:
        try:
            t = dash.evaluate("()=>document.body?document.body.innerText:''")
            for m in DATE_RE.findall(t or ""):
                found_dates_iframe.add(m.replace('/', '-').replace('.', '-'))
        except Exception:
            pass

    # 全フレームから日付テキスト・日付inputを抽出
    found_dates = set()
    inputs = []
    for fr in page.frames:
        try:
            txt = fr.locator("body").inner_text(timeout=3000)
            for m in DATE_RE.findall(txt):
                found_dates.add(m.replace("/", "-").replace(".", "-"))
        except Exception:
            pass
        try:
            for di in fr.locator('input[type="date"]').all():
                v = di.get_attribute("value"); mn = di.get_attribute("min"); mx = di.get_attribute("max")
                inputs.append({"value": v, "min": mn, "max": mx})
        except Exception:
            pass
    norm = sorted(d for d in found_dates if re.match(r"20\d\d-\d{1,2}-\d{1,2}", d))
    print("\n=== 結果 ===")
    norm_if = sorted(d for d in found_dates_iframe if re.match(r"20\d\d-\d{1,2}-\d{1,2}", d))
    print("Lookerレポート(iframe)内の日付(上位):", norm_if[-12:] if norm_if else "なし")
    print("レポート内に出現した日付(上位):", norm[-12:] if norm else "なし")
    print("date入力(value/min/max):", inputs if inputs else "なし")
    print("→ 06-22以降の日付が見えれば『ZOZOに有る』、06-21までなら『ZOZO未公開』")
    browser.close()
