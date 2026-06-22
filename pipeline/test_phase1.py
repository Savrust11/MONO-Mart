"""
Phase 1 Local Verification Script
==================================
Run this BEFORE connecting to GCP to verify:
  1. CSV parsing works correctly (MMS, ZOZO BO)
  2. Field mapping produces the expected BigQuery schema
  3. No import errors

Usage:
  # Test MMS cost CSV
  python test_phase1.py --mms-cost path/to/評価額一覧-MMS.csv

  # Test MMS incoming stock CSV
  python test_phase1.py --mms-incoming path/to/mms_order_data.csv

  # Test ZOZO orders CSV
  python test_phase1.py --zozo-orders path/to/yyyy_mm_dd.csv --date 2025-05-01

  # Test ZOZO inventory CSV
  python test_phase1.py --zozo-inventory path/to/syyyymmdd.csv --date 2025-05-01

  # Test ZOZO reservations CSV
  python test_phase1.py --zozo-reserve path/to/yyyymmdd_ReserveList.csv --date 2025-05-01

  # Test product master CSV
  python test_phase1.py --zozo-products path/to/goods_cs.csv

  # Run all with a directory of sample files
  python test_phase1.py --dir path/to/sample_csvs/ --date 2025-05-01
"""
from __future__ import annotations

import argparse
import json
import sys
import io
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Add pipeline to path
sys.path.insert(0, str(Path(__file__).parent))

from extractors.zozo_csv_extractor import ZOZOCsvExtractor
from extractors.mms_extractor import MMSExtractor
from extractors.sitateru_extractor import SitateruExtractor
from extractors.tableau_extractor import TableauExtractor


def _print_sample(rows: list[dict], label: str, n: int = 3) -> None:
    print(f"\n{'='*60}")
    print(f"  {label}: {len(rows)} rows parsed")
    print(f"{'='*60}")
    for i, row in enumerate(rows[:n]):
        print(f"\n  Row {i+1}:")
        for k, v in row.items():
            print(f"    {k}: {v!r}")
    if len(rows) > n:
        print(f"\n  ... and {len(rows)-n} more rows")


def _check_required_fields(rows: list[dict], required: list[str], label: str) -> bool:
    if not rows:
        print(f"  WARNING: {label} — 0 rows parsed. Check field names in the CSV.")
        return False
    missing = [f for f in required if f not in rows[0]]
    if missing:
        print(f"  WARNING: {label} — missing expected fields: {missing}")
        print(f"  Actual fields: {list(rows[0].keys())}")
        return False
    print(f"  OK: {label} — all required fields present")
    return True


def test_mms_cost(path: str, date: str) -> None:
    data = Path(path).read_bytes()
    ext = MMSExtractor()
    rows = ext.parse_cost_master(data, date)
    _print_sample(rows, "MMS 原価 (cost master)")
    _check_required_fields(rows, ["sku_code", "cost_price", "valid_from"], "MMS cost master")

    # Check for duplicates
    skus = [r["sku_code"] for r in rows]
    dupes = len(skus) - len(set(skus))
    if dupes:
        print(f"  INFO: {dupes} duplicate SKUs were deduplicated (client noted this is expected)")
    else:
        print(f"  INFO: No duplicate SKUs found")


def test_mms_incoming(path: str, date: str) -> None:
    data = Path(path).read_bytes()
    ext = MMSExtractor()
    rows = ext.parse_incoming_stock(data, date)
    _print_sample(rows, "MMS 着荷データ (incoming stock)")
    _check_required_fields(rows, ["sku_code", "incoming_qty", "source_date"], "MMS incoming stock")


def _read_head_bytes(path: str, max_lines: int = 3000) -> bytes:
    """Read only the first max_lines lines — safe for large files (e.g. 800MB 受注)."""
    lines: list[bytes] = []
    with open(path, "rb") as f:
        for i, line in enumerate(f):
            lines.append(line)
            if i >= max_lines:
                break
    return b"".join(lines)


