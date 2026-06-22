# -*- coding: utf-8 -*-
"""読み取りのみ：4種類の応答の中身(HTML or CSV)を実際に見る。"""
import os, time
from playwright.sync_api import sync_playwright

BASE = "https://to.zozo.jp/to/"
TYPES = [
    ("日別CSV",          "DailyCSVDownLoad",      "shop"),
    ("品番別CSV",        "GoodsInfoCSVDownLoad",  "brandcode"),
    ("アップロード品番CSV", "UploadGoodsCSVDownLoad", "goodslist"),
    ("詳細CSV",          "DetailCSVDownLoad",     "brandcode"),
]
D = os.getenv("DIAG_DATE", "2026-06-14")


def _login(page):
    page.goto(BASE, wait_until="domcontentloaded", timeout=30000)
    if page.locator('input[name="LoginName"]').count() > 0:
        page.fill('input[name="LoginName"]', os.environ["ZOZO_LOGIN_ID"])
        page.fill('input[name="Password"]', os.environ["ZOZO_LOGIN_PASSWORD"])
        with page.expect_navigation(wait_until="domcontentloaded", timeout=30000):
            page.get_by_role("button", name="ログイン").first.click()


with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(locale="ja-JP", viewport={"width": 1440, "height": 1100},
                        http_credentials={"username": os.environ["ZOZO_BASIC_USER"],
                                          "password": os.environ["ZOZO_BASIC_PASSWORD"]},
                        accept_downloads=True)
    page = ctx.new_page()
    _login(page)
    # 検索確立
    page.goto(BASE + "AdReports.asp?c=Init", wait_until="domcontentloaded", timeout=45000)
    time.sleep(1)
    page.evaluate(r"""(d) => {
      const f=document.forms['form']||document.querySelector('form[action="AdReports.asp"]');
      if(!f) return;
      for(const n of ['TermFrom','TermTo']){const i=f.querySelector(`input[name="${n}"]`); if(i) i.value=d;}
      const cb=f.querySelector('input[name="DailyFlag"]'); if(cb) cb.checked=true;
      const sel=f.querySelector('select[name="ShopID"]'); if(sel) sel.value='-1';
    }""", D.replace("-","/"))
    with page.expect_navigation(wait_until="domcontentloaded", timeout=60000):
        page.locator('button[name="search"][value="search"]').first.click()
    time.sleep(2)

    print(f"=== {D} MONO-MART(1787) 4種類の応答 ===")
    for label, c, t in TYPES:
        url = f"{BASE}AdReports.asp?c={c}&type={t}&SearchShopID=1787&BeginDate={D}&EndDate={D}"
        r = ctx.request.get(url, timeout=120000, headers={"referer": BASE + "AdReports.asp"})
        body = r.body()
        ct = r.headers.get("content-type", "")
        disp = r.headers.get("content-disposition", "")
        head = body[:200].decode("cp932", "replace").replace("\n", " ").replace("\r", " ")
        print(f"\n[{label}] type={t}  status={r.status} ct='{ct[:40]}' disp='{disp[:40]}' bytes={len(body)}")
        print(f"   head: {head[:170]}")
    b.close()
