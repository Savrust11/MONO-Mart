-- =============================================================================
-- RAW LAYER: Append-only ingestion tables
-- These tables are NEVER updated or deleted. Data quality issues are fixed
-- downstream. Each run appends a new partition.
-- =============================================================================

-- Raw ZOZO sales data (one JSON blob per daily batch)
CREATE TABLE IF NOT EXISTS `raw_layer.zozo_sales_raw` (
  ingested_at   TIMESTAMP  NOT NULL OPTIONS(description="UTC time of ingestion"),
  source_date   DATE       NOT NULL OPTIONS(description="Business date this data covers"),
  sku_code      STRING     OPTIONS(description="CS品番 / SKU identifier from ZOZO"),
  product_code  STRING     OPTIONS(description="品番 / product code"),
  color_code    STRING     OPTIONS(description="Color identifier"),
  size          STRING     OPTIONS(description="Size (S/M/L/XL etc)"),
  sales_qty     INT64      OPTIONS(description="Units sold on source_date"),
  sales_amount  NUMERIC    OPTIONS(description="Sales amount in JPY"),
  favorites_total INT64    OPTIONS(description="Cumulative favorites count as of source_date"),
  view_count    INT64      OPTIONS(description="Page views on source_date"),
  raw_json      STRING     OPTIONS(description="Original API response JSON for audit"),
  source_file   STRING     OPTIONS(description="GCS path of raw file")
)
PARTITION BY source_date
CLUSTER BY product_code, sku_code
OPTIONS(
  description="Raw ZOZO daily sales. Append-only. Do not modify.",
  require_partition_filter=true
);

-- Raw ZOZO inventory snapshots
CREATE TABLE IF NOT EXISTS `raw_layer.zozo_inventory_raw` (
  ingested_at        TIMESTAMP  NOT NULL,
  snapshot_date      DATE       NOT NULL,
  sku_code           STRING,
  product_code       STRING,
  color_code         STRING,
  size               STRING,
  stock_quantity     INT64      OPTIONS(description="在庫数"),
  reserved_quantity  INT64      OPTIONS(description="予約引当済み数"),
  incoming_quantity  INT64      OPTIONS(description="入荷残 — ordered but not yet received"),
  shelf_type         STRING     OPTIONS(description="店舗棚情報 (通常/etc)"),
  raw_json           STRING,
  source_file        STRING
)
PARTITION BY snapshot_date
CLUSTER BY product_code, sku_code
OPTIONS(
  description="Raw ZOZO inventory snapshots. Append-only.",
  require_partition_filter=true
);

-- Raw Google Sheets reservations
CREATE TABLE IF NOT EXISTS `raw_layer.sheets_reservations_raw` (
  ingested_at      TIMESTAMP  NOT NULL,
  source_date      DATE       NOT NULL,
  reservation_id   STRING,
  sku_code         STRING,
  product_code     STRING,
  quantity         INT64,
  status           STRING,
  raw_json         STRING,
  source_file      STRING
)
PARTITION BY source_date
CLUSTER BY product_code, sku_code
OPTIONS(description="Raw reservation data from Google Sheets. Append-only.");

-- Raw Excel cost master (uploaded to GCS by staff)
CREATE TABLE IF NOT EXISTS `raw_layer.excel_cost_raw` (
  ingested_at        TIMESTAMP  NOT NULL,
  source_date        DATE       NOT NULL,
  product_code       STRING,
  color_code         STRING,
  cost_price         NUMERIC,
  retail_price       NUMERIC,
  production_lot_size INT64     OPTIONS(description="発注数 — production lot reference"),
  source_file        STRING,
  raw_json           STRING
)
PARTITION BY source_date
CLUSTER BY product_code
OPTIONS(description="Raw cost master from Excel uploads. Append-only.");
