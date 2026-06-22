import io
from google.cloud import storage
from python_calamine import CalamineWorkbook
c = storage.Client()
bkt = "mono-back-office-system-exports"

for key,label in [("order_management/latest/発注管理表.xlsx","latest(最新URL)"),
                  ("order_management/2026-06-18/発注管理表_20260618.xlsx","6/18 日付指定URL")]:
    blob = c.bucket(bkt).blob(key)
    if not blob.exists():
        print(f"[{label}] 存在しません"); continue
    blob.reload()
    data = blob.download_as_bytes()
    wb = CalamineWorkbook.from_filelike(io.BytesIO(data))
    # 経営者サマリ from title
    summ = wb.get_sheet_by_name("経営者サマリ").to_python()
    title = summ[0][0] if summ and summ[0] else ""
    gen = ""
    for row in summ[:4]:
        for cell in row:
            if "生成日時" in str(cell): gen=str(cell)
    # favorites in 発注管理表
    rows = wb.get_sheet_by_name("発注管理表").to_python()
    hdr=[str(h).strip() for h in rows[0]]
    fi=next(i for i,h in enumerate(hdr) if "お気に入り" in h)
    nz=sum(1 for r in rows[1:] if fi<len(r) and str(r[fi]).strip().isdigit() and int(r[fi])>0)
    print(f"[{label}]")
    print(f"   タイトル: {title}")
    print(f"   {gen}")
    print(f"   更新日時(GCS): {blob.updated}")
    print(f"   Cache-Control: {blob.cache_control}")
    print(f"   お気に入り>0 の行数: {nz}")
    print()
