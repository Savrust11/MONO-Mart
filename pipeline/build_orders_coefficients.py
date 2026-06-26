"""受注実績ベースの52週季節係数（顧客#14・Option A）。

過去2年の受注(sales_daily)を gender×商品タイプ子×ISO週で集計し、
全52週ぶんの係数を作る（販売ゼロの週も実数0として明示＝空欄なし）。
平均週=1.0 になるよう「合計÷52」を分母にする（正しい季節指数）。
"""
from google.cloud import bigquery

PROJECT = "mono-back-office-system"
A = f"{PROJECT}.analytics_layer"
bq = bigquery.Client(project=PROJECT)

bq.query(f"""
CREATE OR REPLACE TABLE `{A}.seasonal_coefficients` AS
WITH pm AS (
  SELECT UPPER(TRIM(product_code)) pc, ANY_VALUE(gender) gender, ANY_VALUE(child_item_type) ct
  FROM `{A}.product_master`
  WHERE gender IS NOT NULL AND gender!='' AND child_item_type IS NOT NULL AND child_item_type!='' GROUP BY pc),
wk AS (
  SELECT pm.gender, pm.ct AS child_item_type, EXTRACT(ISOWEEK FROM s.sale_date) AS week_number, SUM(s.sales_quantity) AS week_qty
  FROM `{A}.sales_daily` s JOIN pm ON UPPER(TRIM(s.product_code))=pm.pc
  WHERE s.source_file='orders' GROUP BY 1,2,3),
cat AS (
  -- 平均週=1.0 になるよう「年間合計÷52」を基準に。十分な実績がある分類のみ。
  SELECT gender, child_item_type, SUM(week_qty)/52.0 AS base FROM wk GROUP BY 1,2
  HAVING SUM(week_qty) >= 1000 AND COUNT(*) >= 26),
grid AS (
  SELECT c.gender, c.child_item_type, w AS week_number, c.base
  FROM cat c CROSS JOIN UNNEST(GENERATE_ARRAY(1,52)) w)
SELECT g.gender, g.child_item_type, g.week_number,
       ROUND(SAFE_DIVIDE(COALESCE(wk.week_qty,0), g.base),3) AS coefficient,
       COALESCE(wk.week_qty,0) AS week_qty, CURRENT_TIMESTAMP() AS updated_at
FROM grid g
LEFT JOIN wk ON wk.gender=g.gender AND wk.child_item_type=g.child_item_type AND wk.week_number=g.week_number
ORDER BY gender, child_item_type, week_number
""").result()

r = list(bq.query(f"""SELECT COUNT(*) n, COUNT(DISTINCT CONCAT(gender,child_item_type)) cats,
  COUNTIF(coefficient IS NULL) nulls, ROUND(AVG(coefficient),3) avg_c FROM `{A}.seasonal_coefficients`"""))[0]
print(f"built seasonal_coefficients (受注実績ベース): {r['n']}行 / {r['cats']}分類 / NULL={r['nulls']} / 平均係数={r['avg_c']}")
