-- =============================================================================
-- Step 5: 在庫消化予測 (Inventory Liquidation Forecast)
--
-- Produces a 12-week forward projection of free inventory per SKU,
-- applying weekly seasonal coefficients to adjust velocity.
--
-- Must run AFTER 03_kpi_metrics.sql (reads mart_layer.order_analysis)
--
-- Parameters:
--   @target_date  DATE   e.g. '2025-11-03'
-- =============================================================================

DELETE FROM `analytics_layer.inventory_forecast`
WHERE forecast_date = @target_date;

INSERT INTO `analytics_layer.inventory_forecast`

WITH

-- -----------------------------------------------------------------------
-- 1. Pull today's order_analysis snapshot
-- -----------------------------------------------------------------------
base AS (
  SELECT
    analysis_date   AS forecast_date,
    sku_code,
    product_code,
    color_code,
    size,
    free_inventory                            AS starting_free_inventory,
    daily_velocity_30d,
    trend_coefficient,
    recommended_order_qty,
    EXTRACT(ISOWEEK FROM @target_date)        AS current_iso_week
  FROM `mart_layer.order_analysis`
  WHERE analysis_date = @target_date
),

-- -----------------------------------------------------------------------
-- 2. Seasonal coefficients for weeks current through current+11
--    Wrap week numbers past 52 back to 1
-- -----------------------------------------------------------------------
weeks AS (
  SELECT week_offset, MOD(current_iso_week + week_offset - 1, 52) + 1 AS iso_week
  FROM UNNEST(GENERATE_ARRAY(0, 11)) AS week_offset
  CROSS JOIN (SELECT EXTRACT(ISOWEEK FROM @target_date) AS current_iso_week)
),

seasonal AS (
  SELECT
    w.week_offset,
    w.iso_week,
    COALESCE(sc.coefficient, 1.0) AS coefficient
  FROM weeks w
  LEFT JOIN `analytics_layer.seasonal_coefficients` sc
    ON sc.week_number = w.iso_week
    AND sc.category   = 'all'
),

