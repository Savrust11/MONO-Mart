-- =============================================================================
-- analytics_layer.seasonal_coefficients
--
-- Stores 52-week seasonal indices per product category.
-- Used by the forecast SQL to adjust velocity estimates by season.
--
-- How to populate:
--   - Initial seed: manually entered from historical sales patterns
--   - Ongoing: recalculated monthly by comparing same-week sales vs. annual avg
--
-- coefficient meaning:
--   1.0 = average week
--   1.3 = 30% above average (peak season)
--   0.7 = 30% below average (off season)
-- =============================================================================

CREATE TABLE IF NOT EXISTS `analytics_layer.seasonal_coefficients` (
  category        STRING NOT NULL,  -- e.g. 'tops', 'bottoms', 'accessories', 'all'
  week_number     INT64  NOT NULL,  -- ISO week number 1–52
  coefficient     FLOAT64 NOT NULL, -- seasonal index (1.0 = baseline)
  updated_at      TIMESTAMP
);

-- =============================================================================
-- analytics_layer.inventory_forecast
--
-- Pre-computed 12-week forward inventory forecast per SKU.
-- Rebuilt nightly by 05_forecast.sql after order_analysis is ready.
-- =============================================================================

CREATE TABLE IF NOT EXISTS `analytics_layer.inventory_forecast` (
  forecast_date   DATE NOT NULL,      -- date this forecast was computed (= today)
  sku_code        STRING NOT NULL,
  product_code    STRING NOT NULL,
  color_code      STRING NOT NULL,
  size            STRING NOT NULL,
  -- Input snapshot
  starting_free_inventory INT64,
  daily_velocity_30d      FLOAT64,
  trend_coefficient       FLOAT64,
  -- Forecast columns: projected_free_stock_wN = free stock at end of week N
  projected_week_1        INT64,
  projected_week_2        INT64,
  projected_week_3        INT64,
  projected_week_4        INT64,
  projected_week_5        INT64,
  projected_week_6        INT64,
  projected_week_7        INT64,
  projected_week_8        INT64,
  projected_week_9        INT64,
  projected_week_10       INT64,
  projected_week_11       INT64,
  projected_week_12       INT64,
  -- When does stock run out?
  estimated_stockout_week INT64,      -- NULL = will not stock out within 12 weeks
  estimated_stockout_date DATE,       -- NULL = same
  -- If an order of recommended_order_qty is placed today
  with_order_stockout_week INT64,
  computed_at             TIMESTAMP
)
PARTITION BY forecast_date
CLUSTER BY product_code, sku_code;


-- =============================================================================
-- Seed data: default seasonal coefficients for all categories
-- These are generic apparel seasonality patterns — tune per brand/category
-- =============================================================================

INSERT INTO `analytics_layer.seasonal_coefficients`
  (category, week_number, coefficient, updated_at)
VALUES
-- Week 1-13: Winter / Post-holiday clearance → early spring
('all',  1, 0.75, CURRENT_TIMESTAMP()),
('all',  2, 0.70, CURRENT_TIMESTAMP()),
('all',  3, 0.72, CURRENT_TIMESTAMP()),
('all',  4, 0.78, CURRENT_TIMESTAMP()),
('all',  5, 0.80, CURRENT_TIMESTAMP()),
('all',  6, 0.82, CURRENT_TIMESTAMP()),
('all',  7, 0.85, CURRENT_TIMESTAMP()),
('all',  8, 0.88, CURRENT_TIMESTAMP()),
('all',  9, 0.92, CURRENT_TIMESTAMP()),
('all', 10, 0.95, CURRENT_TIMESTAMP()),
('all', 11, 0.98, CURRENT_TIMESTAMP()),
('all', 12, 1.00, CURRENT_TIMESTAMP()),
('all', 13, 1.02, CURRENT_TIMESTAMP()),
-- Week 14-26: Spring/early summer peak
('all', 14, 1.05, CURRENT_TIMESTAMP()),
('all', 15, 1.10, CURRENT_TIMESTAMP()),
('all', 16, 1.15, CURRENT_TIMESTAMP()),
('all', 17, 1.18, CURRENT_TIMESTAMP()),
('all', 18, 1.20, CURRENT_TIMESTAMP()),
('all', 19, 1.18, CURRENT_TIMESTAMP()),
('all', 20, 1.15, CURRENT_TIMESTAMP()),
('all', 21, 1.12, CURRENT_TIMESTAMP()),
('all', 22, 1.10, CURRENT_TIMESTAMP()),
('all', 23, 1.08, CURRENT_TIMESTAMP()),
('all', 24, 1.05, CURRENT_TIMESTAMP()),
('all', 25, 1.02, CURRENT_TIMESTAMP()),
('all', 26, 1.00, CURRENT_TIMESTAMP()),
-- Week 27-39: Summer sale / off-peak
('all', 27, 0.95, CURRENT_TIMESTAMP()),
('all', 28, 0.90, CURRENT_TIMESTAMP()),
('all', 29, 0.88, CURRENT_TIMESTAMP()),
('all', 30, 0.85, CURRENT_TIMESTAMP()),
('all', 31, 0.85, CURRENT_TIMESTAMP()),
('all', 32, 0.88, CURRENT_TIMESTAMP()),
('all', 33, 0.92, CURRENT_TIMESTAMP()),
('all', 34, 0.95, CURRENT_TIMESTAMP()),
('all', 35, 0.98, CURRENT_TIMESTAMP()),
('all', 36, 1.00, CURRENT_TIMESTAMP()),
('all', 37, 1.02, CURRENT_TIMESTAMP()),
('all', 38, 1.05, CURRENT_TIMESTAMP()),
('all', 39, 1.08, CURRENT_TIMESTAMP()),
-- Week 40-52: Autumn/Winter peak → year-end
('all', 40, 1.12, CURRENT_TIMESTAMP()),
('all', 41, 1.15, CURRENT_TIMESTAMP()),
('all', 42, 1.18, CURRENT_TIMESTAMP()),
('all', 43, 1.20, CURRENT_TIMESTAMP()),
('all', 44, 1.22, CURRENT_TIMESTAMP()),
('all', 45, 1.25, CURRENT_TIMESTAMP()),
('all', 46, 1.28, CURRENT_TIMESTAMP()),
('all', 47, 1.30, CURRENT_TIMESTAMP()),
('all', 48, 1.25, CURRENT_TIMESTAMP()),
('all', 49, 1.20, CURRENT_TIMESTAMP()),
('all', 50, 1.15, CURRENT_TIMESTAMP()),
('all', 51, 1.05, CURRENT_TIMESTAMP()),
('all', 52, 0.90, CURRENT_TIMESTAMP());
