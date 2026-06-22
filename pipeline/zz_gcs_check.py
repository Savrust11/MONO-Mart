from google.cloud import storage
import os
os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", r"C:\Users\Administrator\Downloads\system\pipeline\sheets-sa-key.json")
c = storage.Client()
bucket = "mono-back-office-system-raw-data"
for sub in ("uploads/zozo/orders/", "uploads/zozo/shipped/"):
    blobs = list(c.list_blobs(bucket, prefix=sub, max_results=20))
    print(f"\n=== gs://{bucket}/{sub} ===")
    if not blobs:
        print("  (empty — no files)")
    else:
        for b in blobs[:20]:
            print(f"  {b.name}  ({b.size} bytes, updated {b.updated})")
