import csv
from collections import Counter
f = r"C:\Users\Administrator\Downloads\2024_07_01.csv"
ym = Counter()
mn = "9999"; mx = "0000"; n = 0; bad = 0
with open(f, encoding="cp932", errors="replace", newline="") as fh:
    rdr = csv.reader(fh)
    header = next(rdr)
    di = header.index("注文日")
    for row in rdr:
        n += 1
        if di < len(row):
            d = row[di].strip().replace("/", "-")[:10]  # YYYY-MM-DD
            if len(d) >= 7 and d[:4].isdigit():
                key = d[:7]
                ym[key] += 1
                if d < mn: mn = d
                if d > mx: mx = d
            else:
                bad += 1
print(f"総行数: {n:,}  (日付不正 {bad})")
print(f"注文日レンジ: {mn} 〜 {mx}")
print("\n年月別 件数:")
for k in sorted(ym):
    print(f"  {k}: {ym[k]:,}")
