from pathlib import Path
from python_calamine import CalamineWorkbook
cands = [r"C:\Users\Administrator\Downloads\【共有】AI商品発注判断支援プロジェクト.xlsx",
         r"C:\Users\Administrator\Downloads\system\data\【共有】AI商品発注判断支援プロジェクト.xlsx"]
f = next((c for c in cands if Path(c).exists()), None)
print("ファイル:", f)
if not f:
    import glob
    for g in glob.glob(r"C:\Users\Administrator\Downloads\**\*AI商品発注*", recursive=True): print(" 候補:", g)
else:
    wb = CalamineWorkbook.from_path(f)
    print("シート一覧:", wb.sheet_names)
    # find the data list tab
    for sn in wb.sheet_names:
        if "データ" in sn or "使用" in sn or "リスト" in sn:
            ws=wb.get_sheet_by_name(sn); rows=ws.to_python()
            print(f"\n=== シート「{sn}」: {len(rows)}行 ===")
            for i,r in enumerate(rows[:40]):
                line=[str(c)[:18] for c in r[:7]]
                if any(x.strip() for x in line): print(f"  行{i+1}: " + " | ".join(line))