def test_zozo_orders(path: str, date: str, is_shipped: bool = False) -> None:
    label = "ZOZO 発送" if is_shipped else "ZOZO 受注"
    file_size_mb = Path(path).stat().st_size / 1024 / 1024
    print(f"\n  File size: {file_size_mb:.1f} MB", end="")

    # Large files (>50MB): read first 3000 lines only
    if file_size_mb > 50:
        print(f" → large file, sampling first 3,000 lines")
        data = _read_head_bytes(path, max_lines=3000)
    else:
        data = Path(path).read_bytes()

    ext = ZOZOCsvExtractor()
    rows = ext.parse_orders(data, date, is_shipped=is_shipped)
    _print_sample(rows, label)
    _check_required_fields(rows, ["sale_date", "sku_code", "sales_quantity", "shop_name"], label)

    if rows:
        total_qty = sum(r["sales_quantity"] for r in rows)
        total_amt = sum(r["sales_amount"] or 0 for r in rows)
        shops = {}
        malls = {}
        ptypes = {}
        for r in rows:
            shops[r.get("shop_name") or "?"] = shops.get(r.get("shop_name") or "?", 0) + 1
            malls[r.get("mall") or "?"] = malls.get(r.get("mall") or "?", 0) + 1
            ptypes[r.get("price_type") or "?"] = ptypes.get(r.get("price_type") or "?", 0) + 1
        print(f"  INFO: {len(rows):,} rows, 注文数={total_qty:,}, 売上(税抜)=¥{int(total_amt):,}")
        print(f"  INFO: ショップ={shops}")
        print(f"  INFO: モール={malls}")
        print(f"  INFO: 価格タイプ={ptypes}")
        if file_size_mb > 50:
            print(f"  ⚠️  NOTE: 先頭3,000行のみ集計。全件は BigQuery ロード後に確認してください。")


def test_zozo_inventory(path: str, date: str) -> None:
    data = Path(path).read_bytes()
    ext = ZOZOCsvExtractor()
    rows = ext.parse_inventory_sku(data, date)
    _print_sample(rows, "ZOZO 倉庫在庫：SKU毎")
    _check_required_fields(
        rows,
        ["snapshot_date", "sku_code", "stock_quantity", "shop_name", "price_type"],
        "ZOZO inventory",
    )
    if rows:
        total_stock = sum(r["stock_quantity"] for r in rows)
        total_value = sum(r.get("stock_value") or 0 for r in rows)
        shops: dict[str, int] = {}
        for r in rows:
            s = r.get("shop_name") or "?"
            shops[s] = shops.get(s, 0) + r["stock_quantity"]
        zero_stock = sum(1 for r in rows if r["stock_quantity"] == 0)
        print(f"  INFO: {len(rows):,} SKUs, 総在庫数={total_stock:,}, 在庫評価額=¥{int(total_value):,}")
        print(f"  INFO: ショップ別在庫数={shops}")
        print(f"  INFO: 在庫0件数={zero_stock}")


def test_zozo_reserve(path: str, date: str) -> None:
    data = Path(path).read_bytes()
    ext = ZOZOCsvExtractor()
    rows = ext.parse_reservations(data, date)
    _print_sample(rows, "ZOZO 予約管理一覧")
    _check_required_fields(rows, ["reservation_date", "sku_code", "quantity"], "ZOZO reservations")


def test_zozo_products(path: str) -> None:
    data = Path(path).read_bytes()
    ext = ZOZOCsvExtractor()
    rows = ext.parse_product_master(data)
    _print_sample(rows, "ZOZO 登録商品情報 (product master)")
    _check_required_fields(rows, ["sku_code", "product_code", "color_name", "size"], "product master")


def test_sitateru_sku(path: str, date: str) -> None:
    data = Path(path).read_bytes()
    ext = SitateruExtractor()
    rows = ext.parse_sku_master(data, date)
    _print_sample(rows, "sitateru SKU master")
    _check_required_fields(
        rows,
        ["sitateru_item_id", "product_name", "color_name", "size", "production_lot_qty"],
        "sitateru SKU master",
    )
    # Summary stats
    items = len({r["sitateru_item_id"] for r in rows})
    total_qty = sum(r["production_lot_qty"] or 0 for r in rows)
    has_sku = sum(1 for r in rows if r.get("sku_code"))
    print(f"  INFO: {items} items, {len(rows)} SKU records, total lot qty={total_qty:,}")
    print(f"  INFO: {has_sku} records have sitateru SKUコード (rest need MMS cross-ref)")


def test_tableau_yoyaku(path: str, date: str) -> None:
    data = Path(path).read_bytes()
    ext = TableauExtractor()
    rows = ext.parse_yoyaku_kanri(data, date)
    _print_sample(rows, "Tableau 予約管理 (incoming stock)")
    _check_required_fields(rows, ["sku_code", "incoming_qty", "source_date"], "Tableau 予約管理")
    total = sum(r["incoming_qty"] for r in rows)
    print(f"  INFO: {len(rows)} SKUs, total incoming_qty={total:,}")


