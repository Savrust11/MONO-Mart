from python_calamine import CalamineWorkbook
p = r"C:\Users\Administrator\Downloads\【共有】AI商品発注判断支援プロジェクト (1).xlsx"
wb = CalamineWorkbook.from_path(p)
print("=== シート一覧 ===")
for i,n in enumerate(wb.sheet_names):
    print(f"  [{i}] {n}")
