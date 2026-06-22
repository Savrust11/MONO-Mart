-- =============================================================================
-- Step 3: Build mart_layer.order_analysis for target_date
--
-- This is the core KPI calculation SQL that replaces the Excel 分析表 logic.
-- All formula assumptions are documented in docs/formula_assumptions.md.
--
-- Parameters (passed via BigQuery named params):
--   @target_date          DATE   e.g. '2025-11-03'
--   @coverage_weeks       INT64  target stock coverage in weeks (default: 8)
--   @trend_coeff_min      FLOAT  trend coefficient floor (default: 0.5)
--   @trend_coeff_max      FLOAT  trend coefficient ceiling (default: 2.0)
--   @critical_stock_days  INT64  stock_days threshold for CRITICAL (default: 0)
--   @warning_stock_days   INT64  stock_days threshold for WARNING (default: 14)
--   @overstock_stock_days INT64  stock_days threshold for OVERSTOCK (default: 90)
-- =============================================================================

-- Delete existing mart data for this date (full rebuild, idempotent)
DELETE FROM `mart_layer.order_analysis`
WHERE analysis_date = @target_date;

INSERT INTO `mart_layer.order_analysis`
SELECT
  analysis_date,
  product_code,
  product_name,
  color_code,
  color_name,
  size,
  sku_code,
  maker_color_code,
  shelf_type,
  -- Supply
  inventory,
  incoming_stock,
  reserved_quantity,
  reservations_pending,
  free_inventory,
  -- Demand
  sales_cumulative,
  favorites_total,
  sales_7d,
  sales_30d,
  sales_2w,
  sales_ytd,
  monthly_sales,
  daily_sales_30d,
  daily_velocity_7d,
  daily_velocity_30d,
  -- KPIs
  stock_days_7d,
  monthly_gap,
  trend_coefficient,
  -- Cost
  cost_price,
  retail_price,
  gross_margin_pct,
  -- Recommendation
  recommended_order_qty,
  order_urgency,
  days_to_stockout,
  CURRENT_TIMESTAMP() AS computed_at

