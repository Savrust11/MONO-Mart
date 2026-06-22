import sys
sys.path.insert(0, r"C:\Users\Administrator\Downloads\system\pipeline")
from google.cloud import bigquery, storage
from extractors.zozo_csv_extractor import ZOZOCsvExtractor
import logging; logging.disable(logging.INFO)
bq = bigquery.Client(project="mono-back-office-system")
gcs = storage.Client()
ext = ZOZOCsvExtractor()

print("=== ① 発送が『出荷日』で正しく日付展開されているか (月初に潰れていないか) ===")
for ym, folder in (("2024-07","2024-07-01"),("2024-08","2024-08-01")):
    r=list(bq.query(f"""SELECT COUNT(DISTINCT sale_date) days, MIN(sale_date) lo, MAX(sale_date) hi,
      COUNTIF(sales_quantity>0) qp, COUNT(*) n FROM `analytics_layer.sales_daily`
      WHERE source_file='shipped' AND FORMAT_DATE('%Y-%m',sale_date)='{ym}'""").result())[0]
    print(f"  {ym}: {r.days}日に分散 ({r.lo}..{r.hi})  出荷数>0={r.qp}/{r.n}")

print("\n=== ② GCS原本 vs BigQuery 突合 (発送 2ヶ月) ===")
for mfile in ("2024-08-01","2024-09-01"):
    blobs=list(gcs.list_blobs("mono-back-office-system-raw-data", prefix=f"uploads/zozo/shipped/{mfile}/"))
    src=[]
    for b in blobs:
        src += ext.parse_orders(b.download_as_bytes(), mfile, is_shipped=True)
    sn=len(src); sq=sum(r["sales_quantity"] for r in src)
    ym=mfile[:7]
    r=list(bq.query(f"""SELECT COUNT(*) n, SUM(sales_quantity) q FROM `analytics_layer.sales_daily`
      WHERE source_file='shipped' AND FORMAT_DATE('%Y-%m',sale_date)='{ym}'""").result())[0]
    ok = (sn==r.n and sq==r.q)
    print(f"  {ym}: GCS原本(行{sn:,} 出荷数{sq:,}) vs BQ(行{r.n:,} 出荷数{r.q:,})  {'✓一致' if ok else '✗不一致'}")
