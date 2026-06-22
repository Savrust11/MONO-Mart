from google.cloud import bigquery
c = bigquery.Client(project="mono-back-office-system")
checks = [
  ("受注 orders", "analytics_layer.sales_daily", "sale_date", "source_file='orders'"),
  ("発送 shipped", "analytics_layer.sales_daily", "sale_date", "source_file='shipped'"),
  ("在庫分析 stock_analysis", "analytics_layer.stock_analysis", "snapshot_date", "1=1"),
  ("倉庫在庫 inventory", "analytics_layer.inventory_snapshot", "snapshot_date", "1=1"),
  ("予約 reservations", "analytics_layer.reservations", "reservation_date", "1=1"),
  ("入荷残 incoming", "analytics_layer.incoming_stock", "source_date", "1=1"),
]
print("ソース別 最新取得日（今日=2026-06-21、昨日=2026-06-20）")
for label, tbl, col, cond in checks:
    try:
        r=list(c.query(f"SELECT MAX({col}) mx FROM `{tbl}` WHERE {cond}").result())[0]
        print(f"  {label:<28} 最新={r.mx}")
    except Exception as e:
        print(f"  {label:<28} 失敗 {str(e)[:40]}")
