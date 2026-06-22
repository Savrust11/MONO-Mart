"""
sitateru Extractor

Handles SKU master CSV downloaded from sitateru Cloud.

Download path:
  sitateru Cloud → アイテム一覧 → 一括処理 → アイテムSKUの一括登録・変更

File format:
  Encoding : UTF-8 BOM (utf-8-sig)
  Separator: comma
  Layout   : wide — 4 fixed columns + up to 10 SKU groups per row

Fixed columns:
  アイテムID, アイテム名, 生産タブID, 生産タブ名

Per-SKU group (repeated ×10, suffix N = 1..10):
  色N         — color name  (e.g. "ブラック(8)")
  色コードN   — color code  (e.g. "8")
  サイズN     — size label  (e.g. "M", "F", "FREE")
  サイズコードN — size code
  SKUコードN  — sitateru internal SKU code (often empty)
  数量N       — production lot quantity

Output tables:
  analytics_layer.product_master  — one record per color×size SKU
  (数量 is stored as production_lot_qty for reference)

⚠️  SKUコード is usually empty in this export.
    Cross-reference to ZOZO CS品番 is done via MMS / Tableau using
    商品名 × 色 × サイズ matching.
"""
from __future__ import annotations

import csv
import io
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Number of SKU groups in the wide format
_MAX_SKU_GROUPS = 10

# Fixed header columns (not part of SKU groups)
_FIXED_COLS = {"アイテムID", "アイテム名", "生産タブID", "生産タブ名"}


def _clean(v: str | None) -> str | None:
    if not v:
        return None
    s = str(v).strip().strip('"')
    return s if s else None


