"""
発注/予約 CSV Extractor (originally Tableau Crosstab, now Google Sheets too)

Handles two input formats:
  1. Google Sheets export — UTF-8 CSV (BOM ok), comma-separated. Headers include
     '_tab', 'ZOZO親品番', 'ZOZOカラー', 'ZOZOサイズ', '発注数', '入荷済みチェック',
     'ZOZO納品予定日' (and the deeper 発注明細 cluster: '(a)親品番', '本納品日',
     '単価(円) 税抜き', 'SKU', '(i)ZOZOカラー', '(j)ZOZOサイズ').
     入荷残 calc: rows where 入荷済みチェック ∉ {'TRUE','済','✓','1','はい'} contribute
     their 発注数 as incoming_qty.
  2. Tableau Cloud Crosstab — UTF-16 LE, tab-separated (kept as fallback for when
     the client PAT is provided and we switch back).
"""
from __future__ import annotations

import csv as _csv
import io as _io
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── Status values that count as "not yet delivered" (入荷残あり) ──────────────
# 仮発注済  = provisionally ordered
# 新色＆リピート / リピート / 新品番 = order types (not statuses per se, but count as pending)
_PENDING_STATUSES = {"仮発注済", "新色＆リピート", "リピート", "新品番"}


def _read_tsv_utf16(data: bytes) -> tuple[list[str], list[dict[str, str]]]:
    """
    Parse UTF-16 LE tab-separated file (Tableau Cloud export format).
    Returns (headers, rows).
    """
    text = data.decode("utf-16")
    lines = text.strip().splitlines()
    if not lines:
        return [], []

    headers = [h.strip() for h in lines[0].split("\t")]
    rows: list[dict[str, str]] = []
    for line in lines[1:]:
        cols = [c.strip() for c in line.split("\t")]
        # Pad short rows
        while len(cols) < len(headers):
            cols.append("")
        rows.append(dict(zip(headers, cols)))

    return headers, rows


def _read_csv_utf8(data: bytes) -> tuple[list[str], list[list[str]]]:
    """
    Parse UTF-8 (BOM ok) comma-separated CSV (Google Sheets export format).
    Returns (headers, rows) where rows are positional lists — caller picks by
    column index since the Sheets file has duplicate column names ('発注数'
    appears twice).
    """
    text = data.decode("utf-8-sig", errors="replace")
    reader = _csv.reader(_io.StringIO(text))
    all_rows = [[c.strip() for c in r] for r in reader]
    if not all_rows:
        return [], []
    headers = all_rows[0]
    return headers, all_rows[1:]


def _looks_like_sheets_csv(data: bytes) -> bool:
    """Quick sniff — first few hundred bytes contain a sheets-format header."""
    head = data[:400]
    # UTF-16 starts with BOM 0xFFFE or 0xFEFF; everything else we try CSV
    if head.startswith(b"\xff\xfe") or head.startswith(b"\xfe\xff"):
        return False
    try:
        s = head.decode("utf-8-sig", errors="ignore")
    except Exception:
        return False
    return ("_tab" in s) or ("ZOZO親品番" in s) or ("入荷済みチェック" in s)


def _to_int(v: str | None) -> int:
    if not v:
        return 0
    try:
        return int(str(v).replace(",", "").strip())
    except (ValueError, TypeError):
        return 0


def _to_float(v: str | None) -> float | None:
    if not v:
        return None
    try:
        return float(str(v).replace(",", "").replace("\\", "").replace("¥", "").strip())
    except (ValueError, TypeError):
        return None


def _clean(v: str | None) -> str | None:
    if not v:
        return None
    s = str(v).strip()
    return s if s else None


