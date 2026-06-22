import io
from google.cloud import storage
from python_calamine import CalamineWorkbook
c = storage.Client()
data = c.bucket("mono-back-office-system-exports").blob("order_management/latest/発注管理表.xlsx").download_as_bytes()
wb = CalamineWorkbook.from_filelike(io.BytesIO(data))
print("シート:", wb.sheet_names)
ws = wb.get_sheet_by_name("発注管理表")
rows = ws.to_python()
hdr = [str(h).strip() for h in rows[0]]
fi = next(i for i,h in enumerate(hdr) if "お気に入り" in h)
col_letter = chr(65+fi) if fi<26 else "A"+chr(65+fi-26)
print(f"お気に入り登録数 = {col_letter}列（{fi+1}番目）")
vals=[]
for r in rows[1:]:
    if fi<len(r):
        try: vals.append(int(r[fi]))
        except: vals.append(0)
nz=[v for v in vals if v>0]
print(f"発注管理表シート: {len(rows)-1}行")
print(f"お気に入り>0 の行: {len(nz)} / 最大: {max(vals)} / 先頭5値: {vals[:5]}")
