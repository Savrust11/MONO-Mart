import csv
from google.cloud import bigquery, storage
c = bigquery.Client(project="mono-back-office-system")

# Fresh file stats
gcs = storage.Client()
data = gcs.bucket("mono-back-office-system-raw-data").blob("uploads/zozo/stock_analysis/2026-06-18/20260619.csv").download_as_bytes()
text = data.decode("cp932","replace")
rdr = list(csv.reader(text.splitlines()))
hdr = rdr[0]
fi = next(i for i,h in enumerate(hdr) if "お気に入り登録数" in h)
ci = next(i for i,h in enumerate(hdr) if h.strip()=="CS品番")
vals=[]; f8=None
for row in rdr[1:]:
    if fi<len(row):
        try: v=int(row[fi])
        except: v=0
        vals.append(v)
        if ci<len(row) and row[ci].strip()=="F8": f8=v
nz=[v for v in vals if v>0]
print("=== 今取得したファイル(fresh) ===")
print(f"  F8={f8}  max={max(vals)}  avg(>0)={sum(nz)/len(nz):.1f}  非0={len(nz)}")

# BigQuery (recovery-ingested) 6/18
r=list(c.query("""SELECT MAX(favorites) mx, AVG(IF(favorites>0,favorites,NULL)) av, COUNTIF(favorites>0) nz,
  MAX(IF(sku_code='F8',favorites,NULL)) f8
  FROM `analytics_layer.stock_analysis` WHERE snapshot_date='2026-06-18'""").result())[0]
print("=== BigQuery(以前の取込) 6/18 ===")
print(f"  F8={r.f8}  max={r.mx}  avg(>0)={r.av:.1f}  非0={r.nz}")
