from google.cloud import bigquery
c = bigquery.Client(project="mono-back-office-system")
t = c.get_table("analytics_layer.sales_daily")
print("=== sales_daily 列 ===")
for f in t.schema:
    print(f"  {f.name}: {f.field_type}")
