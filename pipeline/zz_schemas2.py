from google.cloud import bigquery
c = bigquery.Client(project="mono-back-office-system")
import re
def show(tbl):
    try:
        t=c.get_table(tbl)
        print(f"=== {tbl} ({t.num_rows:,}行) ===")
        print("  ", ", ".join(f.name for f in t.schema))
    except Exception as e:
        print(f"=== {tbl} : 無し/失敗 ({str(e)[:60]})")
for t in ["analytics_layer.reservations","analytics_layer.incoming_stock",
          "analytics_layer.product_reviews","analytics_layer.reviews",
          "analytics_layer.product_master"]:
    show(t)
# datasetのテーブル一覧（reviews系を探す）
print("\n=== analytics_layer テーブル一覧 ===")
for t in c.list_tables("analytics_layer"):
    print("  ", t.table_id)
