-- Migration 002: Add arrival_date, favorites, barcode to analytics_layer.stock_analysis
-- Added 2026-06-17 per client request: enable ALL optional columns when downloading
-- 在庫分析データ from ZOZO BO (ArriveDT + FavoriteList + Barcode checkboxes).
--
-- Run once against production BigQuery:
--   bq query --project_id=mono-back-office-system --use_legacy_sql=false < 002_stock_analysis_add_cols.sql

ALTER TABLE `analytics_layer.stock_analysis`
  ADD COLUMN IF NOT EXISTS arrival_date STRING OPTIONS(description="継続入荷日 (ArriveDT)"),
  ADD COLUMN IF NOT EXISTS favorites    INT64  OPTIONS(description="お気に入り登録数 (SKU-level, 30d window)"),
  ADD COLUMN IF NOT EXISTS barcode      STRING OPTIONS(description="バーコード (slash-separated if multiple)");
