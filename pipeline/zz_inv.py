import io
from google.cloud import storage, bigquery
from python_calamine import CalamineWorkbook
c = storage.Client()
data = c.bucket("mono-back-office-system-exports").blob("order_management/latest/発注管理表.xlsx").download_as_bytes()
wb = CalamineWorkbook.from_filelike(io.BytesIO(data))
rows = wb.get_sheet_by_name("発注管理表").to_python()
hdr=[str(h).strip() for h in rows[0]]
gi=next(i for i,h in enumerate(hdr) if h=="倉庫在庫")
print(f"倉庫在庫列 = {chr(65+gi)}列（index {gi}）")
cnt=0; mx=0; samples=[]
for r in rows[1:]:
    if gi<len(r):
        try: v=float(r[gi])
        except: v=0
        if v>0: cnt+=1; 
        if v>mx: mx=v
        if v>0 and len(samples)<5: samples.append((r[0],r[4],v))
print(f"倉庫在庫>0 の行数 = {cnt} / 全{len(rows)-1}行  最大={mx}")
print("0より大きい例（品番/CS品番/在庫）:", samples)

# BigQuery mart で確認
bq=bigquery.Client(project="mono-back-office-system")
r=list(bq.query("""SELECT COUNT(*) n, COUNTIF(inventory>0) inv, MAX(inventory) mx,
  COUNTIF(order_urgency='CRITICAL') crit FROM `mart_layer.order_analysis` WHERE analysis_date='2026-06-18'""").result())[0]
print(f"\nmart 6/18: 全{r.n} 在庫>0={r.inv} 最大={r.mx} CRITICAL={r.crit}")
