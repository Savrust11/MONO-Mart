import csv, io
from pathlib import Path

# locate the file
cands = [r"C:\Users\Administrator\Downloads\2024_07_01.csv",
         r"C:\Users\Administrator\Downloads\system\data\2024_07_01.csv",
         r"C:\Users\Administrator\Downloads\data\2024_07_01.csv"]
f = next((c for c in cands if Path(c).exists()), None)
print("File:", f)
p = Path(f)
print(f"Size: {p.stat().st_size/1024/1024:.0f} MB")

# detect encoding from first bytes
raw = open(f,"rb").read(200000)
enc=None
for e in ("utf-8-sig","cp932","shift_jis","utf-8"):
    try: raw.decode(e); enc=e; break
    except UnicodeDecodeError: continue
print("Encoding:", enc)

# read header + first 3 rows
with open(f, encoding=enc, errors="replace", newline="") as fh:
    rdr = csv.reader(fh)
    header = next(rdr)
    print(f"\nColumns: {len(header)}")
    for i,h in enumerate(header):
        print(f"  [{i}] {h.strip()}")
    print("\n--- first 2 data rows (first 22 cols) ---")
    for i,row in enumerate(rdr):
        if i>=2: break
        print(f"row{i+1}:", [c[:16] for c in row[:22]])
