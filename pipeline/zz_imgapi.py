import json, urllib.request
url="http://localhost:3000/api/period-report?product_code=sc1032&start=2026-05-01&end=2026-05-31"
j=json.load(urllib.request.urlopen(url, timeout=120))
img=None
for row in j["data"]:
    if row["kind"]=="item" and row["label"]=="画像":
        img=row["value"]; print(f"画像 = {row['value']}   [{row['note']}]")
    if row["kind"]=="item" and row["label"] in ("前回原価","CVR(%)","お気に率(%)"):
        print(f"{row['label']} = {row['value']}")
# 画像URLが実際に開けるか
if img and img.startswith("http"):
    try:
        r=urllib.request.urlopen(urllib.request.Request(img, method="HEAD", headers={"User-Agent":"Mozilla/5.0"}), timeout=10)
        print(f"\n画像URL検証: HTTP {r.status} {r.headers.get('Content-Type')} {r.headers.get('Content-Length')}B → {'OK 表示可' if 'image' in r.headers.get('Content-Type','') else 'x'}")
    except Exception as e:
        print("画像URL検証 失敗:", e)
else:
    print("画像URLなし")
