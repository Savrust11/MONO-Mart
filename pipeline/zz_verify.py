from python_calamine import CalamineWorkbook
p = r"C:\Users\Administrator\Downloads\【共有】AI商品発注判断支援プロジェクト (1).xlsx"
wb = CalamineWorkbook.from_path(p)
import re
KEYS = ["在庫日数","中央値","平均","UU","ユニーク","レビュー","件数","点数","評価"]
for name in ["発注管理表 案1","発注管理表 案2","データリストメモ","社内で決めること","発注管理表項目詳細"]:
    ws = wb.get_sheet_by_name(name)
    rows = ws.to_python()
    print(f"\n========== {name} : 関連行のみ ==========")
    for ri,row in enumerate(rows):
        cells=[("" if c is None else str(c)).strip() for c in row]
        joined=" | ".join([c for c in cells if c])
        if any(k in joined for k in KEYS):
            print(f"  R{ri:02d}: {joined[:200]}")
