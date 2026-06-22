"""
MMS (Merchandise Management System) Extractor

Handles cost and inventory data from the MMS system.
MMS account credentials are provided by the client (see アカウント情報 sheet
in AI商品発注判断支援プロジェクト.xlsx).

Data sources:
  No.10 原価         : 在庫管理＞ショップ別評価一覧 → 評価額一覧-MMS.csv
                       Contains cost_price per SKU. Note: duplicate SKUs possible.
  No.49 着荷データ   : 発注管理＞発注書一覧 → mms_order_data.yyyyMMddHHmmss.csv
                       Contains incoming_stock (入荷残) per SKU.

⚠️  MMS API availability is not confirmed. This extractor assumes CSV export
    upload to GCS as the ingestion method. Update _fetch_via_api() if an API
    becomes available.
"""
from __future__ import annotations

import csv
import io
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── Field maps ────────────────────────────────────────────────────────────────

# No.10 原価 (評価額一覧-MMS)
# Actual column names confirmed from client file:
# MMS商品ID, ショップID, ブランド品番, CS品番, カラー名, サイズ名, 最新評価額(単価), 更新日
_COST_FIELD_MAP = {
    "CS品番":              "sku_code",
    "ブランド品番":        "product_code",
    "カラー名":            "color_name",
    "サイズ名":            "size",
    "最新評価額(単価)":    "cost_price",
    "MMS商品ID":           "mms_product_id",
    "ショップID":          "shop_id",
    "更新日":              "updated_date",
}

# No.49 着荷データ (mms_order_data.yyyyMMddHHmmss.csv)
# Actual column names confirmed from client file (cp932 encoding, 38 columns):
# #, 枝番, 発注年月日, 発注区分, 発注書No, 発注先会社, 発注先部門, ショップ, 親カテゴリ,
# 商品名, ブランド品番, CS品番, SKU品番, ZOZOカラー名, ZOZOサイズ名,
# 発注数量, 単価, 商品単価, 諸掛, 発注金額, 現状, 希望納期, 予定納期,
# 予定数量, 出荷日, 出荷数量, 納品書番号, ZOZO計上日, 着荷数量, ...
# 現状 values: 発注登録済み / 納期回答あり / 出荷あり / 着荷あり
_INCOMING_FIELD_MAP = {
    "SKU品番":             "sku_code",
    "ブランド品番":        "product_code",
    "CS品番":              "cs_code",
    "ZOZOカラー名":        "color_name",
    "ZOZOサイズ名":        "size",
    "商品名":              "product_name",
    "ショップ":            "shop_name",
    "発注数量":            "order_qty",
    "予定数量":            "planned_qty",
    "着荷数量":            "arrived_qty",
    "現状":                "status",
    "希望納期":            "expected_arrival_date",
    "予定納期":            "scheduled_arrival_date",
    "発注年月日":          "order_date",
    "発注書No":            "po_number",
}


def _read_csv(data: bytes) -> list[dict[str, str]]:
    # MMS files use cp932 (Windows Japanese Shift-JIS superset)
    for enc in ("cp932", "utf-8-sig", "shift_jis", "utf-8"):
        try:
            text = data.decode(enc)
            reader = csv.DictReader(io.StringIO(text))
            return list(reader)
        except UnicodeDecodeError:
            continue
    raise ValueError("Cannot decode MMS CSV — check file encoding")


