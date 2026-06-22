from google.cloud import bigquery
c = bigquery.Client(project="mono-back-office-system")
r = list(c.query("""SELECT product_code, SUM(sales_quantity) q
FROM `analytics_layer.sales_daily`
WHERE source_file='orders' AND sale_date BETWEEN '2026-04-01' AND '2026-04-30'
  AND product_code!='sc1032' AND product_code IS NOT NULL
GROUP BY product_code ORDER BY q DESC LIMIT 1""").result())[0]
print(r.product_code)
