import csv, io
from google.cloud import storage
c = storage.Client()
data = c.bucket("mono-back-office-system-raw-data").blob("uploads/zozo/stock_analysis/2026-06-18/20260619.csv").download_as_bytes()
for enc in ("utf-8-sig","cp932","shift_jis"):
    try: text=data.decode(enc); print("enc:",enc); break
    except UnicodeDecodeError: continue
rdr=csv.reader(io.StringIO(text))
header=next(rdr)
print(f"\n列数: {len(header)}")
print("全列:", header)
# check target columns
for col in ("お気に入り登録数","バーコード","最終入荷日","継続入荷日"):
    print(f"  {'○' if any(col in h for h in header) else '×'} {col}")
# sample favorites values
fav_i = next((i for i,h in enumerate(header) if "お気に入り登録数" in h), None)
if fav_i is not None:
    vals=[]; nonzero=0; n=0
    for row in rdr:
        n+=1
        if fav_i<len(row):
            v=row[fav_i].strip()
            if n<=5: vals.append(v)
            if v not in ("","0"): nonzero+=1
    print(f"\nお気に入り登録数(列{fav_i}) 先頭5値: {vals}")
    print(f"  全{n}行中、非0の行: {nonzero}")
