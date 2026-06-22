from google.cloud import bigquery
c = bigquery.Client(project="mono-back-office-system")
print("=== CLEsc1116/S10000 の受注行サンプル (orders) ===")
for r in c.query("""
SELECT sale_date, sales_quantity AS qty, sales_amount AS amt, unit_price AS up,
  proper_price AS pp, price_type, sale_type
FROM `analytics_layer.sales_daily`
WHERE product_code='CLEsc1116' AND sku_code='S10000' AND source_file='orders'
  AND sale_date BETWEEN DATE_SUB(DATE '2026-06-18', INTERVAL 30 DAY) AND '2026-06-18'
ORDER BY sale_date DESC LIMIT 15""").result():
    print(f"  {r.sale_date} 数量={r.qty} 金額={r.amt} 単価={r.up} 上代={r.pp} 価格Type={r.price_type} 販売Type={r.sale_type}")

print("\n=== 金額の分布 (この SKU) ===")
for r in c.query("""
SELECT CASE WHEN sales_amount=0 THEN '0円' WHEN sales_amount<500 THEN '1-499円'
            WHEN sales_amount<2000 THEN '500-1999円' ELSE '2000円+' END AS band,
       COUNT(*) AS n, SUM(sales_quantity) AS qty, ROUND(SUM(sales_amount)) AS rev
FROM `analytics_layer.sales_daily`
WHERE product_code='CLEsc1116' AND sku_code='S10000' AND source_file='orders'
  AND sale_date BETWEEN DATE_SUB(DATE '2026-06-18', INTERVAL 30 DAY) AND '2026-06-18'
GROUP BY band ORDER BY band""").result():
    print(f"  {r.band}: 行={r.n} 数量={r.qty} 売上={r.rev}")
