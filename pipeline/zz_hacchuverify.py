import sys
sys.path.insert(0, r"C:\Users\Administrator\Downloads\system\pipeline")
sys.path.insert(0, r"C:\Users\Administrator\Downloads\system\pipeline\extractors")
from google.cloud import storage
import csv, io
c = storage.Client()
bk = c.bucket("mono-back-office-system-raw-data")
# 最新の hacchu CSV を探す
blobs = sorted([b for b in bk.list_blobs(prefix="uploads/zozo/") if "tableau/hacchu" in b.name and b.name.endswith(".csv")], key=lambda b: b.name)
if not blobs:
    blobs = sorted([b for b in bk.list_blobs(prefix="uploads/") if "tableau/hacchu" in b.name], key=lambda b: b.name)
print("hacchu CSV件数:", len(blobs))
if not blobs:
    raise SystemExit("hacchu CSV が見つからない")
blob = blobs[-1]
print("使用:", blob.name)
data = blob.download_as_bytes()

# 修正後の抽出器で解析
from tableau_extractor import TableauExtractor
ext = TableauExtractor()
recs = ext.parse_hacchu_meisai(data, "2026-06-20")
print(f"\n解析結果: {len(recs)} 件（入荷残）")
# 生CSVの ZOZO納品予定日 / 本納品日 列の有無
headers = data.decode("utf-8","replace").splitlines()[0].split(",")
print("ZOZO納品予定日 列あり:", "ZOZO納品予定日" in headers, " / 本納品日 列あり:", "本納品日" in headers)
print("\n=== サンプル（入荷予定日 = 修正後の値）===")
for r in recs[:8]:
    print(f"  {str(r['product_code'])[:14]:<14} {str(r.get('color_name') or '')[:8]:<8} 入荷予定日={r['earliest_arrival_date']} 入荷残={r['incoming_qty']}")
