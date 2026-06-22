from google.cloud import bigquery
c = bigquery.Client(project="mono-back-office-system")
print("=== analytics_layer.stock_analysis 最近の取込状況 ===")
rows=list(c.query("""
SELECT snapshot_date,
       COUNT(*) AS n,
       COUNTIF(favorites IS NOT NULL) AS fav_nn,
       COUNTIF(favorites > 0) AS fav_pos,
       COUNTIF(barcode IS NOT NULL) AS bc_nn,
       COUNTIF(arrival_date IS NOT NULL) AS arr_nn
FROM `analytics_layer.stock_analysis`
WHERE snapshot_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
GROUP BY snapshot_date ORDER BY snapshot_date DESC LIMIT 12
""").result())
if not rows: print("  (最近30日に在庫分析データなし)")
for r in rows:
    print(f"  {r.snapshot_date}: {r.n:,}行  favorites非NULL={r.fav_nn:,} (>0:{r.fav_pos:,})  barcode={r.bc_nn:,}  最終入荷日={r.arr_nn:,}")
