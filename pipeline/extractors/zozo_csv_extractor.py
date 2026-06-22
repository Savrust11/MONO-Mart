"""
ZOZO Back Office (ZOZOBO) CSV Extractor

Handles manual CSV downloads from the ZOZOBO dashboard.
Upload the downloaded files to GCS and this extractor processes them.

Supported file types (from data list No.1–20):
  No.1  受注          : yyyy_mm_dd.csv          (分析＞注文：受注)
  No.2  発送          : yyyy_mm_dd.csv          (分析＞注文：発送)
  No.3  予約管理一覧  : yyyymmdd_ReserveList.csv (商品管理＞予約管理一覧)
  No.4  倉庫在庫SKU毎 : syyyymmdd.csv           (分析＞在庫：SKU毎)
  No.5  倉庫在庫入荷日毎: syyyymmdd.csv         (分析＞在庫：入荷日毎)
  No.6  在庫分析      : yyyymmdd.csv            (分析＞在庫分析データ)
  No.7  ZOZOAD       : Detail.csv              (サイト管理＞ZOZOAD＞詳細CSV)
  No.8  商品別実績    : 商品別実績_yyyymmdd.csv  (ダッシュボード＞商品別実績(新))
  No.9  登録商品SKU   : goods_cs.csv            (商品管理＞商品検索)
  No.17 セール設定    : salegoods.csv           (商品管理＞セール設定)
  No.18 クーポン除外  : {ブランド名}_yyyymmdd.csv (サイト管理＞イベントカレンダー)

GCS upload path convention:
  gs://{bucket}/uploads/zozo/{file_type}/{yyyy-mm-dd}/{filename}.csv
"""
from __future__ import annotations

import csv
import io
import logging
import re
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)

# ── Field name maps (ZOZOBO CSV column → our schema) ─────────────────────────

# No.1 受注 / No.2 発送
# Confirmed column names from actual zozo_order_data.csv (cp932):
# ショップ名, 親カテゴリ, 子カテゴリ, 親商品タイプ, 子商品タイプ, 性別, ブランド品番,
# CS品番, 商品名, カラー, サイズ, 販売開始日, 販売価格（税抜）, 販売タイプ, 価格タイプ,
# プロパー価格（税抜）, 注文番号, 注文数, 合計金額（税抜）, 注文日, 発送日,
# 注文時端末, キャンセル, 会員ID, 年齢, 会員性別, 県名, モール
_ORDER_FIELD_MAP = {
    "CS品番":               "sku_code",
    "ブランド品番":         "product_code",
    "カラー":               "color_name",
    "サイズ":               "size",
    "商品名":               "product_name",
    "注文数":               "order_qty",
    "出荷数":               "order_qty",       # 発送代替ファイル(売上集計)の数量列
    "合計金額（税抜）":     "sales_amount",
    "販売価格（税抜）":     "unit_price",
    "注文日":               "order_date",
    "発送日":               "shipped_date",
    "出荷日":               "shipped_date",   # 発送代替ファイル(売上集計)では「出荷日」
    "売上日":               "order_date",     # 同上: 注文日が無い場合の日付フォールバック
    "キャンセル":           "is_cancelled",
    "販売タイプ":           "sale_type",
    "価格タイプ":           "price_type",
    "プロパー価格（税抜）": "proper_price",
    "親カテゴリ":           "parent_category",
    "子カテゴリ":           "child_category",
    "性別":                 "gender",
    "会員ID":               "member_id",
    "ショップ名":           "shop_name",
    "注文番号":             "order_number",
    "モール":               "mall",
    "注文時端末":           "device",
    "年齢":                 "member_age",
    "会員性別":             "member_gender",
    "県名":                 "prefecture",
}

# No.3 予約管理一覧 (yyyymmdd_ReserveList.csv)
# Confirmed column names from actual 20260505_ReserveList.csv (cp932, 436 rows):
# 表示, ショップ, 親カテゴリ, 商品名, 商品コード, ブランド品番, カラー, サイズ,
# CS品番, 販売価格（税抜）, 販売可能数, 在庫数, 予約受付数, 注文数, 未処理,
# 発送指定日, お届け予定(初回納期), 遅延メール送信履歴, お届け予定(遅延納期),
# 販売終了, バーコード, 自動配信禁止設定, 納期メモ
_RESERVE_FIELD_MAP = {
    "CS品番":            "sku_code",
    "ブランド品番":      "product_code",
    "商品名":            "product_name",
    "カラー":            "color_name",
    "サイズ":            "size",
    "ショップ":          "shop_name",
    "予約受付数":        "reserved_qty",    # ← confirmed: 予約受付数 not 予約数
    "未処理":            "pending_qty",      # ← confirmed: 未処理 not 未処理数
    "注文数":            "ordered_qty",
    "在庫数":            "stock_quantity",
    "販売可能数":        "available_qty",
    "発送指定日":        "ship_date",
    "お届け予定(初回納期)": "expected_arrival",
}

# No.4 倉庫在庫：SKU毎
# Confirmed column names from actual zozo_stock_data.csv (cp932):
# ショップ名, 親カテゴリ, 子カテゴリ, 子商品タイプ, 商品コード, ブランド品番, 商品名,
# CS品番, カラー, サイズ, 販売価格(税抜)【HALF-WIDTH parens】, 在庫数, 価格タイプ,
# 合計金額（税抜）, プロパー価格（税抜）, 納品書NO., 納品書日時, サポート管理, バーコード
# Note: 未販売数/受注済未発送数 are NOT in this export — use 在庫分析(No.6) for those.
_INVENTORY_FIELD_MAP = {
    "CS品番":               "sku_code",
    "ブランド品番":         "product_code",
    "商品名":               "product_name",
    "カラー":               "color_name",
    "サイズ":               "size",
    "在庫数":               "stock_quantity",
    "ショップ名":           "shop_name",
    "親カテゴリ":           "parent_category",
    "価格タイプ":           "price_type",
    "販売価格(税抜)":       "unit_price",       # half-width parens
    "販売価格（税抜）":     "unit_price",       # full-width fallback
    "プロパー価格（税抜）": "proper_price",
    "合計金額（税抜）":     "stock_value",
    "納品書NO.":            "delivery_note_no",
    "納品書日時":           "delivery_note_date",
    "入荷日":               "arrival_date",    # No.5のみ — 入荷日毎の追加列
    "商品コード":           "item_code",
    "バーコード":           "barcode",
}

