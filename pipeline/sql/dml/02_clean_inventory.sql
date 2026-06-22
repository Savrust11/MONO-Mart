-- =============================================================================
-- Step 2: Clean and deduplicate inventory snapshot for target_date
-- Writes into analytics_layer.inventory_snapshot (partition overwrite)
-- =============================================================================

DELETE FROM `analytics_layer.inventory_snapshot`
WHERE snapshot_date = @target_date;

INSERT INTO `analytics_layer.inventory_snapshot`
  (snapshot_date, sku_code, product_code, color_code, size,
   stock_quantity, reserved_quantity, incoming_quantity, shelf_type, ingested_at)

WITH raw AS (
  SELECT
    snapshot_date,
    TRIM(UPPER(sku_code))               AS sku_code,
    TRIM(UPPER(product_code))           AS product_code,
    TRIM(UPPER(color_code))             AS color_code,
    TRIM(UPPER(size))                   AS size,
    GREATEST(0, COALESCE(stock_quantity, 0))    AS stock_quantity,
    GREATEST(0, COALESCE(reserved_quantity, 0)) AS reserved_quantity,
    GREATEST(0, COALESCE(incoming_quantity, 0)) AS incoming_quantity,
    COALESCE(shelf_type, '通常')        AS shelf_type,
    ingested_at,
    ROW_NUMBER() OVER (
      PARTITION BY snapshot_date, TRIM(UPPER(sku_code))
      ORDER BY ingested_at DESC
    ) AS rn
  FROM `raw_layer.zozo_inventory_raw`
  WHERE snapshot_date = @target_date
    AND sku_code IS NOT NULL
    AND sku_code != ''
)
SELECT
  snapshot_date, sku_code, product_code, color_code, size,
  stock_quantity, reserved_quantity, incoming_quantity, shelf_type, ingested_at
FROM raw
WHERE rn = 1;
