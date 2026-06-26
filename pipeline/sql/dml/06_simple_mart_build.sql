-- =============================================================================
-- Simple mart builder — populates mart_layer.order_analysis for DATE(@target_date).
-- Phase 1 minimal version: builds from 5 analytics tables we have data in,
-- without using color_code (deprecated) or trend_coefficient (Phase 2).
--
-- Idempotent: deletes the target_date partition first, then inserts fresh.
-- Parameters:
--   DATE(@target_date)  DATE
-- =============================================================================

-- Step 1: Wipe the partition for the target date (idempotent rerun)
DELETE FROM `mart_layer.order_analysis`
WHERE analysis_date = DATE(@target_date);

-- Step 2: Insert fresh (explicit column list to be safe against schema reordering)
INSERT INTO `mart_layer.order_analysis` (
  analysis_date, product_code, product_name, color_code, color_name, size, sku_code,
  maker_color_code, shelf_type,
  inventory, incoming_stock, reserved_quantity, reservations_pending, free_inventory,
  sales_cumulative, favorites_total, sales_7d, sales_30d, sales_2w, sales_ytd,
  monthly_sales, daily_sales_30d,
  daily_velocity_7d, daily_velocity_30d,
  stock_days_7d, monthly_gap, trend_coefficient,
  cost_price, retail_price, selling_price, proper_price,
  period_revenue, period_total_cost, gross_margin_pct,
  recommended_order_qty, order_urgency, days_to_stockout,
  arrival_date,
  computed_at
)
-- =============================================================================
-- フリー在庫（クライアント最終仕様 2026-05-15・簡素化版）:
--   予約受付数 × 0.7 の逆算は不要。入荷残をそのまま使う。
--   通常タイプ・予約タイプ共通で:
--       フリー在庫 = 在庫 + 入荷残 − 予約未処理
--   ・在庫        = 倉庫在庫（inventory_snapshot）
--   ・入荷残      = 既発注未入荷（incoming_stock, MMS/Tableau）
--   ・予約未処理  = 予約受注がついている分（予約管理一覧の未処理数 = quantity）
--   通常タイプは予約未処理が無いので実質「在庫 + 入荷残」になる。
-- =============================================================================
WITH
-- Latest inventory snapshot
inv AS (
  SELECT
    sku_code,
    product_code,
    product_name,
    color_name,
    size,
    shop_name,
    SUM(stock_quantity) AS inventory,
    MAX(snapshot_date)  AS snapshot_date
  FROM `analytics_layer.inventory_snapshot`
  WHERE snapshot_date = DATE(@target_date)
  GROUP BY sku_code, product_code, product_name, color_name, size, shop_name
),

-- Stock analysis (No.6 在庫分析CSV)
-- 「販売可能数 (S列)」 = ユーザーが購入できる状態の在庫 (受注未出荷を除外).
-- 通常タイプはこれを在庫として表示。予約タイプは 0 に置換する (client 2026-06-09).
-- 販売タイプ (通常/予約) は product_master に存在するので JOIN で取得.
stock_an AS (
  SELECT
    sku_code,
    product_code,
    product_name,
    color_name,
    size,
    shop_name,
    available_qty,                              -- S列: 販売可能数 (=「在庫」表示の元)
    price_type,
    sales_7d,
    sales_30d,
    favorites,
    arrival_date,                               -- 最終入荷日 (発注管理表 仕様 行31)
    unit_price          AS reference_price,
    proper_price
  FROM `analytics_layer.stock_analysis`
  WHERE snapshot_date = DATE(@target_date)
),

-- Product master — sale_type (通常 / 予約 / 未販売)
pm_sale AS (
  SELECT
    UPPER(TRIM(product_code)) AS j_product_code,
    UPPER(TRIM(sku_code))     AS j_sku_code,
    ANY_VALUE(sale_type)      AS sale_type
  FROM `analytics_layer.product_master`
  WHERE product_code IS NOT NULL
    AND sku_code     IS NOT NULL
  GROUP BY j_product_code, j_sku_code
),

-- 売上集計（粗利率計算の基礎）
-- 受注CSV由来の sales_daily を 30日間集計
-- 「合計金額（税抜）」がそのまま period_revenue として使える
-- (= 注文時の販売価格 × 注文数 を全注文で集計したもの)
sales_period AS (
  SELECT
    product_code,
    sku_code,
    SUM(sales_amount)   AS period_revenue,    -- 合計金額（税抜）の30日合計
    SUM(sales_quantity) AS period_units_sold
  FROM `analytics_layer.sales_daily`
  WHERE sale_date BETWEEN DATE_SUB(DATE(@target_date), INTERVAL 30 DAY)
                      AND DATE(@target_date)
    AND sales_quantity > 0
  GROUP BY product_code, sku_code
),

