import sys
sys.path.insert(0, r"C:\Users\Administrator\Downloads\system\pipeline")
from google.cloud import storage, bigquery
from extractors.zozo_csv_extractor import ZOZOCsvExtractor
from loaders.bigquery_loader import BigQueryLoader
import logging; logging.disable(logging.INFO)
ext = ZOZOCsvExtractor()
bq = BigQueryLoader(project="mono-back-office-system")
gcs = storage.Client()
# show available methods to pick the right upsert
print("upsert methods:", [m for m in dir(bq) if "stock" in m.lower() or "analysis" in m.lower()])
rows=[]
for b in gcs.list_blobs("mono-back-office-system-raw-data", prefix="uploads/zozo/stock_analysis/2026-06-18/"):
    rows += ext.parse_inventory_analysis(b.download_as_bytes(), "2026-06-18")
print(f"parsed {len(rows)} rows; sample favorites:", [r.get("favorites") for r in rows[:5]])
bq.upsert_stock_analysis(rows, "2026-06-18")
print("upserted")
c = bigquery.Client(project="mono-back-office-system")
r=list(c.query("""SELECT COUNT(*) n, COUNTIF(favorites IS NOT NULL) fav, COUNTIF(favorites>0) favpos,
  COUNTIF(barcode IS NOT NULL) bc, COUNTIF(arrival_date IS NOT NULL) arr
  FROM `analytics_layer.stock_analysis` WHERE snapshot_date='2026-06-18'""").result())[0]
print(f"BigQuery 2026-06-18: {r.n} rows  favorites非NULL={r.fav}(>0:{r.favpos})  barcode={r.bc}  最終入荷日={r.arr}")
