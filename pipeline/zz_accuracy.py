import sys
sys.path.insert(0, r"C:\Users\Administrator\Downloads\system\pipeline")
from google.cloud import bigquery, storage
from extractors.zozo_csv_extractor import ZOZOCsvExtractor
import logging; logging.disable(logging.INFO)

bq = bigquery.Client(project="mono-back-office-system")
gcs = storage.Client()
ext = ZOZOCsvExtractor()

print("=== 1) 取込済み3ヶ月の品質サマリ ===")
q = """
SELECT FORMAT_DATE('%Y-%m', sale_date) AS ym, COUNT(*) AS n,
  COUNT(DISTINCT sale_date) AS days, COUNT(DISTINCT sku_code) AS skus,
  COUNTIF(sku_code IS NULL) AS sku_null,
  COUNTIF(product_code IS NULL) AS pc_null,
  COUNTIF(sales_quantity IS NULL OR sales_quantity=0) AS qty_zero,
  SUM(sales_quantity) AS tot_qty, ROUND(SUM(sales_amount)) AS tot_amt
FROM `analytics_layer.sales_daily`
WHERE source_file='orders' AND sale_date BETWEEN '2024-07-01' AND '2024-09-30'
GROUP BY ym ORDER BY ym
"""
for r in bq.query(q).result():
    print(f"  {r.ym}: {r.n:,}行 {r.days}日 SKU{r.skus:,}  sku_null={r.sku_null} pc_null={r.pc_null} qty0={r.qty_zero}  Σqty={r.tot_qty:,} Σ金額={r.tot_amt:,.0f}")

print("\n=== 2) GCS原本 vs BigQuery 突合 (3日分) ===")
for day in ("2024-07-01","2024-08-15","2024-09-30"):
    # GCS原本をパース
    blobs = list(gcs.list_blobs("mono-back-office-system-raw-data", prefix=f"uploads/zozo/orders/{day}/"))
    src_rows=[]
    for b in blobs:
        src_rows += ext.parse_orders(b.download_as_bytes(), day)
    src_n=len(src_rows); src_qty=sum(r["sales_quantity"] for r in src_rows)
    src_amt=round(sum(r["sales_amount"] for r in src_rows))
    # BigQuery
    r = list(bq.query(f"""SELECT COUNT(*) n, SUM(sales_quantity) q, ROUND(SUM(sales_amount)) a
      FROM `analytics_layer.sales_daily` WHERE source_file='orders' AND sale_date=DATE '{day}'""").result())[0]
    ok = (src_n==r.n and src_qty==r.q and src_amt==round(r.a))
    print(f"  {day}: GCS(行{src_n:,} qty{src_qty:,} 金額{src_amt:,.0f}) vs BQ(行{r.n:,} qty{r.q:,} 金額{r.a:,.0f})  {'✓一致' if ok else '✗不一致'}")
