# -*- coding: utf-8 -*-
"""
MMS 発注書一覧 取得 — 前回発注日・前回原価 用（品番×発注年月日×単価）。
取得元: 発注管理＞発注書一覧 (order_list.php)
  ① 検索(do=1) で対象期間の発注書を一覧化（itemTable_length 大）
  ② 全 order_id を収集
  ③ CSV出力API: POST do=10 + csv_order_ids[] + type=api → {key,filename,stamp}
  ④ get_file.php?key=&filename=&stamp= で CSV(cp932) ダウンロード
CSV列: 発注年月日, ブランド品番, CS品番, ZOZOカラー名, ZOZOサイズ名, 発注数量, 単価 …
出力 : gs://{bucket}/uploads/mms/orders/{date}/mms_orders.csv
        BigQuery analytics_layer.mms_orders (WRITE_TRUNCATE)
env  : LOGIN_USER, LOGIN_PASS, GOOGLE_APPLICATION_CREDENTIALS, [START_DATE=YYYY-MM-DD]
"""
import os, sys, csv, io, time, json
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlencode
from playwright.sync_api import sync_playwright
from google.cloud import storage, bigquery

PROJECT = "mono-back-office-system"
BUCKET = os.getenv("GCS_RAW_BUCKET", "mono-back-office-system-raw-data")
BASE = "https://mms.a-rg.work/"
LOGIN = BASE + "login.php"
ORDER = BASE + "order_list.php"
TODAY = date.today().isoformat()
START = os.getenv("START_DATE", (date.today() - timedelta(days=550)).isoformat())  # 既定 約18ヶ月
GCS_PATH = f"uploads/mms/orders/{TODAY}/mms_orders.csv"


def _login(ctx):
    pg = ctx.new_page()
    pg.goto(LOGIN, wait_until="domcontentloaded", timeout=40000)
    pg.locator("#user_id, input[name='user_id']").first.fill(os.environ["LOGIN_USER"], timeout=15000)
    pg.locator("#passwd, input[name='passwd']").first.fill(os.environ["LOGIN_PASS"], timeout=15000)
    pg.locator("button[type='submit'], input[type='submit']").first.click(timeout=10000)
    pg.wait_for_load_state("domcontentloaded"); time.sleep(3)
    if "login" in pg.url.lower():
        raise RuntimeError("MMS login failed")
    return pg


def fetch_csv_bytes() -> bytes:
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = b.new_context(locale="ja-JP", viewport={"width": 1440, "height": 1100})
        pg = _login(ctx)
        # ① 検索（発注年月日 START〜TODAY・大量表示）
        pg.goto(ORDER, wait_until="networkidle", timeout=40000); time.sleep(1)
        search = {"do": "1", "s_date": START, "e_date": TODAY, "schedule_s_date": "", "schedule_e_date": "",
                  "zozo_s_date": "", "zozo_e_date": "", "com": "", "order_no": "", "min_status": "",
                  "max_status": "", "tmp_price": "", "shop_id": "", "p_category": "", "item_cd": "",
                  "itemTable_length": "100000"}
        rs = ctx.request.post(ORDER, data=urlencode(search),
                              headers={"content-type": "application/x-www-form-urlencoded", "referer": ORDER},
                              timeout=120000)
        # 検索結果HTMLから order_id を収集
        import re
        ids = re.findall(r"name=\"data\[output_csv\]\[order_ids\]\[\]\"[^>]*value=\"(\d+)\"", rs.text())
        ids = list(dict.fromkeys(ids))
        print(f"対象発注書: {len(ids)} 件 (発注日 {START}〜{TODAY})")
        if not ids:
            raise RuntimeError("no orders found in window")
        # getFileUrl
        get_file_url = "//mms.a-rg.work/get_file.php"
        m = re.search(r"getFileUrl\s*=\s*['\"]([^'\"]+)['\"]", pg.content())
        if m:
            get_file_url = m.group(1)
        dl_base = ("https:" + get_file_url) if get_file_url.startswith("//") else get_file_url

        # ② CSV出力API（order_idは多すぎる場合チャンク分割）
        all_text = None
        CHUNK = 4000
        merged_lines = []
        header = None
        for i in range(0, len(ids), CHUNK):
            chunk = ids[i:i + CHUNK]
            fields = [("do", "10"), ("s_date", START), ("e_date", TODAY),
                      ("schedule_s_date", ""), ("schedule_e_date", ""), ("zozo_s_date", ""), ("zozo_e_date", ""),
                      ("com", ""), ("order_no", ""), ("min_status", ""), ("max_status", ""), ("tmp_price", ""),
                      ("shop_id", ""), ("p_category", ""), ("item_cd", ""), ("itemTable_length", "100000"),
                      ("type", "api")] + [("csv_order_ids[]", x) for x in chunk]
            jr = ctx.request.post(ORDER, data=urlencode(fields),
                                  headers={"content-type": "application/x-www-form-urlencoded", "referer": ORDER},
                                  timeout=120000)
            resp = json.loads(jr.text())
            data = resp.get("data")
            if isinstance(data, list):
                data = data[0] if data else {}
            if not isinstance(data, dict) or "key" not in data:
                print(f"  予期しない応答: {str(resp)[:200]}")
                continue
            dl_url = dl_base + "?" + urlencode({"key": data["key"], "filename": data["filename"], "stamp": data["stamp"]})
            d = ctx.request.get(dl_url, timeout=120000, headers={"referer": ORDER})
            lines = d.body().decode("cp932", "replace").splitlines()
            if not lines:
                continue
            if header is None:
                header = lines[0]
            merged_lines.extend(lines[1:])
            print(f"  chunk {i//CHUNK+1}: +{len(lines)-1} 行")
        b.close()
    if header is None:
        raise RuntimeError("no CSV rows")
    return ("\n".join([header, *merged_lines]) + "\n").encode("cp932", "replace")


