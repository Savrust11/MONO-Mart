from google.cloud import storage
c = storage.Client()
b = "mono-back-office-system-raw-data"
for key in ("uploads/zozo/orders/2025-09-01/2025_09_01_orders.csv",):
    data = c.bucket(b).blob(key).download_as_bytes()
    print(f"=== {key} ({len(data)} bytes) ===")
    for enc in ("utf-8-sig","cp932","shift_jis","utf-8"):
        try:
            text = data.decode(enc); print(f"(decoded {enc})"); break
        except UnicodeDecodeError: continue
    print(text[:1500])
