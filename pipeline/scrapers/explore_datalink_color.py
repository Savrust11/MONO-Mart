# -*- coding: utf-8 -*-
"""検証：カラーマスタDL → 商品の色名にカラーIDを当て → 画像URLが実際に通るか確認。"""
import os, sys, time, csv, io, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from playwright.sync_api import sync_playwright
from google.cloud import bigquery
from zozo_scraper import ZOZOScraper, BASE_URL

COLOR_URL = BASE_URL + "MappingAdEd.asp?c=UpdateCommonMaster&IsMaster=2"
s = ZOZOScraper(basic_user=os.environ["ZOZO_BASIC_USER"], basic_pw=os.environ["ZOZO_BASIC_PASSWORD"],
    login_id=os.environ["ZOZO_LOGIN_ID"], password=os.environ["ZOZO_LOGIN_PASSWORD"], headless=True)

# 1) カラーマスタDL
with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=["--no-sandbox","--disable-blink-features=AutomationControlled"])
    ctx = s._new_context(b); page = ctx.new_page(); s._login(page); time.sleep(2)
    page.goto(BASE_URL + "MappingAdEd.asp?c=Init", wait_until="networkidle", timeout=40000); time.sleep(1)
    body = ctx.request.get(COLOR_URL, timeout=60000, headers={"referer": BASE_URL+"MappingAdEd.asp?c=Init"}).body()
    b.close()
text = body.decode("cp932")
rdr = csv.DictReader(io.StringIO(text))
name2id = {}
for row in rdr:
    nm = (row.get("カラー名") or "").strip()
    cid = (row.get("カラーID") or "").strip()
    if nm and cid: name2id[nm] = cid
print(f"カラーマスタ: {len(name2id)} 色")

# 2) sc1032 の色名と item_code
c = bigquery.Client(project="mono-back-office-system")
rows = list(c.query("""SELECT DISTINCT color_name, ANY_VALUE(item_code) ic
  FROM `analytics_layer.product_master` WHERE UPPER(TRIM(product_code))='SC1032' AND color_name IS NOT NULL
  GROUP BY color_name""").result())
item_code = rows[0].ic
print(f"sc1032 item_code={item_code}, 色数={len(rows)}\n")

def img_ok(ic, cid):
    url=f"https://o.imgz.jp/{ic[-3:]}/{ic}/{ic}b_{cid}_d.jpg"
    try:
        r=urllib.request.urlopen(urllib.request.Request(url, method="HEAD", headers={"User-Agent":"Mozilla/5.0"}), timeout=8)
        return "OK" if (r.status==200 and "image" in r.headers.get("Content-Type","")) else "x"
    except Exception: return "404"

print("商品色名 → マスタ照合 → カラーID → 画像")
def norm(x): return x.replace("系","").strip()
norm_map = {norm(k):v for k,v in name2id.items()}
for r in rows:
    cn = r.color_name
    cid = name2id.get(cn) or name2id.get(norm(cn)) or norm_map.get(norm(cn))
    if cid:
        print(f"  {cn:<16} → ID={cid:<5} 画像={img_ok(item_code, cid)}")
    else:
        print(f"  {cn:<16} → マスタに一致なし")