def _to_int(v: str | None) -> int | None:
    if not v:
        return None
    try:
        return int(str(v).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def _extract_color_name(raw: str | None) -> str | None:
    """
    sitateru color field format: "ブラック(8)" or "ブラック系(10010)"
    Returns the human-readable name part before the parenthesis.
    """
    if not raw:
        return None
    raw = raw.strip()
    m = re.match(r"^(.+?)\s*\(", raw)
    return m.group(1).strip() if m else raw


def _read_csv(data: bytes) -> list[dict[str, str | None]]:
    """Decode and parse the wide-format sitateru CSV."""
    for enc in ("utf-8-sig", "utf-8", "cp932", "shift_jis"):
        try:
            text = data.decode(enc)
            reader = csv.DictReader(io.StringIO(text))
            return list(reader)
        except UnicodeDecodeError:
            continue
    raise ValueError("Cannot decode sitateru CSV — check file encoding")


class SitateruExtractor:
    """
    Parse sitateru SKU CSV exports into dicts matching our BigQuery schema.
    Accepts raw bytes (as read from GCS or local disk).
    """

    def parse_sku_master(
        self,
        data: bytes,
        source_date: str,
    ) -> list[dict[str, Any]]:
        """
        アイテムSKUの一括登録・変更 CSV.

        Melts the wide format (up to 10 SKU groups per row) into one record
        per color × size combination.

        Returns records for analytics_layer.product_master.
        """
        raw_rows = _read_csv(data)
        logger.info("Parsing sitateru SKU master CSV: %d raw rows", len(raw_rows))

        records: list[dict[str, Any]] = []

        for row in raw_rows:
            item_id   = _clean(row.get("アイテムID"))
            item_name = _clean(row.get("アイテム名"))
            tab_id    = _clean(row.get("生産タブID"))
            tab_name  = _clean(row.get("生産タブ名"))

            if not item_id:
                continue

            for n in range(1, _MAX_SKU_GROUPS + 1):
                color_raw  = _clean(row.get(f"色{n}"))
                if not color_raw:
                    # No more SKU groups in this row
                    break

                color_code = _clean(row.get(f"色コード{n}"))
                size_label = _clean(row.get(f"サイズ{n}"))
                size_code  = _clean(row.get(f"サイズコード{n}"))
                sku_code   = _clean(row.get(f"SKUコード{n}"))  # usually empty
                qty        = _to_int(row.get(f"数量{n}"))

                records.append({
                    # sitateru identifiers
                    "sitateru_item_id":    item_id,
                    "sitateru_tab_id":     tab_id,
                    "production_tab_name": tab_name,

                    # Product info
                    "product_name":        item_name,

                    # Color
                    "color_name":          _extract_color_name(color_raw),
                    "color_name_raw":      color_raw,   # full string e.g. "ブラック(8)"
                    "color_code":          color_code,

                    # Size
                    "size":                size_label,
                    "size_code":           size_code,

                    # SKU — sitateru stores half-width katakana color names here
                    # (e.g. ｱｲﾎﾞﾘｰ), NOT a ZOZO CS品番.
                    # Cross-reference to CS品番 must be done via MMS/Tableau.
                    "sku_code":            sku_code,

                    # Production quantity (発注ロット数)
                    "production_lot_qty":  qty,

                    # Metadata
                    "source_date":         source_date,
                    "source_file":         "sitateru_sku_master",
                })

        total_qty = sum(r["production_lot_qty"] or 0 for r in records)
        logger.info(
            "Parsed sitateru SKU master: %d items → %d SKU records, "
            "total production_lot_qty=%d",
            len(raw_rows), len(records), total_qty,
        )
        return records

    def parse_item_list(
        self,
        data: bytes,
        source_date: str,
    ) -> list[dict[str, Any]]:
        """
        アイテムリスト_yyyymmdd.csv (item list export — current daily download via RPA).

        140-column rich product metadata format. One product per row (not SKU-level).
        Daily merged output where the client uses RPA "アシロボ" to combine
        multiple filter queries (each capped at 2,000 records by sitateru UI).

        Maps the most useful 25 columns into structured fields.
        Cross-references to ZOZO CS品番 happen downstream via 品番 (product_code).

        Returns records for analytics_layer.sitateru_item_master.
        """
        raw_rows = _read_csv(data)
        logger.info("Parsing sitateru item list CSV: %d raw rows", len(raw_rows))

        # Column names with star-prefix etc — defined here to handle UUID-prefixed variants.
        # Some columns have format "ex:production_<uuid> ★ブランド名" — we match by suffix.
        def _find(row: dict, *suffixes: str) -> str | None:
            """Find column whose name ends with any of the given suffixes (after stripping)."""
            for k in row.keys():
                if k is None:
                    continue
                cleaned = k.strip().lstrip("﻿")
                for sfx in suffixes:
                    if cleaned.endswith(sfx):
                        return _clean(row.get(k))
            return None

        records: list[dict[str, Any]] = []
        for row in raw_rows:
            item_id = _find(row, "アイテムID")
            if not item_id:
                continue

            records.append({
                "snapshot_date":            source_date,
                "sitateru_item_id":         item_id,
                "item_name":                _find(row, "アイテム名"),
                "product_code":             _find(row, "品番"),
                "tentative_product_code":   _find(row, "★仮品番"),
                "shop_name":                _find(row, "★SHOP名"),
                "brand_name":               _find(row, "★ブランド名", "★ブランド名　"),
                "product_name":             _find(row, "★商品名"),
                "manufacturer":             _find(row, "★メーカー"),
                "business_division":        _find(row, "★事業部"),
                "planner":                  _find(row, "★企画担当"),
                "order_type":               _find(row, "★発注種別（新規/リピート/新色・柄・サイズ追加）"),
                "season":                   _find(row, "★年度/シーズン（半期ベース）"),
                "md_season":                _find(row, "★MDシーズン"),
                "md_type":                  _find(row, "★MD種別"),
                "zozo_parent_category":     _find(row, "★ZOZO商品タイプ親"),
                "zozo_child_category":      _find(row, "★ZOZO商品タイプ子"),
                "zozo_main_gender":         _find(row, "★ZOZO主性別"),
                "zozo_sub_gender":          _find(row, "★ZOZO副性別"),
                "category":                 _find(row, "★カテゴリ"),
                "promo_rank":               _find(row, "★販促ランク"),
                "color_options":            _find(row, "色展開"),
                "size_options":             _find(row, "サイズ展開"),

                "planned_delivery_date":    _find(row, "★希望納期"),
                "delivery_available_date":  _find(row, "●納品可能日"),
                "confirmed_delivery_date":  _find(row, "確定納品日"),
                "confirmed_release_date":   _find(row, "確定リリース日"),
                "release_week":             _find(row, "★リリース週"),
                "promo_week":               _find(row, "★販促週"),
                "first_delivery_date":      _find(row, "1st着日"),

                "proposed_wholesale_price": _to_int(_find(row, "★希望下代")),
                "proposed_retail_price":    _to_int(_find(row, "★希望上代")),
                "confirmed_wholesale_price":_to_int(_find(row, "確定下代")),
                "confirmed_retail_price":   _to_int(_find(row, "確定上代")),
                "actual_cost":              _to_int(_find(row, "実績コスト")),
                "total_order_qty":          _to_int(_find(row, "★発注総数")),
                "actual_delivery_qty":      _to_int(_find(row, "実納品数量")),

                "sample_quantity":          _to_int(_find(row, "サンプル数量")),
                "production_quantity":      _to_int(_find(row, "量産数量")),

                "progress_status":          _find(row, "進行ステータス"),
                "sample_status":            _find(row, "サンプルステータス"),
                "display_aggregation_flag": _find(row, "表示/集計フラグ"),
                "production_country":       _find(row, "●生産国"),
                "sale_type":                _find(row, "販売タイプ"),
                "tags":                     _find(row, "タグリスト"),
                "public_tags":              _find(row, "公開タグ"),

                "source_file":              "sitateru_item_list",
                "ingested_date":            source_date,
            })

        logger.info("Parsed sitateru item list: %d items", len(records))
        return records
