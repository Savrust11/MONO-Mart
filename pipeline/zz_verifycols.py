import io
from google.cloud import storage
from python_calamine import CalamineWorkbook
c = storage.Client()
data = c.bucket("mono-back-office-system-exports").blob("order_management/latest/発注管理表.xlsx").download_as_bytes()
wb = CalamineWorkbook.from_filelike(io.BytesIO(data))
rows = wb.get_sheet_by_name("発注管理表").to_python()
hdr=[str(h).strip() for h in rows[0]]
print(f"列数: {len(hdr)}")
for i,h in enumerate(hdr):
    col = chr(65+i) if i<26 else "A"+chr(65+i-26)
    mark = " ★NEW" if h in ("最終入荷日","確定発注数") else ""
    print(f"  {col}: {h}{mark}")
# 最終入荷日に値が入っているか
ai=hdr.index("最終入荷日")
vals=[r[ai] for r in rows[1:6] if ai<len(r)]
print(f"\n最終入荷日の先頭5値: {vals}")
ci=hdr.index("確定発注数")
print(f"確定発注数の先頭5値: {[r[ci] for r in rows[1:6] if ci<len(r)]} (手入力欄＝空が正常)")
# 粗利率がまだ正しいか
wi=hdr.index("粗利率(%)")
print(f"粗利率(%)の先頭5値: {[r[wi] for r in rows[1:6] if wi<len(r)]}")
