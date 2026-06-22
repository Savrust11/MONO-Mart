from google.cloud import bigquery
c = bigquery.Client(project="mono-back-office-system")
print("=== mart_layer.order_analysis の favorites_total (顧客が見る発注管理表の元) ===")
rows=list(c.query("""SELECT analysis_date, COUNT(*) n, COUNTIF(favorites_total>0) favpos, MAX(favorites_total) mx
  FROM `mart_layer.order_analysis` GROUP BY analysis_date ORDER BY analysis_date DESC LIMIT 6""").result())
if not rows: print("  (mart にデータなし)")
for r in rows:
    print(f"  {r.analysis_date}: {r.n:,}行  お気に入り>0={r.favpos:,}  最大={r.mx}")
