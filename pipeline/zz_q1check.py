from google.cloud import bigquery
c = bigquery.Client(project="mono-back-office-system")
for tbl in ["analytics_layer.inventory_snapshot","analytics_layer.stock_analysis","analytics_layer.product_master"]:
    try:
        t=c.get_table(tbl)
        cols=[f.name for f in t.schema]
        print(f"=== {tbl} ({t.num_rows:,}行) ===")
        print("  列:", ", ".join(cols))
        # 納品書/delivery/color_code 関連を抽出
        hit=[x for x in cols if any(k in x.lower() for k in ["delivery","note","納品","color_code","maker","arrival","invoice","denpyo"])]
        print("  関連列:", hit if hit else "（該当なし）")
    except Exception as e:
        print(f"=== {tbl} : 取得失敗 {e}")
    print()
# 日次在庫の保持範囲
for tbl,dt in [("analytics_layer.stock_analysis","snapshot_date"),("analytics_layer.inventory_snapshot","snapshot_date")]:
    try:
        r=list(c.query(f"SELECT MIN({dt}) mn, MAX({dt}) mx, COUNT(DISTINCT {dt}) d FROM `{tbl}`").result())[0]
        print(f"{tbl}: {dt} 範囲 {r.mn}〜{r.mx} (異なる日数={r.d})")
    except Exception as e:
        print(f"{tbl}: 日付確認失敗 {e}")
