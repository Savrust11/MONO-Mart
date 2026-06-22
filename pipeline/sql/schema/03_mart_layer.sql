-- =============================================================================
-- MART LAYER: Aggregated output tables — rebuilt fully every night
-- These power the dashboard and Excel export. Do not write to these manually.
-- =============================================================================

-- Main order analysis table — mirrors and extends the Excel 分析表
CREATE TABLE IF NOT EXISTS `mart_layer.order_analysis` (
  analysis_date       DATE    NOT NULL OPTIONS(description="Business date of this snapshot"),
  product_code        STRING  NOT NULL OPTIONS(description="品番"),
  product_name        STRING           OPTIONS(description="商品名"),
  color_code          STRING  NOT NULL,
  color_name          STRING           OPTIONS(description="カラー"),
  size                STRING  NOT NULL,
  sku_code            STRING           OPTIONS(description="CS品番"),
  maker_color_code    STRING           OPTIONS(description="メーカーカラー名"),
  shelf_type          STRING           OPTIONS(description="店舗棚情報"),

  -- Supply fields (在庫関連)
  inventory           INT64            OPTIONS(description="在庫 — ZOZO倉庫の総在庫数（倉庫在庫CSV）"),
  incoming_stock      INT64            OPTIONS(description="入荷残 — 既に発注済で未入荷の数量（MMS/Tableau）。フリー在庫に加算"),
  reserved_quantity   INT64            OPTIONS(description="引当済 — 予約未処理と同義のため未使用（0固定）"),
  reservations_pending INT64           OPTIONS(description="予約未処理 — 予約受注がついている分（予約管理一覧の未処理数 quantity）"),
  free_inventory      INT64            OPTIONS(description="フリー在庫 = 在庫 + 入荷残 − 予約未処理（通常/予約タイプ共通・クライアント仕様 2026-05-15）"),

  -- Demand fields (販売関連)
  sales_cumulative    INT64            OPTIONS(description="販売数(累計) — all-time sales"),
  favorites_total     INT64            OPTIONS(description="お気に入り数(累計)"),
  sales_7d            INT64            OPTIONS(description="7日間販売数"),
  sales_30d           INT64            OPTIONS(description="一ヶ月販売数"),
  sales_2w            INT64            OPTIONS(description="直近2週間"),
  sales_ytd           INT64            OPTIONS(description="年度累計 (2025年)"),

  -- Monthly sales by month (dynamically computed, stored as struct for efficiency)
  monthly_sales       ARRAY<STRUCT<month STRING, qty INT64>>
                                       OPTIONS(description="Monthly sales breakdown [{month:'2025-09', qty:46}, ...]"),

  -- Daily sales for the last 30 days (for sparkline chart)
  daily_sales_30d     ARRAY<STRUCT<sale_date DATE, qty INT64>>
                                       OPTIONS(description="Last 30 days daily sales for sparkline"),

  -- Velocity（販売開始<30日の品番は実販売日数で割って公平な速度を算出）
  daily_velocity_7d   FLOAT64          OPTIONS(description="日次販売速度(7日) = 直近7日販売数 / MIN(7, SKU別実販売日数)"),
  daily_velocity_30d  FLOAT64          OPTIONS(description="日次販売速度(30日) = 直近30日販売数 / MIN(30, SKU別実販売日数)。SKU(=カラー×サイズ)毎の実初回受注日基準なので、同一品番の既存色は÷30・新色は実日数で公平に評価"),

  -- Derived KPIs
  stock_days_7d       FLOAT64          OPTIONS(description="7日間分 = free_inventory / daily_velocity_7d (days of stock)"),
  monthly_gap         INT64            OPTIONS(description="1ヶ月差分 = free_inventory - sales_30d"),
  trend_coefficient   FLOAT64          OPTIONS(description="トレンド係数 = daily_velocity_7d / daily_velocity_30d"),

  -- Cost & margin
  cost_price          NUMERIC          OPTIONS(description="SKU 原価 in JPY (MMS 評価額)"),
  retail_price        NUMERIC          OPTIONS(description="上代 (reference only — typically NULL)"),
  selling_price       NUMERIC          OPTIONS(description="参考販売価格 (前日時点の在庫分析単価。粗利率の計算には使わない)"),
  proper_price        NUMERIC          OPTIONS(description="プロパー価格 in JPY (reference)"),
  period_revenue      NUMERIC          OPTIONS(description="30日合計売上 (受注CSV 合計金額（税抜）の合算)"),
  period_total_cost   NUMERIC          OPTIONS(description="30日合計原価 (SKU原価 × 注文数)"),
  gross_margin_pct    FLOAT64          OPTIONS(description="粗利率 = (period_revenue - period_total_cost) / period_revenue × 100"),

  -- Recommendation
  recommended_order_qty INT64          OPTIONS(description="推奨発注数 = MAX(0, CEIL(8週×7日×30日販売速度 − フリー在庫))。入荷残はフリー在庫に含むため重複控除しない。30日速度はSKU(カラー)毎の実販売日数で算出"),
  order_urgency       STRING           OPTIONS(description="CRITICAL / WARNING / OK / OVERSTOCK"),
  days_to_stockout    FLOAT64          OPTIONS(description="欠品まで何日か (NULL if velocity = 0)"),

  -- Pipeline metadata
  computed_at         TIMESTAMP
)
PARTITION BY analysis_date
CLUSTER BY product_code, color_code, size
OPTIONS(description="Main order analysis mart. Rebuilt nightly. Powers dashboard and Excel export.");

-- Reorder alerts — subset of order_analysis filtered to actionable items
CREATE TABLE IF NOT EXISTS `mart_layer.reorder_alerts` (
  analysis_date         DATE    NOT NULL,
  product_code          STRING  NOT NULL,
  product_name          STRING,
  color_code            STRING  NOT NULL,
  color_name            STRING,
  size                  STRING  NOT NULL,
  sku_code              STRING,
  order_urgency         STRING,
  stock_days_7d         FLOAT64,
  days_to_stockout      FLOAT64,
  free_inventory        INT64,
  incoming_stock        INT64,
  recommended_order_qty INT64,
  trend_coefficient     FLOAT64,
  daily_velocity_7d     FLOAT64,
  estimated_lost_revenue NUMERIC  OPTIONS(description="推定機会損失 = MAX(0, -monthly_gap) × retail_price"),
  computed_at           TIMESTAMP
)
PARTITION BY analysis_date
OPTIONS(description="Reorder alert items only. CRITICAL and WARNING urgencies, sorted by days_to_stockout.");

-- Pipeline run audit log
CREATE TABLE IF NOT EXISTS `monitoring.pipeline_runs` (
  run_id         STRING    NOT NULL OPTIONS(description="UUID for this pipeline run"),
  run_date       DATE      NOT NULL OPTIONS(description="Target date being processed"),
  step           STRING    NOT NULL OPTIONS(description="Pipeline step name"),
  status         STRING    NOT NULL OPTIONS(description="success / failed / skipped"),
  rows_processed INT64,
  duration_ms    INT64,
  error_message  STRING,
  started_at     TIMESTAMP NOT NULL,
  finished_at    TIMESTAMP
)
PARTITION BY run_date
OPTIONS(description="Audit log for all pipeline runs. Never delete entries.");
