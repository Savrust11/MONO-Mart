from google.cloud import bigquery
c = bigquery.Client(project="mono-back-office-system")
def show(tbl):
    try:
        t=c.get_table(tbl); print(f"\n=== {tbl} ({t.num_rows:,}行) ===")
        print("  列:", ", ".join(f.name for f in t.schema))
    except Exception as e:
        print(f"\n=== {tbl}: 無し ({str(e)[:50]})")

# 1) 前回発注/原価の候補ソース
show("analytics_layer.sitateru_item_master")
show("analytics_layer.incoming_stock")
# 2) CVR/お気に率の候補（商品別実績＝アクセス系）
show("analytics_layer.access_log_daily")
# 3) 画像カラーコードの候補（マスタの色コード系）
show("analytics_layer.product_master")

print("\n=== sitateru サンプル（原価/発注日があるか）===")
try:
    for r in c.query("SELECT * FROM `analytics_layer.sitateru_item_master` LIMIT 2").result():
        d=dict(r); print("  ", {k:str(v)[:30] for k,v in list(d.items())[:14]})
except Exception as e: print("  失敗", str(e)[:80])

print("\n=== sales_daily の アクセス/受注点数/お気に入り 系の値（非ゼロがあるか）===")
try:
    r=list(c.query("""SELECT COUNTIF(unique_visitors>0) uu, COUNTIF(buyers_total>0) buyers,
      COUNTIF(favorites>0) fav, COUNTIF(cart_adds>0) cart
      FROM `analytics_layer.sales_daily` WHERE sale_date BETWEEN '2026-05-01' AND '2026-05-31'""").result())[0]
    print(f"  UU>0={r.uu}  buyers_total>0={r.buyers}  favorites>0={r.fav}  cart>0={r.cart}")
except Exception as e: print("  失敗", str(e)[:80])
