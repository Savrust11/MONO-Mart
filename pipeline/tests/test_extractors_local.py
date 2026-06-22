"""
Local extractor test — runs all CSV extractors against actual sample files
in the data/ directory, without touching BigQuery.

Usage:
  cd pipeline
  python tests/test_extractors_local.py
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

# Make pipeline/ importable when running from anywhere
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from extractors.zozo_csv_extractor import ZOZOCsvExtractor
from extractors.mms_extractor import MMSExtractor
from extractors.tableau_extractor import TableauExtractor
from extractors.sitateru_extractor import SitateruExtractor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("test_extractors")

# Where the actual sample data files live
DATA_DIR = ROOT.parent / "data"
ROOT_DIR = ROOT.parent

TEST_DATE = "2026-05-05"


def _read(path: Path) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def _check(name: str, rows: list, min_rows: int = 1, sample: bool = True) -> bool:
    """Print a summary of extracted rows."""
    n = len(rows)
    ok = n >= min_rows
    status = "OK" if ok else "FAIL"
    print(f"  [{status}] {name}: {n} rows")
    if sample and rows:
        sample_row = rows[0]
        # Show first 5 keys/values
        preview = {k: v for i, (k, v) in enumerate(sample_row.items()) if i < 6}
        print(f"         sample: {json.dumps(preview, ensure_ascii=False, default=str)[:200]}")
    return ok


def test_zozo_csv():
    print("\n=== ZOZOBO CSV Extractors ===")
    z = ZOZOCsvExtractor()
    failures = []

    # No.1 受注
    f = ROOT_DIR / "zozo_order_data.csv"
    if f.exists():
        rows = z.parse_orders(_read(f), TEST_DATE)
        if not _check("No.1 受注 (zozo_order_data.csv)", rows): failures.append("orders")
    else:
        print(f"  [SKIP] No.1 受注: {f.name} not found")

    # No.3 予約管理一覧
    f = ROOT_DIR / "20260505_ReserveList.csv"
    if f.exists():
        rows = z.parse_reservations(_read(f), TEST_DATE)
        if not _check("No.3 予約管理一覧", rows): failures.append("reservations")
    else:
        print(f"  [SKIP] No.3 予約管理一覧: {f.name} not found")

    # No.4 倉庫在庫 (use S20260505.csv)
    f = ROOT_DIR / "S20260505.csv"
    if f.exists():
        rows = z.parse_inventory_sku(_read(f), TEST_DATE)
        if not _check("No.4 倉庫在庫SKU毎 (S20260505.csv)", rows): failures.append("inventory_sku")
    else:
        print(f"  [SKIP] No.4 倉庫在庫: {f.name} not found")

    # No.6 在庫分析
    f = ROOT_DIR / "20260505.csv"
    if f.exists():
        rows = z.parse_inventory_analysis(_read(f), TEST_DATE)
        if not _check("No.6 在庫分析 (20260505.csv)", rows): failures.append("stock_analysis")
    else:
        print(f"  [SKIP] No.6 在庫分析: {f.name} not found")

    # No.7 ZOZOAD
    f = DATA_DIR / "Detail.csv"
    if f.exists():
        rows = z.parse_zozoad(_read(f), TEST_DATE)
        if not _check("No.7 ZOZOAD (Detail.csv)", rows): failures.append("zozoad")
    else:
        print(f"  [SKIP] No.7 ZOZOAD: {f.name} not found")

    # No.8 商品別実績(新)
    f = DATA_DIR / "商品別実績_20260505.csv"
    if f.exists():
        rows = z.parse_performance(_read(f), TEST_DATE)
        if not _check("No.8 商品別実績(新)", rows): failures.append("performance")
    else:
        print(f"  [SKIP] No.8 商品別実績: {f.name} not found")

    # No.9 商品マスタ (goods_cs)
    f = ROOT_DIR / "goods_cs.csv"
    if f.exists():
        rows = z.parse_product_master(_read(f))
        if not _check("No.9 goods_cs.csv", rows, min_rows=10000): failures.append("product_master")
    else:
        # Try smaller brand-split file
        f = ROOT_DIR / "goods_cs_MONO_MART.csv"
        if f.exists():
            rows = z.parse_product_master(_read(f))
            if not _check(f"No.9 {f.name}", rows): failures.append("product_master")
        else:
            print(f"  [SKIP] No.9 goods_cs: not found")

    # No.17 セール設定
    f = DATA_DIR / "salegoods.csv"
    if f.exists():
        rows = z.parse_sale_settings(_read(f), TEST_DATE)
        if not _check("No.17 セール設定 (salegoods.csv)", rows): failures.append("sale_settings")
    else:
        print(f"  [SKIP] No.17 セール設定: {f.name} not found")

    # No.18 クーポン除外 (3 brand files)
    for brand_file in ["MONO-MART_20260506.csv", "EMMA CLOTHES_20260506.csv", "Chaco closet_20260506.csv"]:
        f = DATA_DIR / brand_file
        if f.exists():
            brand = ZOZOCsvExtractor.extract_brand_from_filename(brand_file)
            rows = z.parse_coupon_exclusion(_read(f), TEST_DATE, brand_name=brand)
            if not _check(f"No.18 クーポン除外 ({brand})", rows): failures.append(f"coupon_{brand}")
        else:
            print(f"  [SKIP] No.18 クーポン除外: {brand_file} not found")

    return failures


def test_mms():
    print("\n=== MMS Extractor ===")
    m = MMSExtractor()
    failures = []

    f = ROOT_DIR / "評価額一覧-MMS.csv"
    if f.exists():
        rows = m.parse_cost_master(_read(f), TEST_DATE)
        if not _check("No.10 原価 (評価額一覧-MMS.csv)", rows): failures.append("mms_cost")
    else:
        print(f"  [SKIP] No.10 原価: {f.name} not found")

    # mms_order_data
    files = list(ROOT_DIR.glob("mms_order_data*.csv"))
    if files:
        rows = m.parse_incoming_stock(_read(files[0]), TEST_DATE)
        if not _check(f"No.49 着荷データ ({files[0].name})", rows): failures.append("mms_incoming")
    else:
        print("  [SKIP] No.49 着荷データ: mms_order_data not found")

    return failures


def test_tableau():
    print("\n=== Tableau Extractor ===")
    t = TableauExtractor()
    failures = []

    f = ROOT_DIR / "発注明細.csv"
    if f.exists():
        rows = t.parse_hacchu_meisai(_read(f), TEST_DATE)
        if not _check("No.13 発注明細", rows): failures.append("hacchu_meisai")
    else:
        print(f"  [SKIP] No.13 発注明細: {f.name} not found")

    f = ROOT_DIR / "予約管理.csv"
    if f.exists():
        rows = t.parse_yoyaku_kanri(_read(f), TEST_DATE)
        if not _check("Tableau 予約管理", rows): failures.append("yoyaku_kanri")
    else:
        print(f"  [SKIP] Tableau 予約管理: {f.name} not found")

    return failures


def test_sitateru():
    print("\n=== sitateru Extractor ===")
    s = SitateruExtractor()
    failures = []

    # NOTE: export_item_*.csv (new format from アイテム一括登録・変更) has 175+ metadata
    # columns and a different structure than the original wide-format SKU export.
    # The existing parser handles the old アイテムSKUの一括登録・変更 format only.
    # New-format parser is pending finalization of filter criteria with the client.
    candidates = [
        ROOT_DIR / "sitateru_sku.csv",
    ]
    for f in candidates:
        if f.exists():
            rows = s.parse_sku_master(_read(f), TEST_DATE)
            if not _check(f"No.12 sitateru ({f.name})", rows): failures.append("sitateru")
            break
    else:
        print("  [SKIP] No.12 sitateru: no file found")

    return failures


def main():
    print("=" * 70)
    print("Phase 1 Local Extractor Test")
    print("=" * 70)
    print(f"Data directory: {DATA_DIR}")
    print(f"Test date:      {TEST_DATE}")

    all_failures = []
    all_failures += test_zozo_csv()
    all_failures += test_mms()
    all_failures += test_tableau()
    all_failures += test_sitateru()

    print("\n" + "=" * 70)
    if all_failures:
        print(f"FAILED: {len(all_failures)} extractor(s) returned no rows")
        for f in all_failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("ALL EXTRACTORS PASSED")
        sys.exit(0)


if __name__ == "__main__":
    main()