# No.6 在庫分析 (yyyymmdd.csv)
# Confirmed column names from actual 20260505.csv (cp932, 23,284 rows):
# ⚠️ Columns have leading spaces: " 親カテゴリ", " CS品番" etc. — stripped in _read_csv_bytes.
# ショップ, 親カテゴリ, 子カテゴリ, 親商品タイプ, 子商品タイプ, ブランド品番,
# 商品コード, 商品名, 主性別, カラー, サイズ, CS品番, プロパー価格（税抜）,
# 販売価格（税抜）, 価格タイプ, 販売タイプ, WEB表示, 初回販売開始設定日,
# 販売可能数, 外部販売可能数, 販売開始前点数, 販売前予約受付数, 販売可能数合計,
# 直近30日販売数, 直近7日販売数, 前日販売数, 商品詳細ID
_STOCK_ANALYSIS_FIELD_MAP = {
    "CS品番":            "sku_code",
    "ブランド品番":      "product_code",
    "商品名":            "product_name",
    "カラー":            "color_name",
    "サイズ":            "size",
    "ショップ":          "shop_name",
    "主性別":            "gender",
    "販売可能数":        "available_qty",      # フリー在庫（予約・未発送除外済）
    "外部販売可能数":    "external_available", # Yahoo等の外部販売可能数
    "販売可能数合計":    "total_available",    # 販売可能数 + 外部
    "販売開始前点数":    "pre_sale_qty",
    "販売前予約受付数":  "pre_sale_reserved",
    "直近30日販売数":    "sales_30d",          # ← built-in sales velocity!
    "直近7日販売数":     "sales_7d",           # ← built-in sales velocity!
    "前日販売数":        "sales_yesterday",
    "販売価格（税抜）":  "unit_price",
    "プロパー価格（税抜）": "proper_price",
    "価格タイプ":        "price_type",
    "初回販売開始設定日": "sale_start_date",
    "商品詳細ID":        "goods_detail_id",
    # 2026-06-17: new optional columns enabled per client request
    "継続入荷日":        "arrival_date",       # ArriveDT checkbox (旧ラベル)
    "最終入荷日":        "arrival_date",       # ArriveDT checkbox (画面ラベルは最終入荷日)
    "お気に入り登録数":  "favorites",          # FavoriteList checkbox (SKU-level)
    "バーコード":        "barcode",            # Barcode checkbox (slash-separated if multiple)
}

# No.8 商品別実績(新)
# Confirmed column names from actual 商品別実績_20260505.csv (UTF-8, NOT cp932):
# 日付, ショップID, ショップ名, ショップカテゴリ（親）, ショップカテゴリ（子）,
# ZOZOTOWNカテゴリ（親）, ZOZOTOWNカテゴリ（子）, 商品主性別, ブランド品番, 商品コード,
# 商品名, 受注点数, 受注金額, お気に入り登録者数, カート投入数,
# 販売可能数（取寄せ除く）, 販売可能数（取寄せ含む）, UU, PV, 購入者数,
# 購入者数(男), 購入者数(女), 購入者数(新規), 購入者数(既存), 購入者数(復活), 平均年齢
# ⚠️ NOTE: This file is at PRODUCT level (商品コード = item_code), not SKU level.
#         There's no カラー/サイズ — aggregated across all SKUs of a product.
_PERFORMANCE_FIELD_MAP = {
    "商品コード":        "item_code",          # ← product-level (not CS品番)
    "ブランド品番":      "product_code",
    "商品名":            "product_name",
    "ショップ名":        "shop_name",
    "ショップカテゴリ（親）": "shop_parent_category",
    "ショップカテゴリ（子）": "shop_child_category",
    "ZOZOTOWNカテゴリ（親）": "zozo_parent_category",
    "ZOZOTOWNカテゴリ（子）": "zozo_child_category",
    "商品主性別":        "gender",
    "受注点数":          "sales_qty",
    "受注金額":          "sales_amount",
    "お気に入り登録者数": "favorites",
    "カート投入数":      "cart_adds",
    "販売可能数（取寄せ除く）": "available_qty_excl",
    "販売可能数（取寄せ含む）": "available_qty_incl",
    "UU":                "unique_visitors",
    "PV":                "page_views",
    "購入者数":          "buyers_total",
    "購入者数(男)":      "buyers_male",
    "購入者数(女)":      "buyers_female",
    "購入者数(新規)":    "buyers_new",
    "購入者数(既存)":    "buyers_existing",
    "購入者数(復活)":    "buyers_revived",
    "平均年齢":          "average_age",
    "日付":              "record_date",
}

# No.7 ZOZOAD (Detail.csv)
# Confirmed column names from actual Detail.csv (cp932):
# 日付, ショップID, ショップ名, 親カテゴリ, 子カテゴリ, ブランド品番, 商品コード, 商品名,
# 親商品タイプ, 子商品タイプ, 表示箇所, imp, click, コスト, 経由売上件数,
# 経由売上金額（税抜）, CTR, CPC, ROAS
_ZOZOAD_FIELD_MAP = {
    "日付":              "record_date",
    "アップロード日":    "record_date",   # actual header used by the BO export
    "ショップID":        "shop_id",
    "ショップ名":        "shop_name",
    "親カテゴリ":        "parent_category",
    "子カテゴリ":        "child_category",
    "ブランド品番":      "product_code",
    "商品コード":        "item_code",
    "商品名":            "product_name",
    "親商品タイプ":      "parent_item_type",
    "子商品タイプ":      "child_item_type",
    "表示箇所":          "display_location",   # プレミア / その他
    "imp":               "impressions",
    "click":             "clicks",
    "コスト":            "ad_cost",            # JPY
    "経由売上件数":      "attributed_orders",
    "経由売上金額（税抜）": "attributed_revenue",
    "CTR":               "ctr_pct",            # "1.57%" string
    "CPC":               "cpc",                # JPY per click
    "ROAS":              "roas_pct",           # "1268%" string
}

# No.17 セール設定 (salegoods.csv)
# Confirmed column names from actual salegoods.csv (cp932):
# ショップ, 親カテゴリ, 商品名, 商品コード, ブランド品番, プロパー価格（税抜）,
# 変更後セール価格（税抜）, オフ率, 在庫数, 最新販売開始日, セール開始予定日時,
# タイムセール終了日時, 再販売価格（税抜）, セールタイプ
_SALE_FIELD_MAP = {
    "ショップ":          "shop_name",
    "親カテゴリ":        "parent_category",
    "商品名":            "product_name",
    "商品コード":        "item_code",
    "ブランド品番":      "product_code",
    "プロパー価格（税抜）": "proper_price",
    "変更後セール価格（税抜）": "sale_price",
    "オフ率":            "discount_pct",       # "10" → 10%
    "在庫数":            "stock_quantity",
    "最新販売開始日":    "latest_sale_start_date",
    "セール開始予定日時": "sale_start_at",
    "タイムセール終了日時": "sale_end_at",
    "再販売価格（税抜）": "resale_price",
    "セールタイプ":      "sale_type",          # ZOZO企画タイムセール etc.
}

# No.18 クーポン除外 ({ブランド名}_yyyymmdd.csv)
# Confirmed column names from actual MONO-MART_20260506.csv (cp932):
# 商品コード, ブランド品番, 除外対象フラグ（ZOZOTOWN）, 除外対象フラグ（Yahoo!ショッピング）
_COUPON_EXCLUSION_FIELD_MAP = {
    "商品コード":        "item_code",
    "ブランド品番":      "product_code",
    "除外対象フラグ（ZOZOTOWN）":          "excluded_zozotown",
    "除外対象フラグ（Yahoo!ショッピング）": "excluded_yahoo",
}

