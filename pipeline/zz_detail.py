from python_calamine import CalamineWorkbook
p = r"C:\Users\Administrator\Downloads\【共有】AI商品発注判断支援プロジェクト (1).xlsx"
wb = CalamineWorkbook.from_path(p)
ws = wb.get_sheet_by_name("発注管理表項目詳細")
rows = ws.to_python()
print(f"総行数={len(rows)}")
for ri, row in enumerate(rows):
    # trim trailing empties
    cells = [("" if c is None else str(c)).strip() for c in row]
    while cells and cells[-1]=="":
        cells.pop()
    if not cells:
        print(f"R{ri:02d}|")
        continue
    print(f"R{ri:02d}| " + " | ".join(cells))
