-- =============================================================================
-- Step 1: Clean and deduplicate sales data for target_date
-- Writes into analytics_layer.sales_daily (partition overwrite)
-- =============================================================================

-- Delete existing partition first (idempotency)
DELETE FROM `analytics_layer.sales_daily`
WHERE sale_date = @target_date;

-- Insert cleaned sales for target_date
INSERT INTO `analytics_layer.sales_daily`
  (sale_date, sku_code, product_code, color_code, size,
   sales_quantity, sales_amount, favorites_total, view_count, ingested_at)

WITH raw AS (
  SELECT
    source_date                          AS sale_date,
    TRIM(UPPER(sku_code))                AS sku_code,
    TRIM(UPPER(product_code))            AS product_code,
    TRIM(UPPER(color_code))              AS color_code,
    TRIM(UPPER(size))                    AS size,
    COALESCE(sales_qty, 0)               AS sales_quantity,
    COALESCE(sales_amount, 0)            AS sales_amount,
    COALESCE(favorites_total, 0)         AS favorites_total,
    COALESCE(view_count, 0)              AS view_count,
    ingested_at,
    -- Deduplication: keep most recently ingested row per SKU per date
    ROW_NUMBER() OVER (
      PARTITION BY source_date, TRIM(UPPER(sku_code))
      ORDER BY ingested_at DESC
    ) AS rn
  FROM `raw_layer.zozo_sales_raw`
  WHERE source_date = @target_date
    AND sku_code IS NOT NULL
    AND sku_code != ''
)
SELECT
  sale_date, sku_code, product_code, color_code, size,
  sales_quantity, sales_amount, favorites_total, view_count, ingested_at
FROM raw
WHERE rn = 1;
