from google.cloud import bigquery
c = bigquery.Client(project="mono-back-office-system")
print("=== sales_daily 生データ: CLEsc1116/S10000 直近30日 (source別) ===")
for r in c.query("""
SELECT source_file, COUNT(*) AS n, SUM(sales_quantity) AS qty, ROUND(SUM(sales_amount)) AS rev,
  ROUND(SUM(sales_amount)/NULLIF(SUM(sales_quantity),0),1) AS avg_price
FROM `analytics_layer.sales_daily`
WHERE product_code='CLEsc1116' AND sku_code='S10000'
  AND sale_date BETWEEN DATE_SUB(DATE '2026-06-18', INTERVAL 30 DAY) AND '2026-06-18'
GROUP BY source_file ORDER BY source_file""").result():
    print(f"  {r.source_file}: 行={r.n} 枚数={r.qty} 売上={r.rev} 平均単価={r.avg_price}")