# No.9 登録商品情報：SKU単位 (goods_cs.csv)
# Confirmed column names from actual goods_cs.csv (cp932, 42,949 rows):
# モール, ショップ, 親カテゴリ, 子カテゴリ, 親商品タイプ, 子商品タイプ, 性別,
# ブランド品番, 商品コード, CS別品番, 商品名, カラー, サイズ, 登録日,
# 販売価格（税抜）, 価格タイプ, プロパー価格（税抜）, 販売開始前価格（税抜）,
# Web表示, 販売開始日, 素材表記, 原産国, 販売タイプ, 商品コメント,
# おすすめ設定, バーコード, 商品展開ID（GoodsDetailID）, 副性別
# ⚠️ Key: SKU field is "CS別品番" NOT "CS品番"
_PRODUCT_MASTER_FIELD_MAP = {
    "CS別品番":          "sku_code",        # ← confirmed: CS別品番 not CS品番
    "ブランド品番":      "product_code",
    "商品名":            "product_name",
    "カラー":            "color_name",
    "サイズ":            "size",
    "ショップ":          "shop_name",
    "親カテゴリ":        "parent_category",
    "子カテゴリ":        "child_category",
    "親商品タイプ":      "parent_item_type",
    "子商品タイプ":      "child_item_type",
    "性別":              "gender",
    "販売価格（税抜）":  "unit_price",
    "価格タイプ":        "price_type",
    "プロパー価格（税抜）": "proper_price",
    "Web表示":           "web_display",     # "1"=表示中, "0"=非表示
    "販売開始日":        "sale_start_date",
    "登録日":            "registered_date",
    "販売タイプ":        "sale_type",       # 通常/予約/未販売
    "バーコード":        "barcode",
    "商品コード":        "item_code",
    "商品展開ID（GoodsDetailID）": "goods_detail_id",
    "モール":            "mall",
}

# ── 旧列名 → 新列名 の正規化 (クライアント 古城様 2026-06-17 注意①) ─────────────
# 過去にDLしたCSVは、ZOZOのマイナー改修前の旧列名のまま保存されているケースがある。
# 新たにDLし直したものは新名称に統一されている。両方を読めるよう、読み込み時点で
# 旧名称を新名称へ正規化する。これにより全フィールドマップ（新名称ベース）が
# 旧ファイルでもそのまま機能する。
# ※ クライアントが明示した6ペアのみを対象とする。
_COLUMN_ALIASES = {
    "カテゴリ(親)":     "親カテゴリ",
    "カテゴリ(子)":     "子カテゴリ",
    "商品タイプ(親)":   "親商品タイプ",
    "商品タイプ(子)":   "子商品タイプ",
    "販売価格タイプ":   "価格タイプ",
    "元上代（税抜）":   "プロパー価格（税抜）",
}


# 会員限定セール期間中、親/子カテゴリ(=ブランド)がデータ上 "【限定】" に化ける
# (クライアント 古城様 2026-06-17 注意②)。これを正規ブランドとして保存しないよう
# 検出する。完全復元には施策実施前(例: 2026/7/29-31 のセールなら 7/28 時点)の
# goods_cs から product_code 単位で親/子カテゴリを補完する必要がある。
_LIMITED_BRAND_MARKERS = ("【限定】", "限定")


def _clean_category(v: str | None) -> str | None:
    """カテゴリ値が会員限定セールの "【限定】" 表記なら None を返す。
    None にしておくことで、後段で goods_cs から正しいブランドを補完できる。"""
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    if s in _LIMITED_BRAND_MARKERS or s.startswith("【限定】"):
        return None
    return s


def _normalize_columns(row: dict[str, str]) -> dict[str, str]:
    """列名の前後空白を除去し、旧列名を新列名へ正規化する。
    新列名が既に存在する場合は上書きしない（新優先）。"""
    out: dict[str, str] = {}
    for k, v in row.items():
        key = k.strip() if k else k
        key = _COLUMN_ALIASES.get(key, key)
        if key in out and out[key] not in (None, ""):
            continue
        out[key] = v
    return out


def _read_tsv_bytes(data: bytes) -> list[dict[str, str]]:
    """Parse TSV (tab-separated) bytes. Looker exports are UTF-8."""
    for enc in ("utf-8-sig", "utf-8", "cp932"):
        try:
            text = data.decode(enc)
            reader = csv.DictReader(io.StringIO(text), delimiter="\t")
            rows = [r for r in reader if r is not None]
            if rows and any(k and k != k.strip() for k in rows[0].keys() if k):
                rows = [{(k.strip() if k else k): v for k, v in r.items()}
                        for r in rows]
            return rows
        except UnicodeDecodeError:
            continue
        except Exception:
            continue
    return []


def _locate_header(text: str, header_markers: tuple[str, ...]) -> str:
    """先頭に説明行などが付くCSV（例: 発送代替ファイルは3行目がヘッダー）に対応。
    header_markers のいずれかを含む最初の行をヘッダーとみなし、それ以前を捨てる。
    マーカーを含む行が見つからなければ元のテキストをそのまま返す（=従来動作）。
    """
    lines = text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if any(m in line for m in header_markers):
            return "".join(lines[i:])
    return text


def _read_csv_bytes(
    data: bytes,
    encoding: str = "utf-8-sig",
    header_markers: tuple[str, ...] | None = None,
) -> list[dict[str, str]]:
    """Parse CSV bytes → list of raw dicts.
    Tries UTF-8-BOM first, then cp932 (Windows Japanese), then Shift-JIS.
    ZOZOBO exports use cp932 (Shift-JIS superset).

    header_markers: 指定すると、その語を含む行までスキップしてヘッダーを探す
    (発送代替ファイルのように先頭に追加行があるケースに対応)。
    旧列名は _normalize_columns で新列名へ正規化する (注意① 対応)。
    """
    # Try strict decode first (no replacement) so wrong encoding is detected
    for enc in (encoding, "cp932", "shift_jis", "utf-8"):
        try:
            text = data.decode(enc)   # strict — raises on bad bytes
            if header_markers:
                text = _locate_header(text, header_markers)
            reader = csv.DictReader(io.StringIO(text))
            rows = [r for r in reader if r is not None]
            # 列名の空白除去＋旧→新名称の正規化 (No.6 在庫分析の " 親カテゴリ" や
            # 旧DLファイルの "カテゴリ(親)" 等をここで吸収)
            return [_normalize_columns(r) for r in rows]
        except UnicodeDecodeError:
            continue
        except Exception:
            continue
    # Last resort: cp932 with replacement (handles truncated chunks in tests)
    text = data.decode("cp932", errors="replace")
    if header_markers:
        text = _locate_header(text, header_markers)
    rows = [r for r in csv.DictReader(io.StringIO(text)) if r is not None]
    return [_normalize_columns(r) for r in rows]


def _remap(row: dict[str, str], field_map: dict[str, str]) -> dict[str, Any]:
    """Apply field_map renaming, skip unmapped columns.

    複数の列名が同じ schema_col にマップされる場合 (例: 注文数/出荷数 → order_qty)、
    最初に見つかった非空の値を優先し、後続の空の別名で上書きしない。
    """
    out: dict[str, Any] = {}
    for csv_col, schema_col in field_map.items():
        raw = row.get(csv_col, "")
        val = raw.strip() if isinstance(raw, str) else raw
        val = val if val not in ("", "-", "N/A") else None
        # 既に非空の値があれば、空の別名で潰さない
        if out.get(schema_col) is not None and val is None:
            continue
        out[schema_col] = val
    return out


