from google.cloud import bigquery
c = bigquery.Client(project="mono-back-office-system")
print("=== 6/18 取込確認 ===")
for sf in ("orders","shipped"):
    r=list(c.query(f"""SELECT COUNT(*) n FROM `analytics_layer.sales_daily` WHERE source_file='{sf}' AND sale_date='2026-06-18'""").result())[0]
    print(f"  {sf} 6/18: {r.n:,}")

print("\n=== shipped 件数差の調査: 日ごとの ショップ数 & 行数 ===")
for r in c.query("""SELECT FORMAT_DATE('%m-%d',sale_date) d, COUNT(DISTINCT shop_name) shops, COUNT(*) n,
  COUNT(DISTINCT product_code) prods
  FROM `analytics_layer.sales_daily` WHERE source_file='shipped' AND sale_date BETWEEN '2026-06-12' AND '2026-06-17'
  GROUP BY d ORDER BY d""").result():
    print(f"  {r.d}: ショップ{r.shops}  品番{r.prods:,}  行{r.n:,}")

print("\n=== shipped 6/13 (低) vs 6/16 (高) のショップ別件数 ===")
for d in ("2026-06-13","2026-06-16"):
    print(f"  [{d}]")
    for r in c.query(f"""SELECT shop_name, COUNT(*) n FROM `analytics_layer.sales_daily`
      WHERE source_file='shipped' AND sale_date='{d}' GROUP BY shop_name ORDER BY n DESC LIMIT 8""").result():
        print(f"     {r.shop_name}: {r.n:,}")
