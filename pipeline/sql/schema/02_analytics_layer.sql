-- =============================================================================
-- ANALYTICS LAYER: Cleaned, typed, deduplicated tables
-- These are the source-of-truth tables for KPI calculations.
-- Updated nightly via MERGE or CREATE OR REPLACE PARTITION.
-- Schemas aligned with CSV extractor output (zozo_csv_extractor, mms_extractor, etc).
-- =============================================================================

-- Product master — one row per SKU (from goods_cs.csv)
CREATE TABLE IF NOT EXISTS `analytics_layer.product_master` (
  sku_code          STRING  NOT NULL OPTIONS(description="CS別品番 — unique SKU identifier"),
  product_code      STRING           OPTIONS(description="ブランド品番"),
  product_name      STRING           OPTIONS(description="商品名"),
  color_name        STRING,
  size              STRING,
  shop_name         STRING,
  parent_category   STRING,
  child_category    STRING,
  parent_item_type  STRING,
  child_item_type   STRING,
  gender            STRING,
  unit_price        NUMERIC,
  proper_price      NUMERIC,
  price_type        STRING,
  sale_type         STRING,
  sale_start_date   STRING,
  registered_date   STRING,
  barcode           STRING,
  item_code         STRING,
  goods_detail_id   STRING,
  mall              STRING,
  is_active         BOOL,
  shelf_type        STRING,
  source_file       STRING,
  updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
CLUSTER BY product_code, sku_code
OPTIONS(description="Product master — one row per SKU (product × color × size).");

-- Daily sales — one row per SKU per day from CSV orders/shipped/performance
CREATE TABLE IF NOT EXISTS `analytics_layer.sales_daily` (
  sale_date         DATE    NOT NULL,
  sku_code          STRING,
  product_code      STRING,
  product_name      STRING,
  color_name        STRING,
  size              STRING,
  shop_name         STRING,
  parent_category   STRING,
  child_category    STRING,
  gender            STRING,
  sales_quantity    INT64,
  sales_amount      NUMERIC,
  unit_price        NUMERIC,
  proper_price      NUMERIC,
  price_type        STRING,
  sale_type         STRING,
  mall              STRING,
  device            STRING,
  order_number      STRING,
  shipped_date      STRING,
  -- Performance-specific fields (No.8)
  item_code             STRING,
  favorites             INT64,
  cart_adds             INT64,
  unique_visitors       INT64,
  page_views            INT64,
  buyers_total          INT64,
  buyers_male           INT64,
  buyers_female         INT64,
  buyers_new            INT64,
  buyers_existing       INT64,
  buyers_revived        INT64,
  available_qty_excl    INT64,
  available_qty_incl    INT64,
  average_age           FLOAT64,
  shop_parent_category  STRING,
  shop_child_category   STRING,
  zozo_parent_category  STRING,
  zozo_child_category   STRING,
  -- Metadata
  source_file       STRING,
  ingested_date     DATE,
  ingested_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
PARTITION BY sale_date
CLUSTER BY product_code, sku_code
OPTIONS(
  description="Daily sales per SKU/item from orders, shipped, and performance CSVs.",
  require_partition_filter=false
);

-- Inventory snapshots — daily warehouse stock from S{yyyymmdd}.csv
CREATE TABLE IF NOT EXISTS `analytics_layer.inventory_snapshot` (
  snapshot_date       DATE    NOT NULL,
  sku_code            STRING,
  product_code        STRING,
  product_name        STRING,
  color_name          STRING,
  size                STRING,
  shop_name           STRING,
  stock_quantity      INT64,
  reserved_quantity   INT64,
  incoming_quantity   INT64,
  unit_price          NUMERIC,
  proper_price        NUMERIC,
  price_type          STRING,
  stock_value         NUMERIC,
  arrival_date        STRING,
  delivery_note_no    STRING,
  shelf_type          STRING,
  source_file         STRING,
  ingested_date       DATE,
  ingested_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
PARTITION BY snapshot_date
CLUSTER BY product_code, sku_code
OPTIONS(description="Daily inventory snapshot per SKU.");

-- Reservations — from ReserveList CSV (or Google Sheets)
CREATE TABLE IF NOT EXISTS `analytics_layer.reservations` (
  reservation_date    DATE,
  updated_date        DATE,
  reservation_id      STRING,
  sku_code            STRING,
  product_code        STRING,
  product_name        STRING,
  color_name          STRING,
  size                STRING,
  shop_name           STRING,
  quantity            INT64,
  reserved_qty        INT64,
  ordered_qty         INT64,
  available_qty       INT64,
  stock_quantity      INT64,
  ship_date           STRING,
  expected_arrival    STRING,
  status              STRING,
  source              STRING,
  created_at          TIMESTAMP,
  updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
  ingested_date       DATE
)
PARTITION BY reservation_date
CLUSTER BY product_code, sku_code
OPTIONS(description="Pending reservations from ZOZO ReserveList or Google Sheets.");

-- Cost master from MMS 評価額一覧 or Excel
CREATE TABLE IF NOT EXISTS `analytics_layer.cost_master` (
  sku_code            STRING,
  product_code        STRING,
  product_name        STRING,
  color_name          STRING,
  size                STRING,
  cost_price          NUMERIC,
  retail_price        NUMERIC,
  valuation_price     NUMERIC,
  production_lot_size INT64,
  mms_product_id      STRING,
  shop_id             STRING,
  updated_date        STRING,
  valid_from          DATE,
  valid_to            DATE,
  source_file         STRING,
  source_date         DATE,
  updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
CLUSTER BY product_code
OPTIONS(description="Cost master per SKU from MMS 評価額一覧.");

-- ZOZOAD daily ad performance per item
CREATE TABLE IF NOT EXISTS `analytics_layer.zozoad_daily` (
  record_date         DATE    NOT NULL OPTIONS(description="集計日"),
  shop_id             STRING           OPTIONS(description="ZOZO Shop ID"),
  shop_name           STRING           OPTIONS(description="ショップ名 (=Brand)"),
  parent_category     STRING,
  child_category      STRING,
  product_code        STRING           OPTIONS(description="ブランド品番"),
  item_code           STRING  NOT NULL OPTIONS(description="商品コード"),
  product_name        STRING,
  parent_item_type    STRING,
  child_item_type     STRING,
  display_location    STRING           OPTIONS(description="表示箇所: プレミア etc"),
  impressions         INT64            OPTIONS(description="imp"),
  clicks              INT64            OPTIONS(description="click"),
  ad_cost             NUMERIC          OPTIONS(description="コスト JPY"),
  attributed_orders   INT64            OPTIONS(description="経由売上件数"),
  attributed_revenue  NUMERIC          OPTIONS(description="経由売上金額（税抜） JPY"),
  ctr                 FLOAT64          OPTIONS(description="Click-through rate (e.g. 1.57)"),
  cpc                 NUMERIC          OPTIONS(description="Cost per click JPY"),
  roas                FLOAT64          OPTIONS(description="Return on ad spend % (e.g. 1268)"),
  source_file         STRING,
  ingested_date       DATE,
  ingested_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
PARTITION BY record_date
CLUSTER BY shop_name, item_code
OPTIONS(description="ZOZOAD daily ad performance per product (No.7).");

-- Sale settings snapshot
CREATE TABLE IF NOT EXISTS `analytics_layer.sale_settings` (
  snapshot_date          DATE    NOT NULL OPTIONS(description="Snapshot date when CSV was downloaded"),
  item_code              STRING  NOT NULL OPTIONS(description="商品コード"),
  product_code           STRING           OPTIONS(description="ブランド品番"),
  product_name           STRING,
  shop_name              STRING,
  parent_category        STRING,
  proper_price           NUMERIC          OPTIONS(description="プロパー価格（税抜） JPY"),
  sale_price             NUMERIC          OPTIONS(description="変更後セール価格（税抜） JPY"),
  discount_pct           FLOAT64          OPTIONS(description="オフ率 (e.g. 10 = 10% off)"),
  stock_quantity         INT64,
  latest_sale_start_date STRING,
  sale_start_at          STRING           OPTIONS(description="セール開始予定日時"),
  sale_end_at            STRING           OPTIONS(description="タイムセール終了日時"),
  resale_price           NUMERIC,
  sale_type              STRING           OPTIONS(description="ZOZO企画タイムセール etc"),
  source_file            STRING,
  ingested_date          DATE,
  captured_at            TIMESTAMP        OPTIONS(description="CSVダウンロード時刻 (GCS blob time_created)。常時タイムセールの価格を『いつ時点の価格か』で時系列追跡するため。再取込で上書きされる ingested_at と異なり元の取得時刻を保持。"),
  ingested_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
PARTITION BY snapshot_date
CLUSTER BY shop_name, item_code
OPTIONS(description="Daily snapshot of items currently on sale (No.17).");

-- Stock analysis (No.6 在庫分析) — has built-in sales velocity (7d/30d/yesterday)
CREATE TABLE IF NOT EXISTS `analytics_layer.stock_analysis` (
  snapshot_date       DATE    NOT NULL,
  sku_code            STRING  NOT NULL,
  product_code        STRING,
  product_name        STRING,
  color_name          STRING,
  size                STRING,
  shop_name           STRING,
  gender              STRING,
  available_qty       INT64   OPTIONS(description="販売可能数 (free inventory excluding reservations/unshipped)"),
  external_available  INT64   OPTIONS(description="外部販売可能数 (Yahoo etc)"),
  total_available     INT64   OPTIONS(description="販売可能数合計"),
  pre_sale_qty        INT64,
  pre_sale_reserved   INT64,
  sales_30d           INT64   OPTIONS(description="直近30日販売数 — built-in velocity"),
  sales_7d            INT64   OPTIONS(description="直近7日販売数 — built-in velocity"),
  sales_yesterday     INT64,
  unit_price          NUMERIC,
  proper_price        NUMERIC,
  price_type          STRING,
  sale_start_date     STRING,
  arrival_date        STRING  OPTIONS(description="継続入荷日 (ArriveDT) — added 2026-06-17"),
  favorites           INT64   OPTIONS(description="お気に入り登録数 (SKU-level, 30d window) — added 2026-06-17"),
  barcode             STRING  OPTIONS(description="バーコード (slash-separated if multiple) — added 2026-06-17"),
  source_file         STRING,
  ingested_date       DATE,
  ingested_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
PARTITION BY snapshot_date
CLUSTER BY product_code, sku_code
OPTIONS(description="Stock analysis with built-in 7d/30d sales velocity (No.6).");

-- Incoming stock (MMS着荷データ + Tableau予約管理 + 発注明細)
CREATE TABLE IF NOT EXISTS `analytics_layer.incoming_stock` (
  source_date          DATE,
  sku_code             STRING,
  product_code         STRING,
  product_name         STRING,
  color_name           STRING,
  size                 STRING,
  shop_name            STRING,
  incoming_qty         INT64   OPTIONS(description="入荷残 = 発注数 − 着荷数量"),
  ordered_qty          INT64,
  delivered_qty        INT64,
  unit_price           NUMERIC,
  earliest_arrival_date STRING,
  source               STRING,
  source_file          STRING,
  ingested_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
PARTITION BY source_date
CLUSTER BY product_code, sku_code
OPTIONS(description="Pending incoming stock per SKU from MMS + Tableau sources.");

-- sitateru product metadata (item list daily snapshot)
CREATE TABLE IF NOT EXISTS `analytics_layer.sitateru_item_master` (
  snapshot_date            DATE    NOT NULL,
  sitateru_item_id         STRING  NOT NULL OPTIONS(description="sitateru アイテムID"),
  item_name                STRING,
  product_code             STRING  OPTIONS(description="品番 — links to ZOZO/MMS"),
  tentative_product_code   STRING,
  shop_name                STRING,
  brand_name               STRING,
  product_name             STRING,
  manufacturer             STRING,
  business_division        STRING  OPTIONS(description="プロダクト1部 / プロダクト2部"),
  planner                  STRING,
  order_type               STRING  OPTIONS(description="新品番 / リピート / 新色 etc"),
  season                   STRING  OPTIONS(description="24/AW, 25/SS etc"),
  md_season                STRING,
  md_type                  STRING,
  zozo_parent_category     STRING,
  zozo_child_category      STRING,
  zozo_main_gender         STRING,
  zozo_sub_gender          STRING,
  category                 STRING,
  promo_rank               STRING,
  color_options            STRING,
  size_options             STRING,
  planned_delivery_date    STRING,
  delivery_available_date  STRING,
  confirmed_delivery_date  STRING,
  confirmed_release_date   STRING,
  release_week             STRING,
  promo_week               STRING,
  first_delivery_date      STRING,
  proposed_wholesale_price INT64,
  proposed_retail_price    INT64,
  confirmed_wholesale_price INT64,
  confirmed_retail_price   INT64,
  actual_cost              INT64,
  total_order_qty          INT64,
  actual_delivery_qty      INT64,
  sample_quantity          INT64,
  production_quantity      INT64,
  progress_status          STRING  OPTIONS(description="本発注済 / 仮発注済 / 進行中"),
  sample_status            STRING,
  display_aggregation_flag STRING,
  production_country       STRING,
  sale_type                STRING,
  tags                     STRING,
  public_tags              STRING,
  source_file              STRING,
  ingested_date            DATE,
  ingested_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
PARTITION BY snapshot_date
CLUSTER BY brand_name, product_code
OPTIONS(description="sitateru product metadata (No.12) — daily snapshot.");

-- Search-keyword access (No.20) — daily TOP20 keywords per shop with click/visit/sales
CREATE TABLE IF NOT EXISTS `analytics_layer.search_keyword_daily` (
  record_date         DATE    NOT NULL OPTIONS(description="集計日"),
  shop_name           STRING           OPTIONS(description="ショップ名"),
  search_keyword      STRING           OPTIONS(description="検索キーワード"),
  rank                INT64            OPTIONS(description="TOP20内ランク"),
  visits              INT64            OPTIONS(description="経由訪問数"),
  page_views          INT64            OPTIONS(description="経由PV"),
  orders              INT64            OPTIONS(description="経由注文数"),
  sales_amount        NUMERIC          OPTIONS(description="経由売上金額(税抜)"),
  source_file         STRING,
  ingested_date       DATE,
  ingested_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
PARTITION BY record_date
CLUSTER BY shop_name, search_keyword
OPTIONS(description="日別 検索キーワード経由アクセス実績 TOP20 (No.20).");

-- Access log (No.19) — daily PV/DAU time series per shop App/PC/SP
CREATE TABLE IF NOT EXISTS `analytics_layer.access_log_daily` (
  record_date         DATE    NOT NULL OPTIONS(description="集計日"),
  shop_name           STRING           OPTIONS(description="ショップ名"),
  device_type         STRING           OPTIONS(description="App / PC / SP / 合計"),
  page_views          INT64            OPTIONS(description="PV"),
  daily_active_users  INT64            OPTIONS(description="DAU"),
  source_file         STRING,
  ingested_date       DATE,
  ingested_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
PARTITION BY record_date
CLUSTER BY shop_name, device_type
OPTIONS(description="日別 アクセス実績(新) PV/DAU per shop × device (No.19).");

-- Product reviews (No.15) — daily delta of newly posted reviews
CREATE TABLE IF NOT EXISTS `analytics_layer.product_reviews` (
  review_date         DATE    NOT NULL OPTIONS(description="投稿日"),
  shop_name           STRING           OPTIONS(description="ショップ名"),
  item_code           STRING           OPTIONS(description="商品コード"),
  product_code        STRING           OPTIONS(description="ブランド品番"),
  product_name        STRING           OPTIONS(description="商品名"),
  parent_category     STRING,
  child_category      STRING,
  rating              INT64            OPTIONS(description="評価 1-5"),
  review_title        STRING,
  review_body         STRING,
  display_status      STRING           OPTIONS(description="表示指定 (公開/非公開)"),
  reviewer_attr       STRING           OPTIONS(description="レビュワー属性 (性別/年代等)"),
  source_file         STRING,
  ingested_date       DATE,
  ingested_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
PARTITION BY review_date
CLUSTER BY shop_name, item_code
OPTIONS(description="商品レビュー 日次差分 (No.15).");

-- Coupon exclusion list per brand per day
CREATE TABLE IF NOT EXISTS `analytics_layer.coupon_exclusion` (
  exclusion_date      DATE    NOT NULL OPTIONS(description="Date of coupon event"),
  brand_name          STRING           OPTIONS(description="ブランド名 (extracted from filename)"),
  item_code           STRING  NOT NULL OPTIONS(description="商品コード"),
  product_code        STRING           OPTIONS(description="ブランド品番"),
  excluded_zozotown   BOOL             OPTIONS(description="除外対象フラグ（ZOZOTOWN）"),
  excluded_yahoo      BOOL             OPTIONS(description="除外対象フラグ（Yahoo!ショッピング）"),
  source_file         STRING,
  ingested_date       DATE,
  ingested_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
PARTITION BY exclusion_date
CLUSTER BY brand_name, item_code
OPTIONS(description="Products excluded from coupon campaigns per brand per day (No.18).");
