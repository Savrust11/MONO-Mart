from python_calamine import CalamineWorkbook
p = r"C:\Users\Administrator\Downloads\【共有】AI商品発注判断支援プロジェクト (1).xlsx"
wb = CalamineWorkbook.from_path(p)
# 全シートから画像/色コード関連のセルを探す
for name in wb.sheet_names:
    ws = wb.get_sheet_by_name(name)
    rows = ws.to_python()
    for ri,row in enumerate(rows):
        for ci,cell in enumerate(row):
            s = "" if cell is None else str(cell)
            if any(k in s for k in ["imgz","カラーコード","色コード","_d.jpg","RIGHT(","b_"]):
                print(f"[{name}] R{ri} C{ci}: {s[:240]}")
