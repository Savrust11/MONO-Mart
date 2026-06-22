from google.cloud import storage
c = storage.Client()
b = c.bucket("mono-back-office-system-raw-data")
blob = b.blob("uploads/zozo/orders/2025-09-01/2025_09_01_orders.csv")
if blob.exists():
    blob.reload()
    if blob.size < 100000:
        blob.delete(); print("deleted garbage Sep-2025 orders file")
    else:
        print("kept (large)")
else:
    print("not present")