def _parse_int(v: str | None) -> int | None:
    if v is None:
        return None
    s = str(v).replace(",", "").strip()
    if not s:
        return None
    try:
        return int(s)
    except (ValueError, TypeError):
        # xlsx→csv変換は整数を "1.0" のように float 文字列で出力するため、
        # int() 直変換が失敗する。float 経由で救済する。
        try:
            return int(float(s))
        except (ValueError, TypeError):
            return None


def _parse_float(v: str | None) -> float | None:
    if v is None:
        return None
    try:
        # Round to 4 decimals to fit BigQuery NUMERIC precision constraints
        return round(float(str(v).replace(",", "").strip()), 4)
    except (ValueError, TypeError):
        return None


def _normalize_date(v: str | None) -> str | None:
    """Convert various date string formats to BigQuery-friendly YYYY-MM-DD.

    Accepts: 2026/03/06, 2026/3/6, 2026-03-06, 2026/03/06 8:39:44,
             20260306 (YYYYMMDD), 20260306.0 (xlsx float) など。
    Returns: 2026-03-06 (or None if unparseable).
    """
    if not v:
        return None
    s = str(v).strip()
    if not s:
        return None
    # Strip time part if present
    s = s.split(" ")[0].split("T")[0]
    # xlsx由来の末尾 ".0" を除去 (例: "20240702.0")
    if s.endswith(".0"):
        s = s[:-2]
    # 区切りなしの YYYYMMDD (発送代替ファイルの出荷日はこの形式)
    if re.fullmatch(r"\d{8}", s):
        y, m, d = int(s[0:4]), int(s[4:6]), int(s[6:8])
        if 2000 <= y <= 2100 and 1 <= m <= 12 and 1 <= d <= 31:
            return f"{y:04d}-{m:02d}-{d:02d}"
    # Try yyyy/mm/dd or yyyy-mm-dd
    parts = re.split(r"[/\-]", s)
    if len(parts) == 3:
        try:
            y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
            if 2000 <= y <= 2100 and 1 <= m <= 12 and 1 <= d <= 31:
                return f"{y:04d}-{m:02d}-{d:02d}"
        except (ValueError, TypeError):
            pass
    return None


# ── Public extractors ─────────────────────────────────────────────────────────