def main() -> int:
    raw = fetch_csv_bytes()
    text = raw.decode("cp932", "replace")
    rows = list(csv.DictReader(io.StringIO(text)))
    recs = []
    for r in rows:
        od = (r.get("発注年月日") or "").strip()
        pc = (r.get("ブランド品番") or "").strip()
        if not od or not pc:
            continue
        def n(x):
            try:
                return float(str(x).replace(",", "")) if x not in (None, "") else None
            except Exception:
                return None
        recs.append({
            "order_date": od.replace("/", "-"),
            "product_code": pc,
            "sku_code": (r.get("CS品番") or "").strip(),
            "color_name": (r.get("ZOZOカラー名") or "").strip(),
            "size": (r.get("ZOZOサイズ名") or "").strip(),
            "order_qty": int(n(r.get("発注数量")) or 0),
            "unit_price": n(r.get("単価")),
            "order_no": (r.get("発注書No") or "").strip(),
            # 顧客要望2026: 発注先会社。自社(株式会社MONO-MART)の再納品等イレギュラーを
            #   前回発注日/前回原価の集計から除外するために使う。
            "supplier_company": (r.get("発注先会社") or "").strip(),
            "snapshot_date": TODAY,
        })
    if not recs:
        raise RuntimeError("no order rows parsed")

    storage.Client().bucket(BUCKET).blob(GCS_PATH).upload_from_string(raw, content_type="text/csv")
    bq = bigquery.Client(project=PROJECT)
    table = f"{PROJECT}.analytics_layer.mms_orders"
    schema = [
        bigquery.SchemaField("order_date", "DATE"),
        bigquery.SchemaField("product_code", "STRING"),
        bigquery.SchemaField("sku_code", "STRING"),
        bigquery.SchemaField("color_name", "STRING"),
        bigquery.SchemaField("size", "STRING"),
        bigquery.SchemaField("order_qty", "INTEGER"),
        bigquery.SchemaField("unit_price", "NUMERIC"),
        bigquery.SchemaField("order_no", "STRING"),
        bigquery.SchemaField("supplier_company", "STRING"),
        bigquery.SchemaField("snapshot_date", "DATE"),
    ]
    bq.load_table_from_json(recs, table,
        job_config=bigquery.LoadJobConfig(schema=schema, write_disposition="WRITE_TRUNCATE")).result()
    print(f"OK: {len(recs)} 明細 -> gs://{BUCKET}/{GCS_PATH} & BQ {table}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