-- 販売速度の算出（クライアント要望対応 2026-05-15）
-- 「既存品番の新色リリース」問題への対応:
--   シタテルの確定リリース日は【品番ごと】のため、同一品番でも
--   ブラック(既存・30日実績)とベージュ(新色・7日実績)を区別できず、
--   ÷7だとブラック過大評価／÷30だとベージュ過少評価になってしまう。
--
--   解決: 有効販売開始日を【SKU(=カラー×サイズ)ごとの実初回受注日】とする。
--   受注データ上の実際の初回注文日なので、ZOZOの不正確な日付項目
--   （受注CSV販売開始日＝最新更新日 等）とは別物で信頼できる。
--   カラー単位で別SKUのため、ブラックは自分の30日で÷30、
--   ベージュは自分の7日で÷7 と、それぞれ公平に評価される。
--   （過去に販売実績のある品番が再販でスパイクしても、初回受注日は
--     古いままなので「新商品」と誤判定されない）
sku_velocity AS (
  SELECT
    sd.product_code,
    sd.sku_code,
    MIN(sd.sale_date) AS first_sale_date,
    MIN(sd.sale_date) AS effective_start_date,   -- SKU(カラー)ごとの実初回受注日
    SUM(CASE WHEN sd.sale_date >= DATE_SUB(DATE(@target_date), INTERVAL 30 DAY)
             THEN sd.sales_quantity ELSE 0 END) AS units_30d,
    SUM(CASE WHEN sd.sale_date >= DATE_SUB(DATE(@target_date), INTERVAL 7 DAY)
             THEN sd.sales_quantity ELSE 0 END) AS units_7d
  FROM `analytics_layer.sales_daily` sd
  WHERE sd.sale_date <= DATE(@target_date)
    AND sd.sales_quantity > 0
  GROUP BY sd.product_code, sd.sku_code
),

-- 予約管理一覧(ReserveList)由来の予約未処理
--   reservations_pending = 予約受注がついている分（予約管理一覧の未処理数 = quantity 列）
--   ⚠️ Bug fix (2026-05-21): JOIN MUST include product_code. sku_code is reused
--   across ~900 different products (e.g. 'L18' appears in 889 different
--   products across 5 shops). Joining on sku_code alone bled other products'
--   reservations into every same-sku row — client reported "products with
--   zero reservations showing huge pending values".
res AS (
  SELECT
    product_code,
    sku_code,
    SUM(quantity) AS reservations_pending   -- 予約未処理
  FROM `analytics_layer.reservations`
  WHERE reservation_date = DATE(@target_date)
    AND product_code IS NOT NULL
    AND sku_code     IS NOT NULL
  GROUP BY product_code, sku_code
),

-- 入荷残（MMS/Tableau 予約管理）
--   ⚠️ JOINキー修正 (2026-05-15): 旧実装は sku_code 結合だったが、
--   Tableau予約管理の sku_code は MMS長形式（例 se6100614号30 = 品番+サイズ+
--   メーカーカラー）で ZOZOの短縮sku（例 F99）と全く別系統のため一致0件 ＝
--   入荷残が常に0になっていた。品番・カラー・サイズの正規化キーで結合する。
--   （cost_master と同じ MMS↔ZOZO SKU符号体系の不一致問題）
inc AS (
  SELECT
    UPPER(TRIM(product_code)) AS j_product_code,
    UPPER(TRIM(color_name))   AS j_color_name,
    UPPER(TRIM(size))         AS j_size,
    SUM(incoming_qty)         AS incoming_stock
  FROM `analytics_layer.incoming_stock`
  WHERE source_date = DATE(@target_date)
    -- 顧客No.5 (2026-06-24 山口): 着荷 > target_date+180日 の入荷予定は「将来の発注」と
    --   みなしフリー在庫に含めない（過大計上＝過小発注の防止）。
    --   着荷日なし・期日超過(過去日)は従来どおり含める。
    AND (earliest_arrival_date IS NULL
         OR SAFE_CAST(REPLACE(earliest_arrival_date,'/','-') AS DATE)
            <= DATE_ADD(DATE(@target_date), INTERVAL 180 DAY))
  GROUP BY j_product_code, j_color_name, j_size
),

