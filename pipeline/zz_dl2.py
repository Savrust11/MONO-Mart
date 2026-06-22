from google.cloud import storage
from pathlib import Path
import csv
c = storage.Client()
src = "uploads/zozo/stock_analysis/2026-06-18/20260619.csv"
dst = r"C:\Users\Administrator\Downloads\在庫分析データ_顧客確認用.csv"
c.bucket("mono-back-office-system-raw-data").blob(src).download_to_filename(dst)
print(f"用意しました: {dst}")
print(f"サイズ: {Path(dst).stat().st_size/1024/1024:.1f} MB")
with open(dst, encoding="cp932", errors="replace", newline="") as f:
    rdr=csv.reader(f); hdr=next(rdr)
    # find favorites column index
    fav_i = next(i for i,h in enumerate(hdr) if "お気に入り登録数" in h)
    cs_i = next(i for i,h in enumerate(hdr) if h.strip()=="CS品番")
    # find F8 sample
    f8=None; n=0
    for row in rdr:
        n+=1
        if cs_i<len(row) and row[cs_i].strip()=="F8" and not f8:
            f8=row[fav_i]
print(f"列数: {len(hdr)}  /  お気に入り列 = {chr(65+fav_i) if fav_i<26 else 'A'+chr(65+fav_i-26)}列目")
print(f"サンプル: CS品番 F8 のお気に入り登録数 = {f8}")
