import time
from google.cloud import bigquery
c = bigquery.Client(project="mono-back-office-system")

top = list(c.query("""
SELECT product_code, SUM(sales_quantity) q
FROM `analytics_layer.sales_daily`
WHERE source_file='orders' AND sale_date BETWEEN '2026-05-01' AND '2026-05-31'
  AND product_code IS NOT NULL
GROUP BY product_code ORDER BY q DESC LIMIT 1""").result())[0]
PC = top.product_code
print(f"検証品番 = {PC} (2026-05 販売数={top.q})\n")

SQL = """
WITH sku_sales AS (
  SELECT product_code, sku_code, color_name, size,
    SUM(sales_quantity) AS qty,
    SUM(sales_amount)   AS revenue,
    SUM(proper_price * sales_quantity) AS list_amount
  FROM `analytics_layer.sales_daily`
  WHERE product_code = @pc AND source_file='orders'
    AND sale_date BETWEEN @sd AND @ed AND sales_quantity > 0
  GROUP BY product_code, sku_code, color_name, size
),
pf_cost AS (
  SELECT UPPER(TRIM(product_code)) j_pc, ANY_VALUE(cost_price) pf
  FROM `analytics_layer.pf_fee_master`
  WHERE snapshot_date=(SELECT MAX(snapshot_date) FROM `analytics_layer.pf_fee_master`)
    AND cost_price>0 GROUP BY j_pc
),
mms_cost AS (
  SELECT j_pc, j_col, j_sz, ARRAY_AGG(cost_price ORDER BY source_date DESC LIMIT 1)[OFFSET(0)] cp
  FROM (SELECT UPPER(TRIM(product_code)) j_pc, UPPER(TRIM(color_name)) j_col,
               UPPER(TRIM(size)) j_sz, cost_price, source_date
        FROM `analytics_layer.cost_master`
        WHERE product_code IS NOT NULL AND color_name IS NOT NULL AND size IS NOT NULL
          AND valid_to IS NULL)
  GROUP BY j_pc, j_col, j_sz
),
costed AS (
  SELECT s.*, COALESCE(pf.pf, mc.cp) AS cost
  FROM sku_sales s
  LEFT JOIN pf_cost pf ON pf.j_pc=UPPER(TRIM(s.product_code))
  LEFT JOIN mms_cost mc ON mc.j_pc=UPPER(TRIM(s.product_code))
    AND mc.j_col=UPPER(TRIM(s.color_name)) AND mc.j_sz=UPPER(TRIM(s.size))
)
SELECT
  SUM(qty) AS total_qty,
  ROUND(SAFE_DIVIDE(SUM(revenue),SUM(qty)),1) AS avg_price,
  ROUND((1-SAFE_DIVIDE(SUM(revenue),SUM(list_amount)))*100,1) AS discount_pct,
  ROUND(SAFE_DIVIDE(SUM(revenue)-SUM(cost*qty),SUM(revenue))*100,1) AS margin_pct,
  COUNT(*) AS sku_n, COUNTIF(cost IS NULL) AS cost_missing
FROM costed
"""
cfg = bigquery.QueryJobConfig(query_parameters=[
  bigquery.ScalarQueryParameter("pc","STRING",PC),
  bigquery.ScalarQueryParameter("sd","DATE","2026-05-01"),
  bigquery.ScalarQueryParameter("ed","DATE","2026-05-31"),
])
t0=time.time()
r=list(c.query(SQL,job_config=cfg).result())[0]
dt=time.time()-t0
print(f"=== 品番={PC} 期間=2026-05-01〜05-31 の実数 ===")
print(f"  合計販売数   : {r.total_qty}")
print(f"  平均売価(税抜): {r.avg_price} 円")
print(f"  値引率       : {r.discount_pct} %")
print(f"  粗利率       : {r.margin_pct} %")
print(f"  SKU数={r.sku_n}  原価欠落SKU={r.cost_missing}")
print(f"\n  クエリ所要時間: {dt:.2f} 秒")
