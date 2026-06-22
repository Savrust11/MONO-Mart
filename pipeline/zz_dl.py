from google.cloud import storage
from pathlib import Path
c = storage.Client()
src = "uploads/zozo/stock_analysis/2026-06-18/20260619.csv"
dst = r"C:\Users\Administrator\Downloads\在庫分析データ_2026-06-18.csv"
c.bucket("mono-back-office-system-raw-data").blob(src).download_to_filename(dst)
p = Path(dst)
print(f"保存しました: {dst}")
print(f"サイズ: {p.stat().st_size/1024/1024:.1f} MB")
# show header so user knows what columns to expect
import csv
with open(dst, encoding="cp932", errors="replace", newline="") as f:
    hdr = next(csv.reader(f))
print(f"列数: {len(hdr)}")
print("列名:", [h.strip() for h in hdr])
