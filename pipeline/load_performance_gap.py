"""GCSにある performance(商品別実績) CSV を BigQuery(sales_daily) へロード。
取得は出来ているがロードが止まっていた欠損日を埋める用。upsert は (sale_date, source_file) 単位で安全。
Usage: python load_performance_gap.py [YYYY-MM-DD ...]
"""
import sys
from google.cloud import storage
from extractors.zozo_csv_extractor import ZOZOCsvExtractor
from loaders.bigquery_loader import BigQueryLoader

PROJECT = "mono-back-office-system"
BUCKET = "mono-back-office-system-raw-data"

DATES = sys.argv[1:] or ["2026-06-22", "2026-06-23", "2026-06-24", "2026-06-25", "2026-06-26"]

sc = storage.Client(project=PROJECT)
zc = ZOZOCsvExtractor()
bq = BigQueryLoader(project=PROJECT)

for d in DATES:
    blobs = [b for b in sc.bucket(BUCKET).list_blobs(prefix=f"uploads/zozo/performance/{d}/")
             if b.name.endswith((".tsv", ".csv"))]
    rows = []
    for b in blobs:
        rows.extend(zc.parse_performance(b.download_as_bytes(), d))
    if rows:
        bq.upsert_sales_daily(rows, d)
    print(f"{d}: blobs={len(blobs)} rows={len(rows)}")
print("done")
