from pathlib import Path
from python_calamine import CalamineWorkbook
from collections import defaultdict
f = Path(r"C:\Users\Administrator\Downloads\平均原価詳細20260615 (1).xlsx")
wb = CalamineWorkbook.from_path(str(f))

# ① PF手数料: 品番 → 下代(Q列=16)
pf = {}
pr = wb.get_sheet_by_name("PF手数料").to_python()
for r in pr[1:]:
    if len(r)>16 and r[4]:
        try: pf[str(r[4]).strip()] = float(r[16])
        except: pass
print("PF手数料表:", pf)

# ② 評価額一覧: SKU(I列=8) → 最新評価額(G列=6)
mms = {}
er = wb.get_sheet_by_name("評価額一覧").to_python()
for r in er[1:]:
    if len(r)>8 and r[8]:
        try: mms[str(r[8]).strip()] = float(r[6])
        except: pass
print(f"評価額一覧: {len(mms)}SKU (例 sc491S1={mms.get('sc491S1')})")

# ③ 受注データ: ヘッダーから列を特定
od = wb.get_sheet_by_name("20260615").to_python()
hdr=[str(c).strip() for c in od[0]]
i_br=hdr.index("ブランド品番"); i_cs=hdr.index("CS品番"); i_qty=hdr.index("注文数")
print(f"\n受注 列: ブランド品番={i_br} CS品番={i_cs} 注文数={i_qty}")

# ④ 各受注行に原価をあてて集計（PF優先→MMS）
agg=defaultdict(lambda:[0.0,0.0])  # 品番 -> [原価額, 注文数]
miss=0
for r in od[1:]:
    if i_qty>=len(r) or not r[i_br]: continue
    br=str(r[i_br]).strip(); cs=str(r[i_cs]).strip() if i_cs<len(r) else ""
    try: qty=float(r[i_qty])
    except: continue
    if br in pf: cost=pf[br]            # PF優先（品番単位）
    elif br+cs in mms: cost=mms[br+cs]  # MMS（SKU単位）
    else: miss+=1; continue
    agg[br][0]+=qty*cost; agg[br][1]+=qty

print("\n=== 実装ロジックの計算結果 ===")
for br,(tc,tq) in agg.items():
    print(f"  {br}: 合計原価額={tc:,.0f}  合計注文数={tq:,.0f}  平均原価={tc/tq:.2f}")
print(f"  原価不明 {miss}行")
print("\n→ PVTの正解: BLEpt1525 平均原価=1,080 (447,120÷414)")
