import io
from pathlib import Path
from python_calamine import CalamineWorkbook
f = Path(r"C:\Users\Administrator\Downloads\平均原価詳細20260615 (1).xlsx")
print(f"ファイル: {f.name}  存在: {f.exists()}")
if f.exists():
    wb = CalamineWorkbook.from_path(str(f))
    print("シート一覧:", wb.sheet_names)
    for sn in wb.sheet_names[:6]:
        ws = wb.get_sheet_by_name(sn)
        rows = ws.to_python()
        print(f"\n=== シート「{sn}」: {len(rows)}行 ===")
        # show first 3 rows, first 12 cols
        for r in rows[:3]:
            print("  ", [str(c)[:14] for c in r[:12]])
        # check for keywords
        flat = " ".join(str(c) for row in rows[:40] for c in row)
        for kw in ("BLEpt1525","sc491","平均原価","下代","最新評価額","PF","SKU"):
            if kw in flat: print(f"   ★「{kw}」を含む")
