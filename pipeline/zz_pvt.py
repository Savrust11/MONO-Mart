import io
from pathlib import Path
from python_calamine import CalamineWorkbook
f = Path(r"C:\Users\Administrator\Downloads\平均原価詳細20260615 (1).xlsx")
wb = CalamineWorkbook.from_path(str(f))

def cell(v):
    if v is None or v=="": return ""
    if isinstance(v,float):
        return str(int(v)) if v==int(v) else f"{v:.2f}"
    return str(v)

print("================ PVT（期待される答え・赤字＝平均原価の考え方）================")
rows = wb.get_sheet_by_name("PVT").to_python()
for i,r in enumerate(rows):
    line=[cell(c) for c in r[:9]]
    if any(line): print(f" 行{i+1}: " + " | ".join(line))

print("\n================ PF手数料（品番単位の原価＝下代） ================")
rows = wb.get_sheet_by_name("PF手数料").to_python()
hdr=[cell(c) for c in rows[0]]
for j,h in enumerate(hdr):
    if h: print(f"  列{j}({chr(65+j) if j<26 else 'A'+chr(65+j-26)}): {h}")
print("  データ行:", [cell(c) for c in rows[1]])
