# -*- coding: utf-8 -*-
"""
ZOZO カラーマスタ取得 — 画像URLの「カラーコード」用（色名→カラーID）。
取得元: サイト管理＞データ連携管理＞ZOZOマスタダウンロード＞カラー
        = MappingAdEd.asp?c=UpdateCommonMaster&IsMaster=2 （CSV添付・cp932・読み取りのみ）
列     : カラーカテゴリ, カラー名, カラーID, ショップ名
出力   : gs://{bucket}/uploads/zozo/color_master/{date}/color_master.csv
         BigQuery analytics_layer.color_master (WRITE_TRUNCATE)
実行   : python fetch_color_master.py
        （env: ZOZO_BASIC_USER/PASSWORD, ZOZO_LOGIN_ID/PASSWORD, GOOGLE_APPLICATION_CREDENTIALS）
"""
import os, sys, csv, io, time
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from playwright.sync_api import sync_playwright
from google.cloud import storage, bigquery
from zozo_scraper import ZOZOScraper, BASE_URL

PROJECT = "mono-back-office-system"
BUCKET = os.getenv("GCS_RAW_BUCKET", "mono-back-office-system-raw-data")
TARGET = os.getenv("TARGET_DATE") or date.today().isoformat()
GCS_PATH = f"uploads/zozo/color_master/{TARGET}/color_master.csv"
COLOR_URL = BASE_URL + "MappingAdEd.asp?c=UpdateCommonMaster&IsMaster=2"


def fetch_csv() -> bytes:
    s = ZOZOScraper(
        basic_user=os.environ["ZOZO_BASIC_USER"], basic_pw=os.environ["ZOZO_BASIC_PASSWORD"],
        login_id=os.environ["ZOZO_LOGIN_ID"], password=os.environ["ZOZO_LOGIN_PASSWORD"], headless=True)
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=[
            "--no-sandbox", "--disable-blink-features=AutomationControlled"])
        ctx = s._new_context(b); page = ctx.new_page(); s._login(page); time.sleep(2)
        page.goto(BASE_URL + "MappingAdEd.asp?c=Init", wait_until="networkidle", timeout=40000); time.sleep(1)
        r = ctx.request.get(COLOR_URL, timeout=60000, headers={"referer": BASE_URL + "MappingAdEd.asp?c=Init"})
        body = r.body()
        b.close()
    if r.status != 200 or len(body) < 100:
        raise RuntimeError(f"color master download failed: status={r.status} bytes={len(body)}")
    return body


def main() -> int:
    body = fetch_csv()
    text = body.decode("cp932")
    rows = list(csv.DictReader(io.StringIO(text)))
    recs = []
    for row in rows:
        nm = (row.get("カラー名") or "").strip()
        cid = (row.get("カラーID") or "").strip()
        if nm and cid:
            recs.append({"color_category": (row.get("カラーカテゴリ") or "").strip(),
                         "color_name": nm, "color_id": cid,
                         "shop_name": (row.get("ショップ名") or "").strip(),
                         "snapshot_date": TARGET})
    if not recs:
        raise RuntimeError("no color rows parsed")

    # GCS（生CSV保存）
    storage.Client().bucket(BUCKET).blob(GCS_PATH).upload_from_string(body, content_type="text/csv")

    # BigQuery（洗い替え）
    bq = bigquery.Client(project=PROJECT)
    table = f"{PROJECT}.analytics_layer.color_master"
    schema = [
        bigquery.SchemaField("color_category", "STRING"),
        bigquery.SchemaField("color_name", "STRING"),
        bigquery.SchemaField("color_id", "STRING"),
        bigquery.SchemaField("shop_name", "STRING"),
        bigquery.SchemaField("snapshot_date", "DATE"),
    ]
    job = bq.load_table_from_json(
        recs, table,
        job_config=bigquery.LoadJobConfig(schema=schema, write_disposition="WRITE_TRUNCATE"))
    job.result()
    print(f"OK: {len(recs)} colors -> gs://{BUCKET}/{GCS_PATH} & BQ {table}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
