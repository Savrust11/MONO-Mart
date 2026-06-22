-- =============================================================================
-- Step 4: Build mart_layer.reorder_alerts for target_date
-- Subset of order_analysis — only actionable CRITICAL/WARNING items
-- =============================================================================

DELETE FROM `mart_layer.reorder_alerts`
WHERE analysis_date = @target_date;

INSERT INTO `mart_layer.reorder_alerts`
SELECT
  analysis_date,
  product_code,
  product_name,
  color_code,
  color_name,
  size,
  sku_code,
  order_urgency,
  stock_days_7d,
  days_to_stockout,
  free_inventory,
  incoming_stock,
  recommended_order_qty,
  trend_coefficient,
  daily_velocity_7d,
  -- 推定機会損失: units short × retail price
  -- If free_inventory is negative, we're already losing sales
  CAST(
    GREATEST(0, -free_inventory) * COALESCE(retail_price, 0)
  AS NUMERIC)                           AS estimated_lost_revenue,
  computed_at
FROM `mart_layer.order_analysis`
WHERE analysis_date = @target_date
  AND order_urgency IN ('CRITICAL', 'WARNING')
ORDER BY
  CASE order_urgency WHEN 'CRITICAL' THEN 0 ELSE 1 END ASC,
  days_to_stockout ASC NULLS LAST;
