from google.cloud import bigquery
c = bigquery.Client(project="mono-back-office-system")
for label, tbl, col, cond in [
  ("受注","analytics_layer.sales_daily","sale_date","source_file='orders'"),
  ("発送","analytics_layer.sales_daily","sale_date","source_file='shipped'"),
  ("在庫分析","analytics_layer.stock_analysis","snapshot_date","1=1"),
  ("倉庫在庫","analytics_layer.inventory_snapshot","snapshot_date","1=1"),
  ("予約","analytics_layer.reservations","reservation_date","1=1"),
]:
    r=list(c.query(f"SELECT MAX({col}) mx FROM `{tbl}` WHERE {cond}").result())[0]
    print(f"  {label:<8} 最新={r.mx}")