-- -----------------------------------------------------------------------
-- 3. Compute weekly demand (7 days × daily_velocity × trend × season)
--    then project running stock week by week
-- -----------------------------------------------------------------------
projections AS (
  SELECT
    b.*,
    -- Weekly demand for each of the 12 forward weeks
    s0.coefficient  AS coeff_w1,
    s1.coefficient  AS coeff_w2,
    s2.coefficient  AS coeff_w3,
    s3.coefficient  AS coeff_w4,
    s4.coefficient  AS coeff_w5,
    s5.coefficient  AS coeff_w6,
    s6.coefficient  AS coeff_w7,
    s7.coefficient  AS coeff_w8,
    s8.coefficient  AS coeff_w9,
    s9.coefficient  AS coeff_w10,
    s10.coefficient AS coeff_w11,
    s11.coefficient AS coeff_w12,

    -- Base weekly demand = 7 × velocity × trend (clamped [0.5,2.0])
    ROUND(7.0 * COALESCE(daily_velocity_30d, 0)
               * LEAST(2.0, GREATEST(0.5, COALESCE(trend_coefficient, 1.0))), 1) AS base_weekly_demand,

    -- Projected free inventory at end of each week
    -- proj_wN = starting - sum(demand_w1..wN)
    CAST(ROUND(starting_free_inventory
      - 7.0 * COALESCE(daily_velocity_30d, 0)
              * LEAST(2.0, GREATEST(0.5, COALESCE(trend_coefficient, 1.0)))
              * s0.coefficient
    ) AS INT64) AS projected_week_1,

    CAST(ROUND(starting_free_inventory
      - 7.0 * COALESCE(daily_velocity_30d, 0)
              * LEAST(2.0, GREATEST(0.5, COALESCE(trend_coefficient, 1.0)))
              * (s0.coefficient + s1.coefficient)
    ) AS INT64) AS projected_week_2,

    CAST(ROUND(starting_free_inventory
      - 7.0 * COALESCE(daily_velocity_30d, 0)
              * LEAST(2.0, GREATEST(0.5, COALESCE(trend_coefficient, 1.0)))
              * (s0.coefficient + s1.coefficient + s2.coefficient)
    ) AS INT64) AS projected_week_3,

    CAST(ROUND(starting_free_inventory
      - 7.0 * COALESCE(daily_velocity_30d, 0)
              * LEAST(2.0, GREATEST(0.5, COALESCE(trend_coefficient, 1.0)))
              * (s0.coefficient + s1.coefficient + s2.coefficient + s3.coefficient)
    ) AS INT64) AS projected_week_4,

    CAST(ROUND(starting_free_inventory
      - 7.0 * COALESCE(daily_velocity_30d, 0)
              * LEAST(2.0, GREATEST(0.5, COALESCE(trend_coefficient, 1.0)))
              * (s0.coefficient + s1.coefficient + s2.coefficient + s3.coefficient + s4.coefficient)
    ) AS INT64) AS projected_week_5,

    CAST(ROUND(starting_free_inventory
      - 7.0 * COALESCE(daily_velocity_30d, 0)
              * LEAST(2.0, GREATEST(0.5, COALESCE(trend_coefficient, 1.0)))
              * (s0.coefficient + s1.coefficient + s2.coefficient + s3.coefficient + s4.coefficient + s5.coefficient)
    ) AS INT64) AS projected_week_6,

    CAST(ROUND(starting_free_inventory
      - 7.0 * COALESCE(daily_velocity_30d, 0)
              * LEAST(2.0, GREATEST(0.5, COALESCE(trend_coefficient, 1.0)))
              * (s0.coefficient + s1.coefficient + s2.coefficient + s3.coefficient + s4.coefficient + s5.coefficient + s6.coefficient)
    ) AS INT64) AS projected_week_7,

    CAST(ROUND(starting_free_inventory
      - 7.0 * COALESCE(daily_velocity_30d, 0)
              * LEAST(2.0, GREATEST(0.5, COALESCE(trend_coefficient, 1.0)))
              * (s0.coefficient + s1.coefficient + s2.coefficient + s3.coefficient + s4.coefficient + s5.coefficient + s6.coefficient + s7.coefficient)
    ) AS INT64) AS projected_week_8,

    CAST(ROUND(starting_free_inventory
      - 7.0 * COALESCE(daily_velocity_30d, 0)
              * LEAST(2.0, GREATEST(0.5, COALESCE(trend_coefficient, 1.0)))
              * (s0.coefficient + s1.coefficient + s2.coefficient + s3.coefficient + s4.coefficient + s5.coefficient + s6.coefficient + s7.coefficient + s8.coefficient)
    ) AS INT64) AS projected_week_9,

    CAST(ROUND(starting_free_inventory
      - 7.0 * COALESCE(daily_velocity_30d, 0)
              * LEAST(2.0, GREATEST(0.5, COALESCE(trend_coefficient, 1.0)))
              * (s0.coefficient + s1.coefficient + s2.coefficient + s3.coefficient + s4.coefficient + s5.coefficient + s6.coefficient + s7.coefficient + s8.coefficient + s9.coefficient)
    ) AS INT64) AS projected_week_10,

    CAST(ROUND(starting_free_inventory
      - 7.0 * COALESCE(daily_velocity_30d, 0)
              * LEAST(2.0, GREATEST(0.5, COALESCE(trend_coefficient, 1.0)))
              * (s0.coefficient + s1.coefficient + s2.coefficient + s3.coefficient + s4.coefficient + s5.coefficient + s6.coefficient + s7.coefficient + s8.coefficient + s9.coefficient + s10.coefficient)
    ) AS INT64) AS projected_week_11,

    CAST(ROUND(starting_free_inventory
      - 7.0 * COALESCE(daily_velocity_30d, 0)
              * LEAST(2.0, GREATEST(0.5, COALESCE(trend_coefficient, 1.0)))
              * (s0.coefficient + s1.coefficient + s2.coefficient + s3.coefficient + s4.coefficient + s5.coefficient + s6.coefficient + s7.coefficient + s8.coefficient + s9.coefficient + s10.coefficient + s11.coefficient)
    ) AS INT64) AS projected_week_12

  FROM base b
  JOIN seasonal s0  ON s0.week_offset = 0
  JOIN seasonal s1  ON s1.week_offset = 1
  JOIN seasonal s2  ON s2.week_offset = 2
  JOIN seasonal s3  ON s3.week_offset = 3
  JOIN seasonal s4  ON s4.week_offset = 4
  JOIN seasonal s5  ON s5.week_offset = 5
  JOIN seasonal s6  ON s6.week_offset = 6
  JOIN seasonal s7  ON s7.week_offset = 7
  JOIN seasonal s8  ON s8.week_offset = 8
  JOIN seasonal s9  ON s9.week_offset = 9
  JOIN seasonal s10 ON s10.week_offset = 10
  JOIN seasonal s11 ON s11.week_offset = 11
),

