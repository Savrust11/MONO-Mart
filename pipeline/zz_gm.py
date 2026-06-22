from google.cloud import bigquery
c = bigquery.Client(project="mono-back-office-system")
print("=== 粗利率が大きくマイナスの行 (原価 vs 売価) ===")
for r in c.query("""
SELECT product_code, sku_code, cost_price, proper_price, selling_price,
  period_revenue,
  ROUND(SAFE_DIVIDE(period_total_cost, NULLIF(cost_price,0))) AS units_used,
  ROUND(SAFE_DIVIDE(period_revenue, NULLIF(SAFE_DIVIDE(period_total_cost,NULLIF(cost_price,0)),0)),1) AS avg_price,
  ROUND(period_total_cost) AS tot_cost, ROUND(gross_margin_pct,1) AS gm
FROM `mart_layer.order_analysis`
WHERE analysis_date='2026-06-18' AND gross_margin_pct < -100
ORDER BY gross_margin_pct ASC LIMIT 8""").result():
    print(f"  {r.product_code}/{r.sku_code}: 原価={r.cost_price} 上代={r.proper_price} 売上={r.period_revenue} 枚数={r.units_used} 平均売価={r.avg_price} 粗利率={r.gm}%")

r=list(c.query("""SELECT COUNT(*) n, COUNTIF(gross_margin_pct<0) neg, COUNTIF(gross_margin_pct< -100) ext
  FROM `mart_layer.order_analysis` WHERE analysis_date='2026-06-18'""").result())[0]
print(f"\n全{r.n}行  粗利率<0={r.neg}  粗利率<-100%={r.ext}")
