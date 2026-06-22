import csv
f = r"C:\Users\Administrator\Downloads\在庫分析データ_顧客確認用.csv"
rows = list(csv.reader(open(f, encoding="cp932", errors="replace")))
hdr = [h.strip() for h in rows[0]]
def idx(name): return next(i for i,h in enumerate(hdr) if h==name)
i_br=idx("ブランド品番"); i_nm=idx("商品名"); i_col=idx("カラー"); i_sz=idx("サイズ")
i_stk=idx("販売可能数"); i_s7=idx("直近7日販売数"); i_fav=idx("お気に入り登録数")
i_arr=idx("最終入荷日"); i_bc=idx("バーコード")
data=[r for r in rows[1:] if i_fav<len(r) and r[i_fav].strip().isdigit()]
data.sort(key=lambda r:-int(r[i_fav]))
print("【顧客が開いた画面イメージ：在庫分析データ 2026-06-18（お気に入り上位）】\n")
print(f"{'ブランド品番':<10}{'商品名':<22}{'カラー':<8}{'サイズ':<5}{'在庫':>5}{'7日販売':>7}{'お気に入り':>9}{'最終入荷日':>12}")
print("-"*90)
for r in data[:10]:
    nm=(r[i_nm][:20])
    print(f"{r[i_br]:<10}{nm:<22}{r[i_col][:6]:<8}{r[i_sz][:4]:<5}{r[i_stk]:>5}{r[i_s7]:>7}{r[i_fav]:>9}{r[i_arr][:10]:>12}")
print("\n※バーコード列(AD列)も入っています。例:", data[0][i_bc][:30] if i_bc<len(data[0]) else "")