-- Cost master (MMS 評価額一覧, SKU-level)
-- ⚠️ Bug fix (2026-05-20): cost_master joined on (product_code, color, size)
--   instead of (product_code, sku_code). Previous JOIN dropped ~80% of cost
--   matches because inventory_sku exports ZOZO-short sku_codes (e.g. 'F8') but
--   cost_master inherits the CS品番 from MMS evaluation export, which doesn't
--   line up row-for-row with the inventory_sku format. The composite color/
--   size key matches reliably (same key already used for incoming_stock).
-- クライアント仕様 (2026-06-18): MMS は「最新評価額(単価)」を SKU 単位で拾う。
-- AVG ではなく source_date 最新の1件を採用 (平均原価 例ファイルで検証済み:
-- sc491 各SKUの最新評価額 → 受注数で加重 → 合計÷合計枚数 = 621.49 が再現)。
cost AS (
  SELECT
    j_product_code, j_color_name, j_size,
    ARRAY_AGG(cost_price   ORDER BY source_date DESC LIMIT 1)[OFFSET(0)] AS cost_price,
    ARRAY_AGG(retail_price ORDER BY source_date DESC LIMIT 1)[OFFSET(0)] AS retail_price
  FROM (
    SELECT
      UPPER(TRIM(product_code)) AS j_product_code,
      UPPER(TRIM(color_name))   AS j_color_name,
      UPPER(TRIM(size))         AS j_size,
      cost_price, retail_price, source_date
    FROM `analytics_layer.cost_master`
    WHERE product_code IS NOT NULL
      AND color_name  IS NOT NULL
      AND size        IS NOT NULL
      AND valid_to IS NULL    -- ▼ only currently-active cost rows (SCD2)
  )
  GROUP BY j_product_code, j_color_name, j_size
),

-- PF手数料 (Google Sheet, product_code-level 下代)
-- Per client direction (2026-06-09): primary cost source. MMS cost_master
-- (above) is the per-SKU fallback when a product_code is absent in PF fee.
-- We pick the row with the most-recent snapshot per product.
pf_cost AS (
  SELECT
    UPPER(TRIM(product_code)) AS j_product_code,
    -- Some products have multiple PF rows (per shop) — take the last by
    -- snapshot_date and any non-null cost.
    ANY_VALUE(cost_price)              AS pf_cost_price
  FROM `analytics_layer.pf_fee_master`
  WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM `analytics_layer.pf_fee_master`)
    AND cost_price IS NOT NULL
    AND cost_price > 0
  GROUP BY j_product_code
),

-- Daily sparkline (last 30 days)
-- ⚠️ Bug fix (2026-05-21): include product_code so cross-product sku_code
-- collisions don't blend daily sales of unrelated products.
spark AS (
  SELECT
    product_code,
    sku_code,
    ARRAY_AGG(STRUCT(sale_date, sales_quantity AS qty)
              ORDER BY sale_date) AS daily_sales_30d
  FROM (
    SELECT
      product_code,
      sku_code,
      sale_date,
      SUM(sales_quantity) AS sales_quantity
    FROM `analytics_layer.sales_daily`
    WHERE sale_date BETWEEN DATE_SUB(DATE(@target_date), INTERVAL 30 DAY) AND DATE(@target_date)
      AND product_code IS NOT NULL
      AND sku_code     IS NOT NULL
    GROUP BY product_code, sku_code, sale_date
  )
  GROUP BY product_code, sku_code
),