def _to_float(v: str | None) -> float | None:
    if not v:
        return None
    try:
        # Handle Japanese yen format: \1,100 or ¥1,100
        cleaned = str(v).replace(",", "").replace("\\", "").replace("¥", "").strip()
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _to_int(v: str | None) -> int | None:
    if not v:
        return None
    try:
        return int(str(v).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


class MMSExtractor:
    """
    Parse MMS CSV exports into dicts matching our BigQuery schema.
    All parse_* methods accept raw bytes (as read from GCS after upload).
    """

    def parse_cost_master(
        self,
        data: bytes,
        valid_from: str,
    ) -> list[dict[str, Any]]:
        """
        No.10 原価 — 評価額一覧-MMS CSV.

        Returns records for analytics_layer.cost_master.
        Deduplication: if duplicate SKUs exist (as noted by client), we keep
        the row with the highest cost_price (most conservative estimate).
        """
        rows = _read_csv(data)
        logger.info("Parsing MMS cost master CSV: %d raw rows", len(rows))

        # Dedup key MUST include product_code: the same CS品番 ('S365', 'M18',
        # etc.) is reused across many different products/shops in MMS. Deduping
        # on sku_code alone collapses them, losing ~90% of legitimate cost rows
        # and breaking the mart's (product_code, color, size) JOIN.
        seen: dict[tuple, dict[str, Any]] = {}
        for r in rows:
            sku = (r.get("CS品番") or "").strip()
            if not sku:
                continue

            cost   = _to_float(r.get("最新評価額(単価)"))
            retail = _to_float(r.get("上代"))  # not in this file; may be None

            product_code = (r.get("ブランド品番") or "").strip() or None
            color_name   = (r.get("カラー名") or "").strip() or None
            size_v       = (r.get("サイズ名") or "").strip() or None

            record: dict[str, Any] = {
                "sku_code":         sku,
                "product_code":     product_code,
                "color_name":       color_name,
                "size":             size_v,
                "cost_price":       cost,
                "retail_price":     retail,
                "valuation_price":  cost,
                "mms_product_id":   (r.get("MMS商品ID") or "").strip() or None,
                "shop_id":          (r.get("ショップID") or "").strip() or None,
                "updated_date":     (r.get("更新日") or "").strip() or None,
                "valid_from":       valid_from,
                "valid_to":         None,
                "source_file":      "mms_cost_master",
            }

            # Composite dedup key. Same product can also have the same
            # (product_code, color, size) across shops (because the SAME
            # physical SKU may be stocked in multiple shops with different
            # valuation prices) — keep the highest cost as before.
            key = (product_code or "", color_name or "", size_v or "", sku)
            if key not in seen:
                seen[key] = record
            else:
                existing_cost = seen[key].get("cost_price") or 0
                if (cost or 0) > existing_cost:
                    seen[key] = record

        result = list(seen.values())
        logger.info("Parsed %d deduplicated cost records "
                    "(composite key product_code+color+size+sku)", len(result))
        return result

    def parse_incoming_stock(
        self,
        data: bytes,
        source_date: str,
    ) -> list[dict[str, Any]]:
        """
        No.49 着荷データ — mms_order_data CSV.

        Returns records representing incoming_stock (入荷残) per SKU.
        Only confirmed / in-transit orders are included (not cancelled).
        """
        rows = _read_csv(data)
        logger.info("Parsing MMS incoming stock CSV: %d raw rows", len(rows))

        # Aggregate by SKU (multiple POs may exist per SKU)
        by_sku: dict[str, dict[str, Any]] = {}
        for r in rows:
            sku = (r.get("SKU品番") or r.get("CS品番") or "").strip()
            if not sku:
                continue

            # 現状 values: 発注登録済み / 納期回答あり / 出荷あり / 着荷あり
            # Only count rows NOT yet fully arrived as incoming_stock
            status = (r.get("現状") or "").strip()
            if status == "着荷あり":
                continue  # already received, not incoming

            # 入荷残 = 発注数量 − 着荷数量
            order_qty   = _to_int(r.get("発注数量")) or 0
            arrived_qty = _to_int(r.get("着荷数量")) or 0
            incoming    = max(0, order_qty - arrived_qty)
            if sku not in by_sku:
                by_sku[sku] = {
                    "sku_code":              sku,
                    "product_code":          (r.get("ブランド品番") or "").strip() or None,
                    "color_name":            (r.get("ZOZOカラー名") or "").strip() or None,
                    "size":                  (r.get("ZOZOサイズ名") or "").strip() or None,
                    "product_name":          (r.get("商品名") or "").strip() or None,
                    "incoming_qty":          0,
                    "earliest_arrival_date": r.get("希望納期") or r.get("予定納期") or None,
                    "source_date":           source_date,
                    "source_file":           "mms_incoming_stock",
                }
            by_sku[sku]["incoming_qty"] += incoming

            # Track earliest expected arrival
            arrival = r.get("希望納期") or r.get("予定納期") or ""
            current_earliest = by_sku[sku]["earliest_arrival_date"] or ""
            if arrival and (not current_earliest or arrival < current_earliest):
                by_sku[sku]["earliest_arrival_date"] = arrival

        result = list(by_sku.values())
        logger.info("Parsed %d incoming-stock records (%d SKUs)", len(result), len(by_sku))
        return result