def test_tableau_hacchu(path: str, date: str) -> None:
    data = Path(path).read_bytes()
    ext = TableauExtractor()
    rows = ext.parse_hacchu_meisai(data, date)
    _print_sample(rows, "Tableau 発注明細 (order details)")
    _check_required_fields(rows, ["sku_code", "incoming_qty", "source_date"], "Tableau 発注明細")
    total = sum(r["incoming_qty"] for r in rows)
    print(f"  INFO: {len(rows)} SKUs, total incoming_qty={total:,}")


def test_directory(dir_path: str, date: str) -> None:
    """Auto-detect and test all CSV files in a directory."""
    ext_zozo = ZOZOCsvExtractor()
    d = Path(dir_path)
    csv_files = list(d.glob("*.csv")) + list(d.glob("*.CSV"))
    if not csv_files:
        print(f"No CSV files found in {dir_path}")
        return

    for f in csv_files:
        file_type = ext_zozo.detect_file_type(f.name)
        print(f"\nFile: {f.name}  →  detected type: {file_type or 'UNKNOWN'}")
        if file_type == "orders":
            test_zozo_orders(str(f), date)
        elif file_type == "reservations":
            test_zozo_reserve(str(f), date)
        elif file_type == "inventory_sku":
            test_zozo_inventory(str(f), date)
        elif file_type == "product_master":
            test_zozo_products(str(f))
        else:
            print(f"  Skipping unrecognised file type. Rename to match convention or test manually.")


def main() -> None:
    today = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d")
    p = argparse.ArgumentParser(description="Phase 1 CSV parsing verification")
    p.add_argument("--date", default=today, help="Target date YYYY-MM-DD")
    p.add_argument("--mms-cost",      help="Path to MMS 原価 CSV (評価額一覧-MMS.csv)")
    p.add_argument("--mms-incoming",  help="Path to MMS 着荷データ CSV")
    p.add_argument("--zozo-orders",   help="Path to ZOZO 受注 CSV")
    p.add_argument("--zozo-shipped",  help="Path to ZOZO 発送 CSV")
    p.add_argument("--zozo-inventory",help="Path to ZOZO 倉庫在庫 CSV")
    p.add_argument("--zozo-reserve",  help="Path to ZOZO 予約管理一覧 CSV")
    p.add_argument("--zozo-products", help="Path to ZOZO goods_cs CSV")
    p.add_argument("--sitateru-sku",    help="Path to sitateru SKU master CSV")
    p.add_argument("--tableau-yoyaku", help="Path to Tableau 予約管理.csv")
    p.add_argument("--tableau-hacchu", help="Path to Tableau 発注明細.csv")
    p.add_argument("--dir",           help="Directory containing CSV files (auto-detect types)")
    args = p.parse_args()

    ran_any = False

    if args.mms_cost:
        test_mms_cost(args.mms_cost, args.date); ran_any = True
    if args.mms_incoming:
        test_mms_incoming(args.mms_incoming, args.date); ran_any = True
    if args.zozo_orders:
        test_zozo_orders(args.zozo_orders, args.date); ran_any = True
    if args.zozo_shipped:
        test_zozo_orders(args.zozo_shipped, args.date, is_shipped=True); ran_any = True
    if args.zozo_inventory:
        test_zozo_inventory(args.zozo_inventory, args.date); ran_any = True
    if args.zozo_reserve:
        test_zozo_reserve(args.zozo_reserve, args.date); ran_any = True
    if args.zozo_products:
        test_zozo_products(args.zozo_products); ran_any = True
    if args.sitateru_sku:
        test_sitateru_sku(args.sitateru_sku, args.date); ran_any = True
    if args.tableau_yoyaku:
        test_tableau_yoyaku(args.tableau_yoyaku, args.date); ran_any = True
    if args.tableau_hacchu:
        test_tableau_hacchu(args.tableau_hacchu, args.date); ran_any = True
    if args.dir:
        test_directory(args.dir, args.date); ran_any = True

    if not ran_any:
        p.print_help()
        print("\nExample:")
        print("  python test_phase1.py --mms-cost 評価額一覧-MMS.csv --date 2025-05-01")


if __name__ == "__main__":
    main()
