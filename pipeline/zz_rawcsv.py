import csv, io
from google.cloud import storage
c = storage.Client()
data = c.bucket("mono-back-office-system-raw-data").blob("uploads/zozo/orders/2026-06-16/20260616.csv").download_as_bytes()
for enc in ("utf-8-sig","cp932"):
    try: text=data.decode(enc); break
    except UnicodeDecodeError: continue
rdr = csv.reader(io.StringIO(text))
hdr = next(rdr)
# find columns
def idx(name): 
    for i,h in enumerate(hdr):
        if h.strip()==name: return i
    return -1
i_br=idx("ブランド品番"); i_cs=idx("CS品番"); i_qty=idx("注文数")
i_amt=idx("合計金額（税抜）"); i_up=idx("販売価格（税抜）"); i_pp=idx("プロパー価格（税抜）")
print(f"列位置: ブランド品番={i_br} CS品番={i_cs} 注文数={i_qty} 合計金額={i_amt} 販売価格={i_up} 上代={i_pp}")
print(f"\nヘッダー全体: {[h.strip() for h in hdr]}")
print("\n=== 生CSV: CLEsc1116/S10000 の行 (最大5件) ===")
n=0
for row in rdr:
    if i_br<len(row) and row[i_br].strip()=="CLEsc1116" and i_cs<len(row) and row[i_cs].strip()=="S10000":
        print(f"  注文数={row[i_qty]} 合計金額={row[i_amt]} 販売価格={row[i_up]} 上代={row[i_pp]}")
        n+=1
        if n>=5: break