-- 全テーブルを結合し、素の項目＋フリー在庫計算の素材を組み立てる
assembled AS (
  SELECT
    DATE(@target_date)                                      AS analysis_date,
    COALESCE(inv.product_code, stock_an.product_code, '')   AS product_code,
    COALESCE(inv.product_name, stock_an.product_name)       AS product_name,
    ''                                                      AS color_code,        -- legacy compatibility
    COALESCE(inv.color_name, stock_an.color_name)           AS color_name,
    COALESCE(inv.size, stock_an.size, '')                   AS size,
    COALESCE(inv.sku_code, stock_an.sku_code)               AS sku_code,
    COALESCE(inv.shop_name, stock_an.shop_name)             AS maker_color_code,
    '通常'                                                  AS shelf_type,

    -- 在庫 (client spec 2026-06-09):
    --   ・通常タイプ → 在庫分析の販売可能数 (available_qty)
    --   ・予約タイプ → 0
    -- 倉庫在庫 (inventory_snapshot.stock_quantity) は受注済未出荷を含むため不採用.
    CASE WHEN pm_sale.sale_type = '予約' THEN 0
         ELSE COALESCE(stock_an.available_qty, 0)
    END                                                     AS inventory,
    COALESCE(inc.incoming_stock, 0)                         AS incoming_stock,
    0                                                       AS reserved_quantity,
    COALESCE(res.reservations_pending, 0)                   AS reservations_pending,
    pm_sale.sale_type                                       AS pm_sale_type,

    0                                                       AS sales_cumulative,
    COALESCE(stock_an.favorites, 0)                         AS favorites_total,
    stock_an.arrival_date                                   AS arrival_date,
    -- 販売数 (client spec 2026-06-09 follow-up):
    -- 「実績は受注CSV統一が望ましい」→ 受注CSV由来の sv_units を採用.
    -- daily_velocity との一貫性 (sales_X ÷ X = velocity) を最優先.
    COALESCE(sku_velocity.units_7d, 0)                      AS sales_7d,
    COALESCE(sku_velocity.units_30d, 0)                     AS sales_30d,
    COALESCE(sku_velocity.units_7d, 0)                      AS sales_2w,
    COALESCE(sku_velocity.units_30d, 0)                     AS sales_ytd,

    CAST([] AS ARRAY<STRUCT<month STRING, qty INT64>>)      AS monthly_sales,
    COALESCE(spark.daily_sales_30d, [])                     AS daily_sales_30d,

    -- 有効販売日数（シタテル確定リリース日 or 実初回販売日 ベース、最大30/7日）
    LEAST(7,  DATE_DIFF(DATE(@target_date), sku_velocity.effective_start_date, DAY) + 1) AS effective_days_7d,
    LEAST(30, DATE_DIFF(DATE(@target_date), sku_velocity.effective_start_date, DAY) + 1) AS effective_days_30d,
    sku_velocity.units_7d                                   AS sv_units_7d,
    sku_velocity.units_30d                                  AS sv_units_30d,

    -- Cost lookup (client spec 2026-06-09):
    --   1) PF手数料表「下代 税抜」 by product_code  (primary)
    --   2) MMS cost_master           by (product, color, size) (fallback)
    COALESCE(pf_cost.pf_cost_price, cost.cost_price)        AS cost_price,
    cost.retail_price,                                                            -- 上代（参考、ほぼ NULL）
    stock_an.reference_price                                AS selling_price,     -- 在庫分析の単価（参考のみ・前日時点）
    stock_an.proper_price                                   AS proper_price,      -- プロパー価格（参考）

    -- ▼ 粗利率（30日集計ベース、クライアント仕様 2026-05-13）
    sales_period.period_revenue                             AS period_revenue,
    COALESCE(pf_cost.pf_cost_price, cost.cost_price) * sales_period.period_units_sold AS period_total_cost,
    SAFE_DIVIDE(
      sales_period.period_revenue - (COALESCE(pf_cost.pf_cost_price, cost.cost_price) * sales_period.period_units_sold),
      NULLIF(sales_period.period_revenue, 0)
    ) * 100                                                  AS gross_margin_pct

  FROM inv
  FULL OUTER JOIN stock_an
    ON  stock_an.sku_code     = inv.sku_code
   AND  stock_an.product_code = inv.product_code
  LEFT JOIN res
    ON  res.sku_code     = COALESCE(inv.sku_code,     stock_an.sku_code)
   AND  res.product_code = COALESCE(inv.product_code, stock_an.product_code)
  LEFT JOIN inc
    ON  inc.j_product_code = UPPER(TRIM(COALESCE(inv.product_code, stock_an.product_code)))
   AND  inc.j_color_name   = UPPER(TRIM(COALESCE(inv.color_name,   stock_an.color_name)))
   AND  inc.j_size         = UPPER(TRIM(COALESCE(inv.size,         stock_an.size)))
  LEFT JOIN cost
    ON  cost.j_product_code = UPPER(TRIM(COALESCE(inv.product_code, stock_an.product_code)))
   AND  cost.j_color_name   = UPPER(TRIM(COALESCE(inv.color_name,   stock_an.color_name)))
   AND  cost.j_size         = UPPER(TRIM(COALESCE(inv.size,         stock_an.size)))
  LEFT JOIN pf_cost
    ON  pf_cost.j_product_code = UPPER(TRIM(COALESCE(inv.product_code, stock_an.product_code)))
  LEFT JOIN pm_sale
    ON  pm_sale.j_product_code = UPPER(TRIM(COALESCE(inv.product_code, stock_an.product_code)))
   AND  pm_sale.j_sku_code     = UPPER(TRIM(COALESCE(inv.sku_code,     stock_an.sku_code)))
  LEFT JOIN sales_period
    ON  sales_period.sku_code     = COALESCE(inv.sku_code,     stock_an.sku_code)
   AND  sales_period.product_code = COALESCE(inv.product_code, stock_an.product_code)
  LEFT JOIN sku_velocity
    ON  sku_velocity.sku_code     = COALESCE(inv.sku_code,     stock_an.sku_code)
   AND  sku_velocity.product_code = COALESCE(inv.product_code, stock_an.product_code)
  LEFT JOIN spark
    ON  spark.sku_code     = COALESCE(inv.sku_code,     stock_an.sku_code)
   AND  spark.product_code = COALESCE(inv.product_code, stock_an.product_code)
  WHERE COALESCE(inv.sku_code, stock_an.sku_code) IS NOT NULL
),

