from python_calamine import CalamineWorkbook
p = r"C:\Users\Administrator\Downloads\【共有】AI商品発注判断支援プロジェクト (1).xlsx"
wb = CalamineWorkbook.from_path(p)
ws = wb.get_sheet_by_name("発注管理表項目詳細")
rows = ws.to_python()
print("シート名：発注管理表項目詳細\n")
print("=== 『現在庫日数』『フリー在庫日数』の実際の行位置 ===\n")
for ri, row in enumerate(rows):
    cells = [("" if c is None else str(c)).strip() for c in row]
    joined = " | ".join([x for x in cells if x])
    # 実スプレッドシートの行番号は ri+1
    if any(k in joined for k in ["現在庫日数","フリー在庫日数","日販中央値","日販平均","直近30日","フリー在庫数"]):
        print(f"  スプレッドシート {ri+1} 行目 :  {joined}")