-- -----------------------------------------------------------------------
-- 4. Determine stockout week (first week where projected stock < 0)
-- -----------------------------------------------------------------------
with_stockout AS (
  SELECT
    *,
    CASE
      WHEN projected_week_1  < 0 THEN 1
      WHEN projected_week_2  < 0 THEN 2
      WHEN projected_week_3  < 0 THEN 3
      WHEN projected_week_4  < 0 THEN 4
      WHEN projected_week_5  < 0 THEN 5
      WHEN projected_week_6  < 0 THEN 6
      WHEN projected_week_7  < 0 THEN 7
      WHEN projected_week_8  < 0 THEN 8
      WHEN projected_week_9  < 0 THEN 9
      WHEN projected_week_10 < 0 THEN 10
      WHEN projected_week_11 < 0 THEN 11
      WHEN projected_week_12 < 0 THEN 12
      ELSE NULL
    END AS estimated_stockout_week,

    -- "with order" scenario: add recommended_order_qty to starting inventory
    -- then find first week stock goes negative
    CASE
      WHEN starting_free_inventory + recommended_order_qty - CAST(ROUND(base_weekly_demand * coeff_w1) AS INT64) < 0 THEN 1
      WHEN starting_free_inventory + recommended_order_qty
           - CAST(ROUND(base_weekly_demand * (coeff_w1 + coeff_w2)) AS INT64) < 0 THEN 2
      WHEN starting_free_inventory + recommended_order_qty
           - CAST(ROUND(base_weekly_demand * (coeff_w1 + coeff_w2 + coeff_w3)) AS INT64) < 0 THEN 3
      WHEN starting_free_inventory + recommended_order_qty
           - CAST(ROUND(base_weekly_demand * (coeff_w1 + coeff_w2 + coeff_w3 + coeff_w4)) AS INT64) < 0 THEN 4
      WHEN starting_free_inventory + recommended_order_qty
           - CAST(ROUND(base_weekly_demand * (coeff_w1 + coeff_w2 + coeff_w3 + coeff_w4 + coeff_w5)) AS INT64) < 0 THEN 5
      WHEN starting_free_inventory + recommended_order_qty
           - CAST(ROUND(base_weekly_demand * (coeff_w1 + coeff_w2 + coeff_w3 + coeff_w4 + coeff_w5 + coeff_w6)) AS INT64) < 0 THEN 6
      ELSE NULL  -- won't stock out within 6 weeks with recommended order
    END AS with_order_stockout_week

  FROM projections
)

SELECT
  forecast_date,
  sku_code,
  product_code,
  color_code,
  size,
  starting_free_inventory,
  daily_velocity_30d,
  trend_coefficient,
  projected_week_1,
  projected_week_2,
  projected_week_3,
  projected_week_4,
  projected_week_5,
  projected_week_6,
  projected_week_7,
  projected_week_8,
  projected_week_9,
  projected_week_10,
  projected_week_11,
  projected_week_12,
  estimated_stockout_week,
  CASE WHEN estimated_stockout_week IS NOT NULL
       THEN DATE_ADD(@target_date, INTERVAL estimated_stockout_week * 7 DAY)
       ELSE NULL
  END AS estimated_stockout_date,
  with_order_stockout_week,
  CURRENT_TIMESTAMP() AS computed_at
FROM with_stockout;
