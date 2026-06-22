"""
巨大な受注エクスポート (2024_07_01.csv, 2.4GB, 2024-10〜2026-06) から、
欠落月 (2025-09〜2026-01) の行だけを抽出し、月別CSVに分割して GCS へアップする。

出力: uploads/zozo/orders/{YYYY-MM-01}/orders_gap_{YYYYMM}.csv
  → backfill_ingest_sales.py が月初フォルダから読み込み、parse_orders が
     行ごとの 注文日 で sale_date を割り当てて BigQuery へ取り込む。

メモリ安全: 月ごとにローカル一時ファイルへストリーム書き込み → 最後にGCSへ。
"""
from __future__ import annotations
import csv, os, sys, tempfile
from pathlib import Path
from google.cloud import storage

SRC = r"C:\Users\Administrator\Downloads\2024_07_01.csv"
BUCKET = os.getenv("GCS_RAW_BUCKET", "mono-back-office-system-raw-data")
GAP = {"2025-09", "2025-10", "2025-11", "2025-12", "2026-01"}


def main() -> int:
    tmpdir = Path(tempfile.mkdtemp(prefix="gaporders_"))
    writers = {}
    handles = {}
    counts = {m: 0 for m in GAP}

    with open(SRC, encoding="cp932", errors="replace", newline="") as fh:
        rdr = csv.reader(fh)
        header = next(rdr)
        di = header.index("注文日")
        for m in GAP:
            h = open(tmpdir / f"{m}.csv", "w", encoding="utf-8-sig", newline="")
            w = csv.writer(h)
            w.writerow(header)
            handles[m] = h
            writers[m] = w
        for row in rdr:
            if di < len(row):
                ym = row[di].strip().replace("/", "-")[:7]
                if ym in GAP:
                    writers[ym].writerow(row)
                    counts[ym] += 1
    for h in handles.values():
        h.close()

    print("抽出件数:", counts)

    gcs = storage.Client()
    for m in sorted(GAP):
        local = tmpdir / f"{m}.csv"
        if counts[m] == 0:
            print(f"  {m}: 0件 skip"); continue
        folder = f"{m}-01"
        key = f"uploads/zozo/orders/{folder}/orders_gap_{m.replace('-','')}.csv"
        gcs.bucket(BUCKET).blob(key).upload_from_filename(str(local))
        print(f"  {m}: {counts[m]:,}行 → gs://{BUCKET}/{key} ({local.stat().st_size/1024/1024:.1f}MB)")
    print("=== split & upload 完了 ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
