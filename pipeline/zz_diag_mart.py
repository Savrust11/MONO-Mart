from google.cloud import bigquery
c = bigquery.Client(project="mono-back-office-system")

print("=== mart 2026-06-18 全体 ===")
r=list(c.query("""SELECT COUNT(*) n, COUNTIF(favorites_total>0) favpos, COUNTIF(inventory>0) invpos
  FROM `mart_layer.order_analysis` WHERE analysis_date='2026-06-18'""").result())[0]
print(f"  行数{r.n:,}  お気に入り>0={r.favpos:,}  在庫>0={r.invpos:,}")

print("\n=== 画面の上位商品(CRITICAL)で favorites/inventory を確認 ===")
for sku,pc in (("S10000","CLEsc1116"),("M3","pa640"),("F8","bg566")):
    r=list(c.query(f"""SELECT favorites_total fav, inventory inv, sales_30d s30, order_urgency u
      FROM `mart_layer.order_analysis` WHERE analysis_date='2026-06-18' AND sku_code='{sku}' AND product_code='{pc}' LIMIT 1""").result())
    if r: print(f"  {pc}/{sku}: お気に入り={r[0].fav} 在庫={r[0].inv} 30日販売={r[0].s30} 緊急度={r[0].u}")
    else: print(f"  {pc}/{sku}: martに行なし")

print("\n=== 同じSKUが stock_analysis(お気に入りの元)に居るか ===")
for sku,pc in (("S10000","CLEsc1116"),("M3","pa640"),("F8","bg566")):
    r=list(c.query(f"""SELECT favorites fav, available_qty av FROM `analytics_layer.stock_analysis`
      WHERE snapshot_date='2026-06-18' AND sku_code='{sku}' AND product_code='{pc}' LIMIT 1""").result())
    if r: print(f"  {pc}/{sku}: stock_analysisに在り → お気に入り={r[0].fav} 販売可能数={r[0].av}")
    else: print(f"  {pc}/{sku}: stock_analysisに無し")

print("\n=== お気に入り>0 の商品は実在する（上位5件）===")
for r in c.query("""SELECT product_code, sku_code, favorites_total, sales_30d, inventory
  FROM `mart_layer.order_analysis` WHERE analysis_date='2026-06-18' AND favorites_total>0
  ORDER BY favorites_total DESC LIMIT 5""").result():
    print(f"  {r.product_code}/{r.sku_code}: お気に入り={r.favorites_total} 在庫={r.inventory} 30日販売={r.sales_30d}")
