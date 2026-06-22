"""ZOZOセール設定 CSV を product_master から抽出して出力。

ZOZO BO の SaleSetting.asp / Sales_download.asp には「セール対象品一覧」の
CSVダウンロード機能がないため、既に毎日取得している goods_cs.csv
(product_master) から price_type='セール' の SKU を抽出する方式で対応。

CSV出力先: gs://mono-back-office-system-raw-data/uploads/zozo/sale/
            {date}/salegoods.csv  (cp932 / 既存ETLが取り込めるレイアウト)
"""
from __future__ import annotations
import csv, io, os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from google.cloud import bigquery, storage

JST = timezone(timedelta(hours=9))
PROJECT = "mono-back-office-system"
BUCKET = "mono-back-office-system-raw-data"


def main():
    target_date = os.getenv("TARGET_DATE") or \
        (datetime.now(JST) - timedelta(days=1)).strftime("%Y-%m-%d")

    bq = bigquery.Client(project=PROJECT)
    q = """
    SELECT
      shop_name, parent_category, child_category,
      parent_item_type, child_item_type, gender,
      product_code, item_code, sku_code, product_name,
      color_name, size,
      CAST(proper_price AS STRING) AS proper_price_str,
      CAST(unit_price   AS STRING) AS unit_price_str,
      CAST(ROUND((proper_price - unit_price)/proper_price * 100, 1) AS STRING)
                                    AS discount_pct_str,
      sale_type, sale_start_date, registered_date, barcode
    FROM `analytics_layer.product_master`
    WHERE is_active = TRUE
      AND price_type = 'セール'
      AND proper_price IS NOT NULL
      AND unit_price  IS NOT NULL
    ORDER BY shop_name, product_code, sku_code
    """
    rows = list(bq.query(q).result())
    if not rows:
        print("(no sale items found)")
        return 1

    print(f"Found {len(rows):,} sale SKUs")

    # Write CSV (cp932 to match existing ZOZO CSV format)
    buf = io.StringIO()
    w = csv.writer(buf)
    aliases = ["ショップ名", "親カテゴリ", "子カテゴリ", "親商品タイプ",
               "子商品タイプ", "性別", "ブランド品番", "商品コード", "CS別品番",
               "商品名", "カラー", "サイズ", "プロパー価格(税抜)",
               "販売価格(税抜)", "オフ率(%)", "販売タイプ", "販売開始日時",
               "登録日", "バーコード"]
    w.writerow(aliases)
    for r in rows:
        w.writerow([("" if v is None else str(v)) for v in r.values()])

    csv_text = buf.getvalue()
    # cp932 for compatibility with existing ZOZO CSV parser
    try:
        data = csv_text.encode("cp932", errors="replace")
    except Exception:
        data = csv_text.encode("utf-8-sig")

    # Upload to GCS at the standard sale_settings path
    sc = storage.Client(project=PROJECT)
    gcs_path = f"uploads/zozo/sale/{target_date}/salegoods.csv"
    sc.bucket(BUCKET).blob(gcs_path).upload_from_string(
        data, content_type="text/csv; charset=shift_jis")
    print(f"✓ uploaded: gs://{BUCKET}/{gcs_path} ({len(data):,} bytes)")

    # Also save local copy for client review
    local = Path(r"C:\Users\Administrator\Downloads\Pictures\system") / "salegoods_latest.csv"
    local.write_bytes(data)
    print(f"✓ local copy: {local.absolute()}")

    # Stats summary
    shops = {}
    discounts = []
    for r in rows:
        d = dict(r.items())
        shop = d.get("shop_name") or "(?)"
        shops[shop] = shops.get(shop, 0) + 1
        off = d.get("discount_pct_str")
        if off:
            try: discounts.append(float(off))
            except: pass

    print(f"\n--- 取得セール品 ショップ別 ---")
    for s, n in sorted(shops.items(), key=lambda x: -x[1]):
        print(f"  {s:25s}: {n:>6,} SKU")
    if discounts:
        print(f"\n--- 割引率分布 ---")
        print(f"  平均: {sum(discounts)/len(discounts):.1f}% off")
        print(f"  最大: {max(discounts):.1f}% off")
        print(f"  最小: {min(discounts):.1f}% off")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
