from google.cloud import storage
c = storage.Client()
bkt = "mono-back-office-system-exports"
print("=== order_management フォルダの中身 ===")
blobs = list(c.list_blobs(bkt, prefix="order_management/"))
if not blobs:
    print("  (発注管理表ファイルが見つかりません)")
for b in sorted(blobs, key=lambda x:x.updated, reverse=True)[:10]:
    pub = ""
    try:
        b.reload()
    except Exception: pass
    print(f"  {b.name}")
    print(f"     更新: {b.updated}  サイズ: {b.size:,} bytes")
# the latest stable file
latest = c.bucket(bkt).blob("order_management/latest/発注管理表.xlsx")
print(f"\nlatest 存在: {latest.exists()}")
if latest.exists():
    latest.reload()
    print(f"  更新日時: {latest.updated}")
    print(f"  公開URL: {latest.public_url}")
