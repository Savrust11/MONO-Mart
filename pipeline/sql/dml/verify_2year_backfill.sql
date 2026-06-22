-- ============================================================
-- 2年分バックフィル 確認クエリ集
-- BigQuery コンソールで順番に実行してください
-- ============================================================


-- ════════════════════════════════════════════════════════════
-- STEP 1: 現在のデータ範囲を確認（まずここから実行）
-- 最古・最新の日付と総行数が返ります。
-- 2024-07-01 より前の最古日付が表示された場合はバックフィル未完了。
-- ════════════════════════════════════════════════════════════
SELECT
  MIN(sale_date)              AS oldest_date,      -- ← 2024-07-01 以降が理想
  MAX(sale_date)              AS latest_date,
  COUNT(*)                    AS total_rows,
  COUNT(DISTINCT sale_date)   AS days_with_data,
  COUNT(DISTINCT sku_code)    AS distinct_skus
FROM `mono-back-office-system.analytics_layer.sales_daily`;


-- ════════════════════════════════════════════════════════════
-- STEP 2: 月別データ量チェック（どの月のデータが揃っているか）
-- 行数が 0 の月 = まだデータが入っていない月
-- ════════════════════════════════════════════════════════════
SELECT
  DATE_TRUNC(sale_date, MONTH)   AS month,
  COUNT(*)                        AS row_count,
  SUM(sales_quantity)             AS total_orders,
  ROUND(SUM(sales_amount), 0)     AS revenue_excl_tax,
  COUNT(DISTINCT sku_code)        AS distinct_skus
FROM `mono-back-office-system.analytics_layer.sales_daily`
WHERE sale_date >= '2024-07-01'
GROUP BY 1
ORDER BY 1;


-- ════════════════════════════════════════════════════════════
-- STEP 3: 24ヶ月の欠損チェック（✅ OK / ❌ MISSING で一覧表示）
-- 理想: 全行が ✅ OK
-- ❌ MISSING の月 = その月のCSVがまだBigQueryに入っていない
-- ════════════════════════════════════════════════════════════
WITH expected AS (
  -- 2024-07 から 24ヶ月分（2026-06 まで）を生成
  SELECT DATE_ADD(DATE '2024-07-01', INTERVAL n MONTH) AS expected_month
  FROM UNNEST(GENERATE_ARRAY(0, 23)) AS n
),
actual AS (
  SELECT DISTINCT DATE_TRUNC(sale_date, MONTH) AS actual_month
  FROM `mono-back-office-system.analytics_layer.sales_daily`
  WHERE sale_date >= '2024-07-01'
)
SELECT
  expected_month,
  CASE
    WHEN actual_month IS NULL THEN '❌ MISSING'
    ELSE                           '✅ OK'
  END AS status
FROM expected
LEFT JOIN actual ON expected_month = actual_month
ORDER BY expected_month;


-- ════════════════════════════════════════════════════════════
-- STEP 4: 前年同月比（Phase 2 の目玉機能）
-- 2024-07〜2025-06 と 2025-07〜2026-06 の両方が揃うと
-- yoy_pct（前年比 %）が計算されます。
-- 片方しかない月は prev_year_revenue が NULL になります。
-- ════════════════════════════════════════════════════════════
SELECT
  DATE_TRUNC(sale_date, MONTH)                                  AS month,
  ROUND(SUM(sales_amount), 0)                                   AS revenue,
  SUM(sales_quantity)                                           AS orders,
  LAG(ROUND(SUM(sales_amount), 0))
    OVER (PARTITION BY EXTRACT(MONTH FROM sale_date)
          ORDER BY EXTRACT(YEAR  FROM sale_date))               AS prev_year_revenue,
  ROUND(
    (SUM(sales_amount)
       / NULLIF(
           LAG(SUM(sales_amount))
             OVER (PARTITION BY EXTRACT(MONTH FROM sale_date)
                   ORDER BY EXTRACT(YEAR  FROM sale_date)),
           0)
     - 1) * 100,
    1
  )                                                             AS yoy_pct
FROM `mono-back-office-system.analytics_layer.sales_daily`
WHERE sale_date >= '2024-07-01'
GROUP BY 1
ORDER BY month;


-- ════════════════════════════════════════════════════════════
-- STEP 5: raw_layer 確認（生データが正しく格納されているか）
-- analytics_layer に問題があるときはこちらで生データを確認
-- ════════════════════════════════════════════════════════════
SELECT
  MIN(sale_date)             AS oldest_raw,
  MAX(sale_date)             AS latest_raw,
  COUNT(*)                   AS raw_rows,
  COUNT(DISTINCT sale_date)  AS raw_days,
  COUNT(DISTINCT source_file) AS source_file_types
FROM `mono-back-office-system.raw_layer.zozo_sales_raw`
WHERE sale_date >= '2024-07-01';
