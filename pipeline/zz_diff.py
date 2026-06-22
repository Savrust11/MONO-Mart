import csv
from google.cloud import storage
c = storage.Client()
b = c.bucket("mono-back-office-system-raw-data")

def header_of(prefix):
    blobs = list(c.list_blobs("mono-back-office-system-raw-data", prefix=prefix))
    if not blobs: return None, None
    data = blobs[0].download_as_bytes()
    text = data.decode("cp932","replace")
    hdr = next(csv.reader(text.splitlines()))
    return [h.strip() for h in hdr], blobs[0].name

# 実装前（古い日付：お気に入り等が無かった頃）と 実装後（最近）を探す
old_hdr, old_name = header_of("uploads/zozo/stock_analysis/2026-06-10/")
new_hdr, new_name = header_of("uploads/zozo/stock_analysis/2026-06-18/")

print("=== 実装前（2026-06-10頃） ===")
print(f"  ファイル: {old_name}")
print(f"  列数: {len(old_hdr) if old_hdr else 'なし'}")
print("=== 実装後（2026-06-18） ===")
print(f"  ファイル: {new_name}")
print(f"  列数: {len(new_hdr)}")

if old_hdr and new_hdr:
    added = [h for h in new_hdr if h not in old_hdr]
    print(f"\n★ 実装で“追加された”列: {added}")
    print(f"  （実装前 {len(old_hdr)}列 → 実装後 {len(new_hdr)}列）")
