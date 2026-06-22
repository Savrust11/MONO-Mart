# -*- coding: utf-8 -*-
"""読み取りのみ：getFileUrl特定 → POST(do=10)→JSON→GET(key/filename/stamp) でCSV取得・列確認。"""
import os, time, re, json
from pathlib import Path
from urllib.parse import urlencode
from playwright.sync_api import sync_playwright

SESS = Path(__file__).resolve().parent / "sessions"
BASE = "https://mms.a-rg.work/"
LOGIN = BASE + "login.php"
ORDER = BASE + "order_list.php"


def login(ctx):
    pg = ctx.new_page()
    pg.goto(LOGIN, wait_until="domcontentloaded", timeout=40000)
    pg.locator("#user_id, input[name='user_id']").first.fill(os.environ["LOGIN_USER"], timeout=15000)
    pg.locator("#passwd, input[name='passwd']").first.fill(os.environ["LOGIN_PASS"], timeout=15000)
    pg.locator("button[type='submit'], input[type='submit']").first.click(timeout=10000)
    pg.wait_for_load_state("domcontentloaded"); time.sleep(3)
    return pg


with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=["--no-sandbox"])
    ctx = b.new_context(locale="ja-JP", viewport={"width": 1440, "height": 1100})
    pg = login(ctx)
    pg.goto(ORDER, wait_until="networkidle", timeout=40000)
    time.sleep(2)

    # getFileUrl の値
    inl = pg.evaluate(r"""() => [...document.querySelectorAll('script:not([src])')].map(s=>s.textContent).join('\n')""")
    m = re.search(r"getFileUrl\s*=\s*['\"]([^'\"]+)['\"]", inl)
    get_file_url = m.group(1) if m else None
    print("getFileUrl =", get_file_url)

    # 先頭2件の order_id
    ids = pg.evaluate(r"""() => [...document.querySelectorAll("input[name='data[output_csv][order_ids][]']")].slice(0,2).map(e=>e.value)""")
    print("order_ids:", ids)

    # POST do=10 ... type=api
    fields = [("do","10"),("s_date","2020-01-01"),("e_date","2026-06-26"),
              ("schedule_s_date",""),("schedule_e_date",""),("zozo_s_date",""),("zozo_e_date",""),
              ("com",""),("order_no",""),("min_status",""),("max_status",""),("tmp_price",""),
              ("shop_id",""),("p_category",""),("item_cd",""),("itemTable_length","50"),("type","api")]
    for oid in ids:
        fields.append(("csv_order_ids[]", oid))
    body = urlencode(fields)
    r = ctx.request.post(ORDER, data=body,
                         headers={"content-type":"application/x-www-form-urlencoded","referer":ORDER}, timeout=60000)
    print("POST status:", r.status, "->", r.text()[:160])
    data = json.loads(r.text()).get("data", {})

    # GET getFileUrl?key=..&filename=..&stamp=..
    if get_file_url and data:
        if get_file_url.startswith("//"):
            dl_base = "https:" + get_file_url
        elif get_file_url.startswith("http"):
            dl_base = get_file_url
        else:
            dl_base = BASE + get_file_url.lstrip("/")
        dl_url = dl_base + "?" + urlencode(
            {"key": data["key"], "filename": data["filename"], "stamp": data["stamp"]})
        print("\nDL URL:", dl_url[:140])
        d = ctx.request.get(dl_url, timeout=60000, headers={"referer": ORDER})
        print("DL status:", d.status, "ct:", d.headers.get("content-type"), "disp:", d.headers.get("content-disposition"))
        raw = d.body(); print("bytes:", len(raw))
        for enc in ("cp932","utf-8-sig"):
            try:
                txt = raw.decode(enc); print(f"\n=== enc={enc} 先頭6行 ===")
                for line in txt.splitlines()[:6]: print("  ", line[:180])
                break
            except UnicodeDecodeError: continue
    b.close()