-- ▼ フリー在庫（クライアント最終仕様 2026-05-15・簡素化版）
--   通常タイプ・予約タイプ共通:
--     フリー在庫 = 在庫 + 入荷残 − 予約未処理
--   （0.7逆算・予約受付数・販売前予約受付数は使わない）
with_ffi AS (
  SELECT
    a.*,
    a.inventory + a.incoming_stock - a.reservations_pending  AS free_inventory,
    -- 販売速度 (client spec 2026-06-09 follow-up):
    -- 実績は受注CSV統一 → sales_X ÷ X (X=7,30) で算出。L列 ÷ 期間 = N列 と一致。
    -- (新色SKUの effective_days 補正は廃止。欠品時シミュレーションは別途定義予定)
    SAFE_DIVIDE(a.sales_7d, 7.0)    AS daily_velocity_7d,
    SAFE_DIVIDE(a.sales_30d, 30.0)  AS daily_velocity_30d
  FROM assembled a
)

SELECT
  analysis_date, product_code, product_name, color_code, color_name, size, sku_code,
  maker_color_code, shelf_type,
  inventory, incoming_stock, reserved_quantity, reservations_pending,
  free_inventory,
  sales_cumulative, favorites_total, sales_7d, sales_30d, sales_2w, sales_ytd,
  monthly_sales, daily_sales_30d,
  daily_velocity_7d, daily_velocity_30d,
  SAFE_DIVIDE(free_inventory, NULLIF(daily_velocity_7d, 0))  AS stock_days_7d,
  0                                                          AS monthly_gap,
  1.0                                                        AS trend_coefficient,
  cost_price, retail_price, selling_price, proper_price,
  period_revenue, period_total_cost, gross_margin_pct,

  -- 推奨発注数: MAX(0, CEIL(8週 × 7日 × 30日販売速度 − フリー在庫))
  --   入荷残はフリー在庫に既に含まれるため、ここで重ねて引かない。
  GREATEST(0, CAST(CEIL(
      8 * 7 * daily_velocity_30d - free_inventory
  ) AS INT64))                                               AS recommended_order_qty,

  -- 在庫ステータス（顧客定義 2026・通年品基準）: 欠品=フリー在庫≤0 / 不足=在庫日数<90 / 過剰=在庫日数≥271
  -- ※季節品は本来シーズン期限前消化が基準だが、季節区分データ未整備のため暫定で通年90日を適用。
  CASE
    WHEN free_inventory <= 0 THEN 'CRITICAL'
    WHEN SAFE_DIVIDE(free_inventory, NULLIF(daily_velocity_7d, 0)) < 90 THEN 'WARNING'
    WHEN SAFE_DIVIDE(free_inventory, NULLIF(daily_velocity_7d, 0)) >= 271 THEN 'OVERSTOCK'
    ELSE 'OK'
  END                                                        AS order_urgency,

  CAST(SAFE_DIVIDE(free_inventory, NULLIF(daily_velocity_7d, 0)) AS INT64) AS days_to_stockout,
  arrival_date,
  CURRENT_TIMESTAMP()                                        AS computed_at
FROM with_ffi;