FROM (

WITH

-- -----------------------------------------------------------------------
-- 1. Today's inventory snapshot
-- -----------------------------------------------------------------------
today_inventory AS (
  SELECT
    sku_code,
    stock_quantity,
    reserved_quantity,
    incoming_quantity   AS incoming_stock,
    shelf_type
  FROM `analytics_layer.inventory_snapshot`
  WHERE snapshot_date = @target_date
),

-- -----------------------------------------------------------------------
-- 2. Sales aggregations across multiple windows
-- -----------------------------------------------------------------------
sales_agg AS (
  SELECT
    sku_code,
    -- Rolling windows
    SUM(CASE WHEN sale_date >= DATE_SUB(@target_date, INTERVAL 7  DAY)
             THEN sales_quantity ELSE 0 END)                          AS sales_7d,
    SUM(CASE WHEN sale_date >= DATE_SUB(@target_date, INTERVAL 30 DAY)
             THEN sales_quantity ELSE 0 END)                          AS sales_30d,
    SUM(CASE WHEN sale_date >= DATE_SUB(@target_date, INTERVAL 14 DAY)
             THEN sales_quantity ELSE 0 END)                          AS sales_2w,
    SUM(CASE WHEN sale_date >= DATE_TRUNC(@target_date, YEAR)
             THEN sales_quantity ELSE 0 END)                          AS sales_ytd,
    SUM(sales_quantity)                                               AS sales_cumulative
  FROM `analytics_layer.sales_daily`
  WHERE sale_date <= @target_date
    AND sale_date >= DATE_SUB(@target_date, INTERVAL 400 DAY)  -- cap lookback for perf
  GROUP BY sku_code
),

-- Favorites aggregated at product_code level.
-- The 商品別実績 (No.8) CSV is product-level only (no sku_code), so the
-- favorites column in sales_daily is NULL for all SKU-keyed rows.
-- We aggregate here by product_code and join via pm.product_code below.
product_favorites AS (
  SELECT
    product_code,
    MAX(favorites)  AS favorites_total
  FROM `analytics_layer.sales_daily`
  WHERE sale_date <= @target_date
    AND sale_date >= DATE_SUB(@target_date, INTERVAL 400 DAY)
    AND favorites > 0
    AND product_code IS NOT NULL
  GROUP BY product_code
),

-- Monthly breakdowns (last 6 months)
monthly_sales_raw AS (
  SELECT
    sku_code,
    FORMAT_DATE('%Y-%m', sale_date) AS month,
    SUM(sales_quantity)             AS qty
  FROM `analytics_layer.sales_daily`
  WHERE sale_date >= DATE_SUB(@target_date, INTERVAL 180 DAY)
    AND sale_date <= @target_date
  GROUP BY sku_code, month
),

monthly_sales_agg AS (
  SELECT
    sku_code,
    ARRAY_AGG(STRUCT(month, qty) ORDER BY month DESC) AS monthly_sales
  FROM monthly_sales_raw
  GROUP BY sku_code
),

-- Daily sales for last 30 days (for sparkline)
daily_sales_agg AS (
  SELECT
    sku_code,
    ARRAY_AGG(
      STRUCT(sale_date, sales_quantity AS qty)
      ORDER BY sale_date DESC
      LIMIT 30
    ) AS daily_sales_30d
  FROM `analytics_layer.sales_daily`
  WHERE sale_date >= DATE_SUB(@target_date, INTERVAL 30 DAY)
    AND sale_date <= @target_date
  GROUP BY sku_code
),

-- -----------------------------------------------------------------------
-- 3. Pending reservations (from Google Sheets)
-- -----------------------------------------------------------------------
reservations_agg AS (
  SELECT
    sku_code,
    SUM(quantity) AS reservations_pending
  FROM `analytics_layer.reservations`
  WHERE status = 'pending'
  GROUP BY sku_code
),

-- -----------------------------------------------------------------------
-- 4. Cost master (point-in-time lookup for target_date)
-- -----------------------------------------------------------------------
cost_lookup AS (
  SELECT
    product_code,
    color_code,
    cost_price,
    retail_price,
    production_lot_size,
    ROW_NUMBER() OVER (
      PARTITION BY product_code, color_code
      ORDER BY valid_from DESC
    ) AS rn
  FROM `analytics_layer.cost_master`
  WHERE valid_from <= @target_date
    AND (valid_to IS NULL OR valid_to >= @target_date)
),

cost_master AS (
  SELECT * EXCEPT(rn) FROM cost_lookup WHERE rn = 1
),

-- -----------------------------------------------------------------------
-- 5. Base join — all active SKUs
-- -----------------------------------------------------------------------
base AS (
  SELECT
    @target_date                                          AS analysis_date,
    pm.product_code,
    pm.product_name,
    pm.color_code,
    pm.color_name,
    pm.size,
    pm.sku_code,
    pm.maker_color_code,
    pm.shelf_type,

    -- Supply
    COALESCE(inv.stock_quantity, 0)                       AS inventory,
    COALESCE(inv.incoming_stock, 0)                       AS incoming_stock,
    COALESCE(inv.reserved_quantity, 0)                    AS reserved_quantity,
    COALESCE(res.reservations_pending, 0)                 AS reservations_pending,

    -- フリー在庫 = 在庫 - 引当済 - 予約未処理数
    COALESCE(inv.stock_quantity, 0)
      - COALESCE(inv.reserved_quantity, 0)
      - COALESCE(res.reservations_pending, 0)             AS free_inventory,

    -- Demand aggregates
    COALESCE(sa.sales_cumulative, 0)                      AS sales_cumulative,
    COALESCE(pf.favorites_total, 0)                       AS favorites_total,
    COALESCE(sa.sales_7d, 0)                              AS sales_7d,
    COALESCE(sa.sales_30d, 0)                             AS sales_30d,
    COALESCE(sa.sales_2w, 0)                              AS sales_2w,
    COALESCE(sa.sales_ytd, 0)                             AS sales_ytd,
    COALESCE(ms.monthly_sales, [])                        AS monthly_sales,
    COALESCE(ds.daily_sales_30d, [])                      AS daily_sales_30d,

    -- Daily velocity
    SAFE_DIVIDE(COALESCE(sa.sales_7d, 0),  7.0)           AS daily_velocity_7d,
    SAFE_DIVIDE(COALESCE(sa.sales_30d, 0), 30.0)          AS daily_velocity_30d,

    -- Cost
    COALESCE(cm.cost_price, 0)                            AS cost_price,
    COALESCE(cm.retail_price, 0)                          AS retail_price

  FROM `analytics_layer.product_master` pm
  LEFT JOIN today_inventory     inv ON pm.sku_code = inv.sku_code
  LEFT JOIN sales_agg           sa  ON pm.sku_code = sa.sku_code
  LEFT JOIN product_favorites   pf  ON pm.product_code = pf.product_code
  LEFT JOIN monthly_sales_agg   ms  ON pm.sku_code = ms.sku_code
  LEFT JOIN daily_sales_agg     ds  ON pm.sku_code = ds.sku_code
  LEFT JOIN reservations_agg    res ON pm.sku_code = res.sku_code
  LEFT JOIN cost_master         cm  ON pm.product_code = cm.product_code
                                    AND (cm.color_code IS NULL
                                         OR pm.color_code = cm.color_code)
  WHERE pm.is_active = TRUE
),

-- -----------------------------------------------------------------------
-- 6. Derived KPIs
-- -----------------------------------------------------------------------
with_kpis AS (
  SELECT
    *,

    -- 7日間分: days of free inventory at current 7-day sales velocity
    -- Negative = already in stockout
    SAFE_DIVIDE(free_inventory, daily_velocity_7d)          AS stock_days_7d,

    -- 1ヶ月差分: free inventory surplus(+) or deficit(-) vs 30-day demand
    free_inventory - CAST(sales_30d AS INT64)               AS monthly_gap,

    -- トレンド係数: recent 7d velocity vs 30d average, clamped to [min, max]
    -- > 1.0 = accelerating sales, < 1.0 = decelerating
    LEAST(
      CAST(@trend_coeff_max AS FLOAT64),
      GREATEST(
        CAST(@trend_coeff_min AS FLOAT64),
        SAFE_DIVIDE(daily_velocity_7d, daily_velocity_30d)
      )
    )                                                        AS trend_coefficient,

    -- 粗利率
    SAFE_DIVIDE(retail_price - cost_price, retail_price)    AS gross_margin_pct

  FROM base
),

-- -----------------------------------------------------------------------
-- 7. Recommended order quantity & urgency classification
-- -----------------------------------------------------------------------
with_recommendation AS (
  SELECT
    *,

    -- 推奨発注数 formula:
    --   target_stock = coverage_days × daily_velocity_30d × trend_coefficient
    --   order = MAX(0, target_stock - free_inventory - incoming_stock)
    -- Coverage days = @coverage_weeks × 7
    GREATEST(0, CAST(CEIL(
      CAST(@coverage_weeks AS FLOAT64) * 7.0
        * daily_velocity_30d
        * trend_coefficient
      - free_inventory
      - incoming_stock
    ) AS INT64))                                             AS recommended_order_qty,

    -- Days until stockout at 7d velocity (NULL if no sales velocity)
    SAFE_DIVIDE(free_inventory, daily_velocity_7d)           AS days_to_stockout,

    -- 緊急度
    CASE
      WHEN SAFE_DIVIDE(free_inventory, daily_velocity_7d) IS NULL
        THEN 'OK'                                   -- no sales = no urgency
      WHEN SAFE_DIVIDE(free_inventory, daily_velocity_7d) <= CAST(@critical_stock_days AS FLOAT64)
        THEN 'CRITICAL'                             -- stockout or imminent
      WHEN SAFE_DIVIDE(free_inventory, daily_velocity_7d) <= CAST(@warning_stock_days AS FLOAT64)
        THEN 'WARNING'                              -- < 2 weeks
      WHEN SAFE_DIVIDE(free_inventory, daily_velocity_7d) > CAST(@overstock_stock_days AS FLOAT64)
        THEN 'OVERSTOCK'                            -- > 90 days
      ELSE 'OK'
    END                                                      AS order_urgency

  FROM with_kpis
)

SELECT * FROM with_recommendation

); -- end INSERT SELECT