class ZOZOCsvExtractor:
    """
    Parse ZOZOBO CSV exports into dicts matching our BigQuery schema.
    All methods accept raw bytes (as read from GCS).
    """

    def parse_orders(
        self,
        data: bytes,
        source_date: str,
        is_shipped: bool = False,
    ) -> list[dict[str, Any]]:
        """
        No.1 受注 / No.2 発送 CSV.
        Returns records suitable for analytics_layer.sales_daily.

        発送の過去分は本来メニューにデータが無く、売上集計メニューの代替ファイルを
        使う (クライアント 古城様 2026-06-17)。代替ファイルは:
          ・日付列が「発送日(U列)」ではなく「出荷日(R列)」 → _ORDER_FIELD_MAP で吸収
          ・データリストが3行目から始まる (先頭に追加行あり) → header_markers で吸収
        通常の受注/発送ファイルはヘッダーが1行目にあり、同じマーカーで検出されるため
        両形式を同一コードで処理できる。
        """
        # 「品番」を含む行をヘッダーとみなす (通常=1行目, 代替=3行目)
        rows = _read_csv_bytes(data, header_markers=("ブランド品番", "CS品番", "CS別品番"))
        logger.info("Parsing orders CSV: %d raw rows (shipped=%s)", len(rows), is_shipped)

        out: list[dict[str, Any]] = []
        for r in rows:
            mapped = _remap(r, _ORDER_FIELD_MAP)
            if not mapped.get("sku_code"):
                continue

            # Skip cancelled rows
            cancelled = str(mapped.get("is_cancelled") or "").strip()
            if cancelled in ("1", "true", "TRUE", "キャンセル"):
                continue

            qty = _parse_int(mapped.get("order_qty")) or 0
            amount = _parse_float(mapped.get("sales_amount")) or 0.0

            # Normalize date: "2026/03/29 8:39:44" → "2026-03-29"
            # 発送代替ファイルには注文日が無く出荷日(=shipped_date)のみのため、
            # 注文日が無ければ出荷日を sale_date として使う (最後に source_date)。
            sale_date = (
                _normalize_date(mapped.get("order_date"))
                or _normalize_date(mapped.get("shipped_date"))
                or source_date
            )

            out.append({
                "sale_date":      sale_date,
                "sku_code":       mapped["sku_code"],
                "product_code":   mapped.get("product_code"),
                "product_name":   mapped.get("product_name"),
                "color_name":     mapped.get("color_name"),
                "size":           mapped.get("size"),
                "shop_name":      mapped.get("shop_name"),
                # 会員限定セール期間の "【限定】" は正規ブランドではないため None 化
                # (注意② — 後段で 7/28 等の goods_cs から補完する想定)
                "parent_category": _clean_category(mapped.get("parent_category")),
                "child_category": _clean_category(mapped.get("child_category")),
                "gender":         mapped.get("gender"),
                "sales_quantity": qty,
                "sales_amount":   amount,
                "unit_price":     _parse_float(mapped.get("unit_price")),
                "proper_price":   _parse_float(mapped.get("proper_price")),
                "price_type":     mapped.get("price_type"),
                "sale_type":      mapped.get("sale_type"),
                "mall":           mapped.get("mall"),
                "device":         mapped.get("device"),
                "order_number":   mapped.get("order_number"),
                "shipped_date":   _normalize_date(mapped.get("shipped_date")),
                "source_file":    "shipped" if is_shipped else "orders",
                "ingested_date":  source_date,
            })
        logger.info("Parsed %d valid order rows", len(out))
        return out

    def parse_reservations(
        self,
        data: bytes,
        source_date: str,
    ) -> list[dict[str, Any]]:
        """
        No.3 予約管理一覧 CSV.
        Returns records for analytics_layer.reservations.
        Only pending (未処理) rows are kept — matching the ZOZOBO filter.
        """
        rows = _read_csv_bytes(data)
        logger.info("Parsing reservations CSV: %d raw rows", len(rows))

        out: list[dict[str, Any]] = []
        for r in rows:
            mapped = _remap(r, _RESERVE_FIELD_MAP)
            if not mapped.get("sku_code"):
                continue

            pending  = _parse_int(mapped.get("pending_qty")) or 0
            reserved = _parse_int(mapped.get("reserved_qty")) or 0
            ordered  = _parse_int(mapped.get("ordered_qty")) or 0

            out.append({
                "reservation_date":  source_date,
                "sku_code":          mapped["sku_code"],
                "product_code":      mapped.get("product_code"),
                "product_name":      mapped.get("product_name"),
                "color_name":        mapped.get("color_name"),
                "size":              mapped.get("size"),
                "shop_name":         mapped.get("shop_name"),
                "quantity":          pending,           # 未処理 = truly pending
                "reserved_qty":      reserved,          # 予約受付数 total
                "ordered_qty":       ordered,           # 注文数 already ordered
                "available_qty":     _parse_int(mapped.get("available_qty")) or 0,
                "stock_quantity":    _parse_int(mapped.get("stock_quantity")) or 0,
                "ship_date":         mapped.get("ship_date"),
                "expected_arrival":  mapped.get("expected_arrival"),
                "status":            "pending",
                "source":            "zozo_reserve_list",
                "ingested_date":     source_date,
            })
        logger.info("Parsed %d reservation rows", len(out))
        return out

    def parse_inventory_sku(
        self,
        data: bytes,
        source_date: str,
    ) -> list[dict[str, Any]]:
        """
        No.4 倉庫在庫：SKU毎 CSV.
        No.5 倉庫在庫：入荷日毎 CSV (same columns + 入荷日 → arrival_date).
        Returns records for analytics_layer.inventory_snapshot.
        """
        rows = _read_csv_bytes(data)
        logger.info("Parsing inventory (SKU) CSV: %d raw rows", len(rows))

        out: list[dict[str, Any]] = []
        for r in rows:
            mapped = _remap(r, _INVENTORY_FIELD_MAP)
            if not mapped.get("sku_code"):
                continue

            out.append({
                "snapshot_date":    source_date,
                "sku_code":         mapped["sku_code"],
                "product_code":     mapped.get("product_code"),
                "product_name":     mapped.get("product_name"),
                "color_name":       mapped.get("color_name"),
                "size":             mapped.get("size"),
                "shop_name":        mapped.get("shop_name"),
                "stock_quantity":   _parse_int(mapped.get("stock_quantity")) or 0,
                "reserved_quantity": 0,   # not in SKU毎 CSV; use 在庫分析(No.6) for this
                "incoming_quantity": 0,   # not in SKU毎 CSV; use MMS/Tableau for this
                "unit_price":       _parse_float(mapped.get("unit_price")),
                "proper_price":     _parse_float(mapped.get("proper_price")),
                "price_type":       mapped.get("price_type"),
                "stock_value":      _parse_float(mapped.get("stock_value")),
                "arrival_date":     mapped.get("arrival_date"),   # No.5のみ; None for No.4
                "delivery_note_no": mapped.get("delivery_note_no"),
                "shelf_type":       "通常",
                "source_file":      "sku_inventory",
                "ingested_date":    source_date,
            })
        logger.info("Parsed %d inventory rows", len(out))
        return out

    def parse_inventory_analysis(
        self,
        data: bytes,
        source_date: str,
    ) -> list[dict[str, Any]]:
        """
        No.6 在庫分析 CSV.
        Provides available_qty (販売可能数) — free inventory including reservations.
        """
        rows = _read_csv_bytes(data)
        logger.info("Parsing inventory analysis CSV: %d raw rows", len(rows))

        out: list[dict[str, Any]] = []
        for r in rows:
            mapped = _remap(r, _STOCK_ANALYSIS_FIELD_MAP)
            if not mapped.get("sku_code"):
                continue

            out.append({
                "snapshot_date":      source_date,
                "sku_code":           mapped["sku_code"],
                "product_code":       mapped.get("product_code"),
                "product_name":       mapped.get("product_name"),
                "color_name":         mapped.get("color_name"),
                "size":               mapped.get("size"),
                "shop_name":          mapped.get("shop_name"),
                "available_qty":      _parse_int(mapped.get("available_qty")) or 0,
                "external_available": _parse_int(mapped.get("external_available")) or 0,
                "total_available":    _parse_int(mapped.get("total_available")) or 0,
                "pre_sale_qty":       _parse_int(mapped.get("pre_sale_qty")) or 0,
                "pre_sale_reserved":  _parse_int(mapped.get("pre_sale_reserved")) or 0,
                # Built-in sales velocity — saves joining with sales_daily for quick KPIs
                "sales_30d":          _parse_int(mapped.get("sales_30d")) or 0,
                "sales_7d":           _parse_int(mapped.get("sales_7d")) or 0,
                "sales_yesterday":    _parse_int(mapped.get("sales_yesterday")) or 0,
                "unit_price":         _parse_float(mapped.get("unit_price")),
                "proper_price":       _parse_float(mapped.get("proper_price")),
                "price_type":         mapped.get("price_type"),
                "sale_start_date":    mapped.get("sale_start_date"),
                # 2026-06-17: optional columns (None when CSV downloaded without these options)
                "arrival_date":       mapped.get("arrival_date") or None,
                "favorites":          _parse_int(mapped.get("favorites")),
                "barcode":            mapped.get("barcode") or None,
                "source_file":        "stock_analysis",
                "ingested_date":      source_date,
            })
        logger.info("Parsed %d stock-analysis rows", len(out))
        return out

    def parse_performance(
        self,
        data: bytes,
        source_date: str,
    ) -> list[dict[str, Any]]:
        """
        No.8 商品別実績(新).
        Provides sales_qty, favorites, UU/PV, buyer demographics per PRODUCT per day.
        Source is Looker's data-export — UTF-8 with embedded BOM, TAB-separated
        (csv.Sniffer false-detects this as comma, so we set delimiter explicitly
        when the header line contains a tab).
        """
        # Detect tab-separated by looking at the first chunk
        head = data[:2048].decode("utf-8-sig", errors="ignore")
        if "\t" in head.split("\n", 1)[0]:
            text = data.decode("utf-8-sig", errors="replace")
            reader = csv.DictReader(io.StringIO(text), delimiter="\t")
            rows = [r for r in reader if r is not None]
        else:
            rows = _read_csv_bytes(data)
        logger.info("Parsing performance CSV: %d raw rows", len(rows))

        out: list[dict[str, Any]] = []
        for r in rows:
            mapped = _remap(r, _PERFORMANCE_FIELD_MAP)
            if not mapped.get("item_code"):
                continue

            out.append({
                # performance file aggregates per product per day; map to sale_date
                "sale_date":            _normalize_date(mapped.get("record_date")) or source_date,
                "item_code":            mapped["item_code"],
                "product_code":         mapped.get("product_code"),
                "product_name":         mapped.get("product_name"),
                "shop_name":            mapped.get("shop_name"),
                "shop_parent_category": mapped.get("shop_parent_category"),
                "shop_child_category":  mapped.get("shop_child_category"),
                "zozo_parent_category": mapped.get("zozo_parent_category"),
                "zozo_child_category":  mapped.get("zozo_child_category"),
                "gender":               mapped.get("gender"),
                "sales_quantity":       _parse_int(mapped.get("sales_qty")) or 0,
                "sales_amount":         _parse_float(mapped.get("sales_amount")) or 0.0,
                "favorites":            _parse_int(mapped.get("favorites")) or 0,
                "cart_adds":            _parse_int(mapped.get("cart_adds")) or 0,
                "available_qty_excl":   _parse_int(mapped.get("available_qty_excl")) or 0,
                "available_qty_incl":   _parse_int(mapped.get("available_qty_incl")) or 0,
                "unique_visitors":      _parse_int(mapped.get("unique_visitors")) or 0,
                "page_views":           _parse_int(mapped.get("page_views")) or 0,
                "buyers_total":         _parse_int(mapped.get("buyers_total")) or 0,
                "buyers_male":          _parse_int(mapped.get("buyers_male")) or 0,
                "buyers_female":        _parse_int(mapped.get("buyers_female")) or 0,
                "buyers_new":           _parse_int(mapped.get("buyers_new")) or 0,
                "buyers_existing":      _parse_int(mapped.get("buyers_existing")) or 0,
                "buyers_revived":       _parse_int(mapped.get("buyers_revived")) or 0,
                "average_age":          _parse_float(mapped.get("average_age")),
                "source_file":          "performance",
                "ingested_date":        source_date,
            })
        logger.info("Parsed %d performance rows", len(out))
        return out

    def parse_zozoad(
        self,
        data: bytes,
        source_date: str,
    ) -> list[dict[str, Any]]:
        """
        No.7 ZOZOAD Detail.csv — ad performance per product per day.
        Returns records for raw_layer.zozoad_daily.
        Note: ZOZOAD file updates around 11am JST and is unstable — schedule pipeline after 12:00.
        """
        rows = _read_csv_bytes(data)
        logger.info("Parsing ZOZOAD CSV: %d raw rows", len(rows))

        out: list[dict[str, Any]] = []
        for r in rows:
            mapped = _remap(r, _ZOZOAD_FIELD_MAP)
            if not mapped.get("item_code"):
                continue

            # CTR/ROAS come as "1.57%" / "1268%" — strip %
            ctr_raw = (mapped.get("ctr_pct") or "").replace("%", "").strip()
            roas_raw = (mapped.get("roas_pct") or "").replace("%", "").strip()

            out.append({
                "record_date":         _normalize_date(mapped.get("record_date")) or source_date,
                "shop_id":             mapped.get("shop_id"),
                "shop_name":           mapped.get("shop_name"),
                "parent_category":     mapped.get("parent_category"),
                "child_category":      mapped.get("child_category"),
                "product_code":        mapped.get("product_code"),
                "item_code":           mapped["item_code"],
                "product_name":        mapped.get("product_name"),
                "parent_item_type":    mapped.get("parent_item_type"),
                "child_item_type":     mapped.get("child_item_type"),
                "display_location":    mapped.get("display_location"),
                "impressions":         _parse_int(mapped.get("impressions")) or 0,
                "clicks":              _parse_int(mapped.get("clicks")) or 0,
                "ad_cost":             _parse_float(mapped.get("ad_cost")) or 0.0,
                "attributed_orders":   _parse_int(mapped.get("attributed_orders")) or 0,
                "attributed_revenue":  _parse_float(mapped.get("attributed_revenue")) or 0.0,
                "ctr":                 _parse_float(ctr_raw),
                "cpc":                 _parse_float(mapped.get("cpc")),
                "roas":                _parse_float(roas_raw),
                "source_file":         "zozoad",
                "ingested_date":       source_date,
            })
        logger.info("Parsed %d ZOZOAD rows", len(out))
        return out

    def parse_sale_settings(
        self,
        data: bytes,
        source_date: str,
    ) -> list[dict[str, Any]]:
        """
        No.17 セール設定 (salegoods.csv) — current sale configurations per product.
        Returns records for raw_layer.sale_settings.
        Used to flag whether a product is currently on sale (プロパー vs セール discrimination).
        """
        rows = _read_csv_bytes(data)
        logger.info("Parsing sale settings CSV: %d raw rows", len(rows))

        out: list[dict[str, Any]] = []
        for r in rows:
            mapped = _remap(r, _SALE_FIELD_MAP)
            if not mapped.get("item_code"):
                continue

            out.append({
                "snapshot_date":           source_date,
                "item_code":               mapped["item_code"],
                "product_code":            mapped.get("product_code"),
                "product_name":            mapped.get("product_name"),
                "shop_name":               mapped.get("shop_name"),
                "parent_category":         mapped.get("parent_category"),
                "proper_price":            _parse_float(mapped.get("proper_price")),
                "sale_price":              _parse_float(mapped.get("sale_price")),
                "discount_pct":            _parse_float(mapped.get("discount_pct")),
                "stock_quantity":          _parse_int(mapped.get("stock_quantity")) or 0,
                "latest_sale_start_date":  mapped.get("latest_sale_start_date"),
                "sale_start_at":           mapped.get("sale_start_at"),
                "sale_end_at":             mapped.get("sale_end_at"),
                "resale_price":            _parse_float(mapped.get("resale_price")),
                "sale_type":               mapped.get("sale_type"),
                "source_file":             "salegoods",
                "ingested_date":           source_date,
            })
        logger.info("Parsed %d sale-setting rows", len(out))
        return out

    def parse_search_keyword(
        self,
        data: bytes,
        source_date: str,
    ) -> list[dict[str, Any]]:
        """No.20 検索キーワード経由アクセス実績 (Looker CSV or TSV)
        Updated 2026-06-09: now ショップ親カテゴリ別 view from dashboard-level
        DL ZIP — adds ショップ親カテゴリ名 column.
        Columns (CSV from dashboard, 2026-06-09):
            日付, ショップ名, ショップ親カテゴリ名, PVランク, 検索キーワード, 商品詳細PV
        Legacy TSV (ショップ別 tile, pre-2026-06-09):
            日付, ショップ名, PVランク, 検索キーワード, 商品詳細PV
        """
        # Try CSV first (new dashboard-DL format); fall back to TSV (legacy)
        rows = _read_csv_bytes(data)
        if not rows or "日付" not in (rows[0] if rows else {}):
            rows = _read_tsv_bytes(data)
        logger.info("Parsing search-keyword: %d raw rows", len(rows))
        out: list[dict[str, Any]] = []
        for r in rows:
            kw = (r.get("検索キーワード") or "").strip()
            shop = (r.get("ショップ名") or "").strip()
            if not kw or not shop:
                continue
            rec_date = (r.get("日付") or source_date).strip()
            out.append({
                "record_date":      rec_date,
                "shop_name":        shop,
                "parent_category":  (r.get("ショップ親カテゴリ名") or "").strip() or None,
                "search_keyword":   kw,
                "rank":             _parse_int(r.get("PVランク")),
                "visits":           None,
                "page_views":       _parse_int(r.get("商品詳細PV")),
                "orders":           None,
                "sales_amount":     None,
                "source_file":      "search_keyword",
                "ingested_date":    source_date,
            })
        logger.info("Parsed %d search-keyword rows", len(out))
        return out

    def parse_access_log_dashboard(
        self,
        data: bytes,
        source_date: str,
        device_hint: str | None = None,
    ) -> list[dict[str, Any]]:
        """No.19 アクセス実績 (App/PC-SP/ショップ親カテゴリ別) — Looker dashboard CSV.

        Verified format (2026-06-05) — `アクセス実績_app_dl用.csv` from the App
        tab's dashboard ZIP download. 47-column wide CSV:
          日付, 曜日, ショップID, ショップ名, ショップ親カテゴリID, ショップ親カテゴリ名,
          PV数, 前年PV数, PV前年比, UU数, 前年UU数, UU前年比,
          + per-経路 (キーワード/お知らせ/カート/.../WEAR/メルマガ/etc) PV+UU pairs.

        Output schema: one row per (date, shop, parent_category, device_type)
        with overall PV/UU totals. The per-経路 breakdown columns are JSON-
        encoded into `route_breakdown` for future analytics.
        """
        rows = _read_csv_bytes(data)
        logger.info("Parsing access-log dashboard CSV: %d raw rows", len(rows))
        out: list[dict[str, Any]] = []
        import json as _json
        for r in rows:
            rec_date = (r.get("日付") or source_date).strip()
            shop = (r.get("ショップ名") or "").strip()
            if not shop:
                continue
            parent_cat = (r.get("ショップ親カテゴリ名") or "").strip()
            # Collect route-specific PV/UU into a JSON dict for analytics
            route = {}
            for k in r:
                if k in ("日付", "曜日", "ショップID", "ショップ名",
                         "ショップ親カテゴリID", "ショップ親カテゴリ名",
                         "PV数", "前年PV数", "PV前年比",
                         "UU数", "前年UU数", "UU前年比"):
                    continue
                v = (r.get(k) or "").strip()
                if v:
                    parsed = _parse_int(v)
                    route[k] = parsed if parsed is not None else v
            out.append({
                "record_date":        rec_date,
                "shop_name":          shop,
                "device_type":        device_hint or "ALL",
                "page_views":         _parse_int(r.get("PV数")),
                "daily_active_users": _parse_int(r.get("UU数")),
                "source_file":        "access_log_dashboard",
                "ingested_date":      source_date,
                # Future-friendly extras (only kept if BQ schema includes them)
                "parent_category":    parent_cat or None,
                "route_breakdown":    _json.dumps(route, ensure_ascii=False)
                                       if route else None,
                "page_views_yoy_pct": (r.get("PV前年比") or "").strip() or None,
                "uu_yoy_pct":         (r.get("UU前年比") or "").strip() or None,
            })
        logger.info("Parsed %d access-log-dashboard rows", len(out))
        return out

    def parse_pf_fee(
        self,
        data: bytes,
        source_date: str,
    ) -> list[dict[str, Any]]:
        """PF手数料表 (Google Sheet export) — per-品番 cost (下代) + 手数料率.
        Used as primary cost source for the order management mart;
        falls back to MMS cost_master when a product_code is missing.

        Sheet structure (confirmed 2026-06-09):
          row 0: title (PF手数料表用《更新用》)
          row 1: section headers
          row 2: column headers — col 5 = 品番, col 17 = 下代 税抜き
          row 3+: data rows
        """
        text = None
        for enc in ("utf-8-sig", "utf-8", "cp932"):
            try:
                text = data.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            return []
        reader = csv.reader(io.StringIO(text))
        rows = list(reader)
        # Find header row containing 品番
        hdr_idx = None
        for i in range(min(8, len(rows))):
            if "品番" in rows[i]:
                hdr_idx = i
                break
        if hdr_idx is None:
            logger.warning("PF fee: header row not found")
            return []
        hdr = rows[hdr_idx]
        # Locate column indices
        col_product = hdr.index("品番") if "品番" in hdr else None
        col_cost = None
        col_zozo_fee = None
        col_shop = hdr.index("ショップ名") if "ショップ名" in hdr else None
        for j, name in enumerate(hdr):
            n = (name or "").strip()
            if "下代" in n and "税抜" in n:
                col_cost = j
            if "ZOZOTOWN" in n and "手数料率" in n:
                col_zozo_fee = j
        if col_product is None or col_cost is None:
            logger.warning("PF fee: required columns missing (品番=%s 下代=%s)",
                           col_product, col_cost)
            return []
        out: list[dict[str, Any]] = []
        for r in rows[hdr_idx + 1:]:
            if not r or len(r) <= col_product:
                continue
            product = (r[col_product] or "").strip()
            if not product:
                continue
            cost_raw = r[col_cost] if len(r) > col_cost else ""
            cost = _parse_float((cost_raw or "").replace(",", ""))
            shop = (r[col_shop] or "").strip() if (col_shop is not None
                                                   and len(r) > col_shop) else None
            zozo_fee = (r[col_zozo_fee] or "").strip() if (
                col_zozo_fee is not None and len(r) > col_zozo_fee) else None
            out.append({
                "product_code":   product,
                "shop_name":      shop or None,
                "cost_price":     cost,    # 下代 税抜
                "zozo_fee_rate":  zozo_fee or None,
                "source_file":    "pf_fee",
                "snapshot_date":  source_date,
                "ingested_at":    None,    # filled by BQ default
            })
        logger.info("Parsed %d PF-fee rows", len(out))
        return out

    def parse_access_log(
        self,
        data: bytes,
        source_date: str,
        shop_hint: str | None = None,
        device_hint: str | None = None,
    ) -> list[dict[str, Any]]:
        """No.19 アクセス実績(新) (Looker TSV from rpid=9)

        Confirmed format (2026-06-03 from 商品別実績(新)>PV推移 tile):
            日付 \t PV数 \t 前年PV数
        Shop name is NOT in the TSV header — it's implied by the per-shop
        filter applied when downloading. The merge logic in zozo_scraper
        concatenates per-shop TSVs but loses the shop tag — for now we tag
        all rows with `shop_hint` (defaulting to "MERGED" when unknown).

        Future enhancement: switch to "App(ショップ親カテゴリ)" / "PC/SP(ショップ親
        カテゴリ)" tiles once exposed in the user account — those include
        shop + device as data columns.
        """
        rows = _read_tsv_bytes(data)
        logger.info("Parsing access-log TSV: %d raw rows", len(rows))
        out: list[dict[str, Any]] = []
        for r in rows:
            keys = {k.strip(): k for k in r.keys() if k}
            def gv(*names):
                for n in names:
                    if n in keys:
                        v = (r.get(keys[n]) or "").strip()
                        if v:
                            return v
                return None
            rec_date = gv("日付", "集計日", "日付（日）")
            if not rec_date:
                continue
            pv = gv("PV数", "PV", "ページビュー", "商品詳細PV", "閲覧数")
            dau = gv("DAU", "UU数", "UU", "ユニークユーザ", "ユニークユーザー")
            shop = (gv("ショップ名", "ショップ", "ショップ親カテゴリ", "親カテゴリ")
                    or shop_hint or "MERGED")
            device = gv("デバイス", "端末", "デバイス区分") or device_hint or "合計"
            out.append({
                "record_date":        rec_date,
                "shop_name":          shop,
                "device_type":        device,
                "page_views":         _parse_int(pv),
                "daily_active_users": _parse_int(dau),
                "source_file":        "access_log",
                "ingested_date":      source_date,
            })
        logger.info("Parsed %d access-log rows", len(out))
        return out

    def parse_product_reviews(
        self,
        data: bytes,
        source_date: str,
    ) -> list[dict[str, Any]]:
        """No.15 商品レビュー — UTF-8 BOM CSV emitted by fetch_product_reviews.py."""
        rows = _read_csv_bytes(data)
        logger.info("Parsing product-reviews CSV: %d raw rows", len(rows))
        out: list[dict[str, Any]] = []
        for r in rows:
            rec_date = (r.get("review_date") or source_date).strip()
            # Accept dates in YYYY/M/D or YYYY-MM-DD; normalize to ISO
            rec_date = rec_date.replace("/", "-")
            out.append({
                "review_date":     rec_date,
                "shop_name":       (r.get("shop_name") or "").strip(),
                "item_code":       (r.get("item_code") or "").strip(),
                "product_code":    (r.get("product_code") or "").strip(),
                "product_name":    (r.get("product_name") or "").strip(),
                "parent_category": (r.get("parent_category") or "").strip(),
                "child_category":  (r.get("child_category") or "").strip(),
                "rating":          _parse_int(r.get("rating")),
                "review_title":    (r.get("review_title") or "").strip(),
                "review_body":     (r.get("review_body") or "").strip(),
                "display_status":  (r.get("display_status") or "").strip(),
                "reviewer_attr":   (r.get("reviewer_attr") or "").strip(),
                "source_file":     "product_reviews",
                "ingested_date":   source_date,
            })
        logger.info("Parsed %d product-review rows", len(out))
        return out

    def parse_coupon_exclusion(
        self,
        data: bytes,
        source_date: str,
        brand_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        No.18 クーポン除外 ({ブランド名}_yyyymmdd.csv) — products excluded from coupons on a given day.
        Filename pattern: {brand_name}_{yyyymmdd}.csv (e.g., MONO-MART_20260506.csv)
        Returns records for raw_layer.coupon_exclusion.
        """
        rows = _read_csv_bytes(data)
        logger.info("Parsing coupon exclusion CSV: %d raw rows (brand=%s)", len(rows), brand_name)

        out: list[dict[str, Any]] = []
        for r in rows:
            mapped = _remap(r, _COUPON_EXCLUSION_FIELD_MAP)
            if not mapped.get("item_code"):
                continue

            zozotown_excluded = str(mapped.get("excluded_zozotown") or "").strip() in ("1", "true")
            yahoo_excluded = str(mapped.get("excluded_yahoo") or "").strip() in ("1", "true")

            out.append({
                "exclusion_date":     source_date,
                "brand_name":         brand_name,
                "item_code":          mapped["item_code"],
                "product_code":       mapped.get("product_code"),
                "excluded_zozotown":  zozotown_excluded,
                "excluded_yahoo":     yahoo_excluded,
                "source_file":        "coupon_exclusion",
                "ingested_date":      source_date,
            })
        logger.info("Parsed %d coupon-exclusion rows", len(out))
        return out

    def parse_product_master(
        self,
        data: bytes,
    ) -> list[dict[str, Any]]:
        """
        No.9 登録商品情報：SKU単位 CSV (goods_cs).
        Returns records for analytics_layer.product_master.
        """
        rows = _read_csv_bytes(data)
        logger.info("Parsing product master CSV: %d raw rows", len(rows))

        out: list[dict[str, Any]] = []
        for r in rows:
            mapped = _remap(r, _PRODUCT_MASTER_FIELD_MAP)
            if not mapped.get("sku_code"):
                continue

            # Web表示: "1"=表示中(active), "0"=非表示, blank=active
            web_disp = (mapped.get("web_display") or "1").strip()
            is_active = web_disp != "0"

            # Force barcode to clean string — strip quotes, tabs, leading/trailing whitespace
            # (some rows have raw values like "\t \"2530000129613/2530000002310\"")
            barcode_raw = mapped.get("barcode")
            if barcode_raw:
                barcode = str(barcode_raw).replace('"', '').replace("\t", "").strip()
                barcode = barcode if barcode else None
            else:
                barcode = None

            out.append({
                "sku_code":          mapped["sku_code"],
                "product_code":      mapped.get("product_code"),
                "product_name":      mapped.get("product_name"),
                "color_name":        mapped.get("color_name"),
                "size":              mapped.get("size"),
                "shop_name":         mapped.get("shop_name"),
                "parent_category":   mapped.get("parent_category"),
                "child_category":    mapped.get("child_category"),
                "parent_item_type":  mapped.get("parent_item_type"),
                "child_item_type":   mapped.get("child_item_type"),
                "gender":            mapped.get("gender"),
                "unit_price":        _parse_float(mapped.get("unit_price")),
                "proper_price":      _parse_float(mapped.get("proper_price")),
                "price_type":        mapped.get("price_type"),
                "sale_type":         mapped.get("sale_type"),
                "sale_start_date":   mapped.get("sale_start_date"),
                "registered_date":   mapped.get("registered_date"),
                "barcode":           barcode,
                "item_code":         mapped.get("item_code"),
                "goods_detail_id":   mapped.get("goods_detail_id"),
                "mall":              mapped.get("mall"),
                "is_active":         is_active,
                "shelf_type":        "通常",
                "source_file":       "product_master",
            })
        logger.info("Parsed %d product master rows", len(out))
        return out

    # ── Filename → type detection ─────────────────────────────────────────────

    @staticmethod
    def detect_file_type(filename: str) -> str | None:
        """
        Infer the ZOZOBO data type from the filename pattern.

        Returns one of:
          'orders', 'shipped', 'reservations', 'inventory_sku',
          'inventory_arrival', 'stock_analysis', 'performance',
          'product_master', 'zozoad', 'sale_settings', 'coupon_exclusion'
        or None if unrecognised.
        """
        # Lowercase for matching but keep original for Japanese chars
        name = filename
        lower = filename.lower()

        if re.search(r"ReserveList|reserve_list|予約管理", name, re.IGNORECASE):
            return "reservations"
        if re.search(r"goods_cs|登録商品", name, re.IGNORECASE):
            return "product_master"
        if re.search(r"商品別実績|performance", name):
            return "performance"
        if "detail" in lower:
            return "zozoad"
        if "salegoods" in lower:
            return "sale_settings"
        # syyyymmdd → inventory files (two types — inventory_sku vs arrival)
        if re.match(r"s\d{8}", lower):
            return "inventory_sku"
        # yyyymmdd → stock analysis
        if re.match(r"\d{8}\.csv", lower):
            return "stock_analysis"
        # yyyy_mm_dd → orders or shipped (can't tell without folder; default orders)
        if re.match(r"\d{4}_\d{2}_\d{2}", lower):
            return "orders"
        # {ブランド名}_yyyymmdd.csv → coupon exclusion
        if re.match(r".+_\d{8}\.csv", name):
            return "coupon_exclusion"
        return None

    @staticmethod
    def extract_brand_from_filename(filename: str) -> str | None:
        """
        Extract brand name from coupon exclusion filename: {brand_name}_yyyymmdd.csv
        Returns the brand name or None.
        """
        m = re.match(r"(.+)_(\d{8})\.csv$", filename)
        if m:
            return m.group(1)
        return None
