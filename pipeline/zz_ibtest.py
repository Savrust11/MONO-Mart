import sys, os
from datetime import date
sys.path.insert(0, r"C:\Users\Administrator\Downloads\system\pipeline\scrapers")
import incremental_backfill as IB
uris = IB.fetch_orders_batch("orders", date(2025,9,1), date(2025,9,30),
                             "mono-back-office-system-raw-data",
                             "mono-back-office-system", dry_run=False)
print("URIs:", uris)
# verify size/content of what landed
from google.cloud import storage
c = storage.Client()
for u in uris:
    key = u.replace("gs://mono-back-office-system-raw-data/","")
    data = c.bucket("mono-back-office-system-raw-data").blob(key).download_as_bytes()
    is_html = b"<html" in data[:300].lower() or b"<!doctype" in data[:300].lower()
    print(f"  {key}: {len(data):,} bytes  HTML={is_html}")
    print("   head:", data[:120].decode("cp932","replace").replace(chr(10)," "))
