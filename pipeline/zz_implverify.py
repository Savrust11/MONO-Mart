from google.cloud import bigquery
c = bigquery.Client(project="mono-back-office-system")

print("=== sales_daily: sc1032 2026-05 のアクセス系合計（CVR/お気に率用）===")
r=list(c.query("""SELECT SUM(unique_visitors) uu, SUM(sales_quantity) chumon,
  SUM(buyers_total) buyers, SUM(favorites) fav
  FROM `analytics_layer.sales_daily`
  WHERE product_code='sc1032' AND sale_date BETWEEN '2026-05-01' AND '2026-05-31'""").result())[0]
print(f"  UU={r.uu} 注文数={r.chumon} buyers_total={r.buyers} favorites={r.fav}")
print(f"  → CVR候補: 注文数/UU={round(r.chumon/r.uu*100,1)}%  buyers/UU={round(r.buyers/r.uu*100,1)}%")
print(f"  → お気に率: favorites/UU={round(r.fav/r.uu*100,1)}%")

print("\n=== coupon_exclusion スキーマ＋サンプル ===")
t=c.get_table("analytics_layer.coupon_exclusion")
print("  列:", ", ".join(f.name for f in t.schema), f" ({t.num_rows}行)")
for row in c.query("SELECT * FROM `analytics_layer.coupon_exclusion` LIMIT 2").result():
    print("  ", {k:str(v)[:24] for k,v in dict(row).items()})

print("\n=== sitateru: 前回原価/日付の候補（MONO-MART品番のサンプル）===")
for row in c.query("""SELECT product_code, snapshot_date, actual_cost, confirmed_wholesale_price,
  proposed_wholesale_price, confirmed_delivery_date, planned_delivery_date, total_order_qty
  FROM `analytics_layer.sitateru_item_master`
  WHERE shop_name='MONO-MART' AND actual_cost IS NOT NULL ORDER BY snapshot_date DESC LIMIT 3""").result():
    print(f"  {row.product_code} snap={row.snapshot_date} actual_cost={row.actual_cost} conf_ws={row.confirmed_wholesale_price} conf_deliv={row.confirmed_delivery_date} order_qty={row.total_order_qty}")
