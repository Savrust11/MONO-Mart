"""経過係数（リリース経過日数カーブ）を構築（顧客・欠品補正#2）。

ブランド(parent_category)ごとに、過去1年の受注から「リリース後 d 日目の日販が、
定常日販の何倍か」を出す。7日実績が無い新商品の販売速度を推定するために使う。

定義:
  first_sale[product] = その品番の初回受注日
  d = sale_date - first_sale + 1   （リリース後 d 日目）
  daily_rate[brand][d] = 品番平均の「d 日目の日販」
  steady[brand]        = d∈[15,30] の平均日販（立ち上がりが落ち着いた定常）
  coefficient[brand][d]= daily_rate[brand][d] / steady[brand]   （定常=1.0 基準のカーブ）

使い方（order-plan 側）:
  新商品(経過 d 日, 累計販売 S)の定常日販推定 = S / Σ_{k=1..d} coefficient[brand][k]
"""
from google.cloud import bigquery

PROJECT = "mono-back-office-system"
A = f"{PROJECT}.analytics_layer"
MAXD = 30
bq = bigquery.Client(project=PROJECT)

bq.query(f"""
CREATE OR REPLACE TABLE `{A}.elapsed_coefficients` AS
WITH base AS (
  SELECT UPPER(TRIM(product_code)) pc, ANY_VALUE(parent_category) brand,
         MIN(sale_date) first_sale
  FROM `{A}.sales_daily`
  WHERE source_file='orders' AND parent_category IS NOT NULL AND parent_category!=''
    AND sale_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 400 DAY)
  GROUP BY pc),
day_sales AS (
  SELECT b.brand, b.pc,
         DATE_DIFF(s.sale_date, b.first_sale, DAY) + 1 AS d,
         SUM(s.sales_quantity) AS qty
  FROM `{A}.sales_daily` s
  JOIN base b ON UPPER(TRIM(s.product_code))=b.pc
  WHERE s.source_file='orders'
    AND DATE_DIFF(s.sale_date, b.first_sale, DAY) + 1 BETWEEN 1 AND {MAXD}
  GROUP BY 1,2,3),
rate AS (  -- ブランド×d の平均日販（品番をまたいで平均）
  SELECT brand, d, AVG(qty) daily_rate, COUNT(DISTINCT pc) n_pc
  FROM day_sales GROUP BY 1,2),
steady AS (  -- 立ち上がり後（15〜30日目）の定常日販。十分な品番数のブランドのみ。
  SELECT brand, AVG(daily_rate) base
  FROM rate WHERE d BETWEEN 15 AND {MAXD}
  GROUP BY brand HAVING SUM(n_pc) >= 20)
SELECT r.brand, r.d AS days_since_release,
       ROUND(SAFE_DIVIDE(r.daily_rate, s.base), 3) AS coefficient,
       r.n_pc, CURRENT_TIMESTAMP() AS updated_at
FROM rate r JOIN steady s USING(brand)
WHERE s.base > 0
ORDER BY brand, days_since_release
""").result()

r = list(bq.query(f"""SELECT COUNT(*) n, COUNT(DISTINCT brand) brands FROM `{A}.elapsed_coefficients`"""))[0]
print(f"built elapsed_coefficients: {r['n']}行 / {r['brands']}ブランド")
print("サンプル（立ち上がりカーブ・先頭ブランド）:")
for x in bq.query(f"""SELECT brand, days_since_release d, coefficient c FROM `{A}.elapsed_coefficients`
  WHERE brand=(SELECT brand FROM `{A}.elapsed_coefficients` ORDER BY brand LIMIT 1)
    AND days_since_release IN (1,2,3,5,7,14,30) ORDER BY d"""):
    print(f"  {x['brand']} 経過{x['d']:>2}日目: 係数={x['c']}")
