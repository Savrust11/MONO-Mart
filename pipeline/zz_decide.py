from python_calamine import CalamineWorkbook
p = r"C:\Users\Administrator\Downloads\【共有】AI商品発注判断支援プロジェクト (1).xlsx"
wb = CalamineWorkbook.from_path(p)
ws = wb.get_sheet_by_name("社内で決めること")
rows = ws.to_python()
for ri, row in enumerate(rows):
    cells = [("" if c is None else str(c)).strip() for c in row]
    while cells and cells[-1]=="":
        cells.pop()
    if not cells: continue
    print(f"R{ri:02d}| " + " || ".join(cells))
