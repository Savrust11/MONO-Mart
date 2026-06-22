from google.cloud import bigquery
c = bigquery.Client(project="mono-back-office-system")
# raw_layer のテーブル一覧
print("=== raw_layer テーブル ===")
try:
    for t in c.list_tables("raw_layer"):
        print("  ", t.table_id)
except Exception as e: print("  失敗", str(e)[:80])

# 商品マスタ/goods系の生テーブルの列に「カラー」「color」「コード」系があるか
print("\n=== 商品マスタ系 生テーブルの列（color/カラー/コード系） ===")
for tbl in ["raw_layer.product_master_raw","raw_layer.registered_products","raw_layer.goods_cs",
            "raw_layer.product_search","analytics_layer.product_master"]:
    try:
        t=c.get_table(tbl)
        cols=[f.name for f in t.schema]
        hit=[x for x in cols if any(k in x.lower() for k in ["color","colour","カラー","code","コード","maker","メーカー"])]
        print(f"  {tbl}: 色/コード系列 = {hit}")
    except Exception as e:
        print(f"  {tbl}: 無し")
