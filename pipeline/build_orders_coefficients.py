"""受注実績ベースの52週季節係数（顧客#14・Option A ＋ 対策A/B/C）。

過去2年の受注(sales_daily)を gender×商品タイプ子×ISO週で集計し、全52週ぶんの係数を作る。

2本立て（対策A）:
  - coefficient_raw … 生の実数（画面ヒートマップ表示用。実績どおり）
  - coefficient     … 補正後（3週移動平均→平均1.0に再正規化→[0.2,3.0]でクリップ）
                      = forecast(05_forecast.sql) が直接読む列。暴れ・欠品ループを防ぐ。
ニッチ補完（対策B）:
  - 子カテゴリの実績が薄く資格未満なら、親カテゴリ(parent_item_type)の季節カーブを継承。
  - coef_source = 'child' | 'parent' で由来を明示。
定期更新（対策C）:
  - 毎月1日 cron で再実行（受注が貯まるほど精度向上）。週次の first_seller cron とは別物（上書き競合なし）。
"""
from google.cloud import bigquery

PROJECT = "mono-back-office-system"
A = f"{PROJECT}.analytics_layer"
bq = bigquery.Client(project=PROJECT)

bq.query(f"""
CREATE OR REPLACE TABLE `{A}.seasonal_coefficients` AS
WITH pm AS (
  SELECT UPPER(TRIM(product_code)) pc, ANY_VALUE(gender) gender,
         ANY_VALUE(child_item_type) ct, ANY_VALUE(parent_item_type) pt
  FROM `{A}.product_master`
  WHERE gender IN ('MEN','WOMEN') AND child_item_type IS NOT NULL AND child_item_type!=''
  GROUP BY pc),
-- 子カテゴリ × ISO週（過去2年の受注を合算）
wk AS (
  SELECT pm.gender, pm.ct AS child_item_type, ANY_VALUE(pm.pt) AS parent_item_type,
         EXTRACT(ISOWEEK FROM s.sale_date) AS week_number, SUM(s.sales_quantity) AS week_qty
  FROM `{A}.sales_daily` s JOIN pm ON UPPER(TRIM(s.product_code))=pm.pc
  WHERE s.source_file='orders' AND EXTRACT(ISOWEEK FROM s.sale_date) BETWEEN 1 AND 52
  GROUP BY 1, 2, 4),
child_cat AS (
  SELECT gender, child_item_type, ANY_VALUE(parent_item_type) parent_item_type,
         SUM(week_qty)/52.0 AS base, SUM(week_qty) tot, COUNT(*) wks
  FROM wk GROUP BY 1, 2),
-- 親カテゴリ × ISO週（全子を合算）
pwk AS (
  SELECT gender, parent_item_type, week_number, SUM(week_qty) AS week_qty
  FROM wk GROUP BY 1, 2, 3),
parent_cat AS (
  SELECT gender, parent_item_type, SUM(week_qty)/52.0 AS base, SUM(week_qty) tot, COUNT(*) wks
  FROM pwk GROUP BY 1, 2),
-- 出力対象 = 子で資格あり OR 親で資格あり（対策B: 親フォールバック）
out_cat AS (
  SELECT c.gender, c.child_item_type, c.parent_item_type,
         (c.tot >= 1000 AND c.wks >= 26) AS child_qualifies
  FROM child_cat c
  WHERE (c.tot >= 1000 AND c.wks >= 26)
     OR EXISTS (SELECT 1 FROM parent_cat p
                WHERE p.gender=c.gender AND p.parent_item_type=c.parent_item_type
                  AND p.tot >= 1000 AND p.wks >= 26)),
grid AS (
  SELECT o.gender, o.child_item_type, o.parent_item_type, o.child_qualifies, w AS week_number
  FROM out_cat o CROSS JOIN UNNEST(GENERATE_ARRAY(1, 52)) w),
-- 生係数: 子が資格ありなら子カーブ、なければ親カーブを継承
raw AS (
  SELECT g.gender, g.child_item_type, g.week_number,
         IF(g.child_qualifies, 'child', 'parent') AS coef_source,
         IF(g.child_qualifies,
            SAFE_DIVIDE(COALESCE(cw.week_qty, 0), cc.base),
            SAFE_DIVIDE(COALESCE(pw.week_qty, 0), pc.base)) AS coefficient_raw,
         IF(g.child_qualifies, COALESCE(cw.week_qty, 0), COALESCE(pw.week_qty, 0)) AS week_qty
  FROM grid g
  LEFT JOIN child_cat cc ON cc.gender=g.gender AND cc.child_item_type=g.child_item_type
  LEFT JOIN wk cw ON cw.gender=g.gender AND cw.child_item_type=g.child_item_type AND cw.week_number=g.week_number
  LEFT JOIN parent_cat pc ON pc.gender=g.gender AND pc.parent_item_type=g.parent_item_type
  LEFT JOIN pwk pw ON pw.gender=g.gender AND pw.parent_item_type=g.parent_item_type AND pw.week_number=g.week_number),
-- 対策A-1: 3週移動平均（W52↔W1 を環状でつなぐ）
ma AS (
  SELECT a.gender, a.child_item_type, a.week_number, AVG(b.coefficient_raw) AS m3
  FROM raw a JOIN raw b
    ON a.gender=b.gender AND a.child_item_type=b.child_item_type
   AND MOD(b.week_number - a.week_number + 52, 52) IN (0, 1, 51)
  GROUP BY 1, 2, 3),
-- 対策A-2: 平均1.0に再正規化（季節指数として不偏に）
nrm AS (SELECT gender, child_item_type, AVG(m3) AS mu FROM ma GROUP BY 1, 2)
SELECT r.gender, r.child_item_type, r.week_number,
       -- coefficient = 補正後（forecast が読む安全値）: 再正規化 → [0.2,3.0] でクリップ
       ROUND(LEAST(3.0, GREATEST(0.2, SAFE_DIVIDE(ma.m3, nrm.mu))), 3) AS coefficient,
       ROUND(r.coefficient_raw, 3) AS coefficient_raw,   -- 生の実数（画面表示用）
       r.coef_source, r.week_qty, CURRENT_TIMESTAMP() AS updated_at
FROM raw r
JOIN ma  USING (gender, child_item_type, week_number)
JOIN nrm USING (gender, child_item_type)
ORDER BY gender, child_item_type, week_number
""").result()

r = list(bq.query(f"""
SELECT COUNT(*) n, COUNT(DISTINCT CONCAT(gender, child_item_type)) cats,
       COUNTIF(coef_source='parent') parent_cells,
       COUNT(DISTINCT IF(coef_source='parent', CONCAT(gender, child_item_type), NULL)) parent_cats,
       ROUND(AVG(coefficient), 3) avg_adj, ROUND(MAX(coefficient), 2) max_adj, ROUND(MIN(coefficient), 2) min_adj,
       ROUND(MAX(coefficient_raw), 1) max_raw, COUNTIF(coefficient_raw=0) raw_zero
FROM `{A}.seasonal_coefficients`"""))[0]
print("built seasonal_coefficients (受注実績ベース ＋ 対策A/B):")
print(f"  {r['n']}行 / {r['cats']}分類（うち親フォールバック {r['parent_cats']}分類・{r['parent_cells']}セル）")
print(f"  coefficient(補正後): 平均={r['avg_adj']} 範囲={r['min_adj']}〜{r['max_adj']}（クリップ[0.2,3.0]）")
print(f"  coefficient_raw(生): 最大={r['max_raw']} / 係数0の週={r['raw_zero']}セル")