class TableauExtractor:
    """
    Parse Tableau Cloud CSV exports into dicts matching our BigQuery schema.
    All methods accept raw bytes (as read from GCS or local disk).
    """

    def parse_yoyaku_kanri(
        self,
        data: bytes,
        source_date: str,
    ) -> list[dict[str, Any]]:
        """
        予約管理.csv — Production order management.

        Calculates 入荷残 (remaining incoming stock) per SKU:
            入荷残 = 発注数 − 実納品数量

        Returns records for analytics_layer.incoming_stock.
        """
        _, rows = _read_tsv_utf16(data)
        logger.info("Parsing 予約管理 CSV: %d raw rows", len(rows))

        # Aggregate by SKU
        by_sku: dict[str, dict[str, Any]] = {}

        for r in rows:
            sku = _clean(r.get("SKU")) or _clean(r.get("CS品番"))
            if not sku:
                continue

            order_qty    = _to_int(r.get("発注数"))
            delivered    = _to_int(r.get("実納品数量"))
            incoming_qty = max(0, order_qty - delivered)

            if sku not in by_sku:
                by_sku[sku] = {
                    "sku_code":              sku,
                    "product_code":          _clean(r.get("ブランド品番")) or _clean(r.get("仮品番")),
                    "color_name":            _clean(r.get("ZOZOカラー")),
                    "size":                  _clean(r.get("ZOZOサイズ")),
                    "product_name":          _clean(r.get("商品名")),
                    "shop_name":             _clean(r.get("ショップ")),
                    "season":                _clean(r.get("シーズン")),
                    "order_type":            _clean(r.get("発注種別")),
                    "incoming_qty":          0,
                    "ordered_qty":           0,
                    "delivered_qty":         0,
                    "earliest_arrival_date": _clean(r.get("希望納期")) or _clean(r.get("確定納品日")),
                    "source_date":           source_date,
                    "source_file":           "tableau_yoyaku_kanri",
                }
            by_sku[sku]["incoming_qty"]  += incoming_qty
            by_sku[sku]["ordered_qty"]   += order_qty
            by_sku[sku]["delivered_qty"] += delivered

            # Track earliest arrival date
            for date_col in ("確定納品日", "希望納期"):
                arrival = _clean(r.get(date_col))
                current = by_sku[sku]["earliest_arrival_date"]
                if arrival and (not current or arrival < current):
                    by_sku[sku]["earliest_arrival_date"] = arrival

        result = list(by_sku.values())
        total_incoming = sum(r["incoming_qty"] for r in result)
        logger.info(
            "Parsed 予約管理: %d SKUs, total 入荷残=%d",
            len(result), total_incoming
        )
        return result

    def parse_hacchu_meisai(
        self,
        data: bytes,
        source_date: str,
    ) -> list[dict[str, Any]]:
        """
        発注明細 — Order detail records → analytics_layer.incoming_stock.

        Auto-detects format: Google Sheets CSV (current source) or Tableau
        Crosstab TSV (fallback). Aggregates per (product_code, color_name, size)
        — the mart joins inventory on that composite key (sku_code mismatches
        between MMS and ZOZO).
        """
        if _looks_like_sheets_csv(data):
            return self._parse_hacchu_sheets(data, source_date)
        return self._parse_hacchu_tsv(data, source_date)

    def _parse_hacchu_sheets(self, data: bytes, source_date: str) -> list[dict[str, Any]]:
        headers, rows = _read_csv_utf8(data)
        if not headers:
            logger.warning("発注明細 Sheets CSV: empty")
            return []

        # ヘッダの表記ゆれ対策: セル内改行(\n/\r)・前後空白を除去して突合する。
        # 例) B列「入荷済み\nチェック」, AB列「単価(円)\n 税抜き」等、Sheets 由来の改行入りヘッダ。
        # これが無いと idx("入荷済みチェック")=-1 となり、入荷済み行が除外されず入荷残が過大計上される。
        def _norm(s: str) -> str:
            return (s or "").replace("\r", "").replace("\n", "").strip()
        norm_headers = [_norm(h) for h in headers]

        # Resolve column positions (positional because '発注数' is duplicated)
        def idx(name: str, start: int = 0) -> int:
            target = _norm(name)
            for i in range(start, len(norm_headers)):
                if norm_headers[i] == target:
                    return i
            return -1

        i_check = idx("入荷済みチェック")
        i_qty_main = idx("発注数")  # ZOZO-side count (= 発注数 in 予約管理 view)
        i_qty_alt = idx("発注数", i_qty_main + 1) if i_qty_main >= 0 else -1
        i_prod_zozo = idx("ZOZO親品番")
        i_prod_alt = idx("(a)親品番")
        i_prod_maker = idx("メーカー品番")
        i_color_zozo = idx("ZOZOカラー")
        i_color_alt = idx("(i)ZOZOカラー")
        i_color_maker = idx("(f)メーカーカラー名")
        i_size_zozo = idx("ZOZOサイズ")
        i_size_alt = idx("(j)ZOZOサイズ")
        i_size_maker = idx("(e)SIZE")
        i_cs = idx("ZOZOCS品番")
        i_cs_alt = idx("(b)CS品番")
        i_sku = idx("SKU")
        i_name = idx("(d)商品名")
        i_shop = idx("ショップ")
        i_season = idx("シーズン")
        i_unit = idx("単価(円)\n 税抜き")
        if i_unit < 0:
            i_unit = idx("単価(円) 税抜き")
        i_arrival = idx("本納品日")
        i_arrival_alt = idx("ZOZO納品予定日")

        TRUE_TOKENS = {"true", "1", "済", "✓", "○", "はい", "yes"}

        def cell(r: list[str], i: int) -> str | None:
            if i < 0 or i >= len(r):
                return None
            v = r[i].strip() if r[i] else ""
            return v or None

        # Aggregate by (product_code, color_name, size)
        agg: dict[tuple, dict[str, Any]] = {}
        skipped_done = 0
        skipped_no_key = 0

        for r in rows:
            prod = cell(r, i_prod_zozo) or cell(r, i_prod_alt) or cell(r, i_prod_maker)
            color = cell(r, i_color_zozo) or cell(r, i_color_alt) or cell(r, i_color_maker)
            size = cell(r, i_size_zozo) or cell(r, i_size_alt) or cell(r, i_size_maker)
            if not prod:
                skipped_no_key += 1
                continue

            chk = (cell(r, i_check) or "").lower()
            if chk in TRUE_TOKENS:
                skipped_done += 1
                continue

            qty = _to_int(cell(r, i_qty_main)) or _to_int(cell(r, i_qty_alt))
            if qty <= 0:
                continue

            sku = cell(r, i_sku)
            if not sku:
                cs = cell(r, i_cs) or cell(r, i_cs_alt) or ""
                sku = f"{prod}{cs}" if cs else prod

            key = (prod, color or "", size or "")
            if key not in agg:
                agg[key] = {
                    "source_date":           source_date,
                    "sku_code":              sku,
                    "product_code":          prod,
                    "product_name":          cell(r, i_name),
                    "color_name":            color,
                    "size":                  size,
                    "shop_name":             cell(r, i_shop),
                    "incoming_qty":          0,
                    "ordered_qty":           0,
                    "delivered_qty":         0,
                    "unit_price":            _to_float(cell(r, i_unit)),
                    "earliest_arrival_date": cell(r, i_arrival_alt) or cell(r, i_arrival),
                    "source":                "sheets",
                    "source_file":           "sheets_hacchu_meisai",
                }
            a = agg[key]
            a["incoming_qty"] += qty
            a["ordered_qty"]  += qty

            up = _to_float(cell(r, i_unit))
            if up and (a["unit_price"] is None or up < a["unit_price"]):
                a["unit_price"] = up
            arrival = cell(r, i_arrival_alt) or cell(r, i_arrival)
            cur = a["earliest_arrival_date"]
            if arrival and (not cur or arrival < cur):
                a["earliest_arrival_date"] = arrival

        result = list(agg.values())
        total = sum(r["incoming_qty"] for r in result)
        logger.info(
            "Parsed 発注明細 (Sheets): %d SKU-keys, total 入荷残=%d "
            "(rows: %d in, %d done-skipped, %d no-key)",
            len(result), total, len(rows), skipped_done, skipped_no_key
        )
        return result

    def _parse_hacchu_tsv(self, data: bytes, source_date: str) -> list[dict[str, Any]]:
        """Legacy Tableau Crosstab path (kept for PAT-based future)."""
        _, rows = _read_tsv_utf16(data)
        logger.info("Parsing 発注明細 TSV (legacy Tableau): %d raw rows", len(rows))

        by_sku: dict[str, dict[str, Any]] = {}
        for r in rows:
            sku = _clean(r.get("SKU")) or _clean(r.get("CS品番"))
            if not sku:
                continue
            order_qty = _to_int(r.get("発注数"))
            unit_price = _to_float(r.get("単価(円) 税抜き"))
            if sku not in by_sku:
                by_sku[sku] = {
                    "source_date":           source_date,
                    "sku_code":              sku,
                    "product_code":          _clean(r.get("親品番")) or _clean(r.get("メーカー品番")),
                    "product_name":          _clean(r.get("商品名")),
                    "color_name":            _clean(r.get("ZOZOカラー")) or _clean(r.get("メーカーカラー名")),
                    "size":                  _clean(r.get("ZOZOサイズ")) or _clean(r.get("SIZE")),
                    "shop_name":             _clean(r.get("ショップ")),
                    "incoming_qty":          0,
                    "ordered_qty":           0,
                    "delivered_qty":         0,
                    "unit_price":            unit_price,
                    "earliest_arrival_date": _clean(r.get("本納品日")),
                    "source":                "tableau",
                    "source_file":           "tableau_hacchu_meisai",
                }
            by_sku[sku]["incoming_qty"] += order_qty
            by_sku[sku]["ordered_qty"]  += order_qty
            if unit_price and (by_sku[sku]["unit_price"] is None
                               or unit_price < by_sku[sku]["unit_price"]):
                by_sku[sku]["unit_price"] = unit_price
            arrival = _clean(r.get("本納品日"))
            cur = by_sku[sku]["earliest_arrival_date"]
            if arrival and (not cur or arrival < cur):
                by_sku[sku]["earliest_arrival_date"] = arrival
        result = list(by_sku.values())
        total = sum(r["incoming_qty"] for r in result)
        logger.info("Parsed 発注明細 (TSV legacy): %d SKUs, total 発注数=%d",
                    len(result), total)
        return result
