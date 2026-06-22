from google.cloud import storage
import datetime as dt
c = storage.Client()
b = "mono-back-office-system-raw-data"
dates = set()
for blob in c.list_blobs(b, prefix="uploads/zozo/orders/"):
    parts = blob.name.split("/")
    if len(parts) > 3 and parts[3]:
        dates.add(parts[3])
dates = sorted(d for d in dates if len(d) == 10)
print(f"total order date-folders in GCS: {len(dates)}")
print(f"earliest: {dates[0]}   latest: {dates[-1]}")
# find gaps
ds = [dt.date.fromisoformat(d) for d in dates]
gaps = []
for i in range(1, len(ds)):
    delta = (ds[i] - ds[i-1]).days
    if delta > 1:
        gaps.append((ds[i-1].isoformat(), ds[i].isoformat(), delta-1))
print(f"\ngaps (missing ranges):")
for a,bb,n in gaps:
    print(f"  {a} -> {bb}  ({n} days missing)")
