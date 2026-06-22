from python_calamine import CalamineWorkbook
p = r"C:\Users\Administrator\Downloads\【共有】AI商品発注判断支援プロジェクト (1).xlsx"
wb = CalamineWorkbook.from_path(p)
ws = wb.get_sheet_by_name("データリストメモ")
rows = ws.to_python()
print(f"総行数={len(rows)}")
# R30〜R34あたりを列インデックス付きで縦に表示（へいきん/中央値 と 列名の対応）
for ri in range(28, 35):
    if ri >= len(rows): break
    cells=[("" if c is None else str(c)).strip() for c in rows[ri]]
    print(f"\n--- R{ri} ---")
    for ci,c in enumerate(cells):
        if c: print(f"   col{ci:02d}: {c}")
