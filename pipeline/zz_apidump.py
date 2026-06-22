import json, urllib.request
url="http://localhost:3000/api/period-report?product_code=sc1032&start=2026-05-01&end=2026-05-31"
j=json.load(urllib.request.urlopen(url, timeout=120))
want=["前回発注日","前回原価","画像","CVR","お気に率","CP対象枚数比","入荷数量","UU","合計販売数"]
for row in j["data"]:
    if row["kind"]=="item" and any(w in row["label"] for w in want):
        print(f"  {row['label']} = {row['value']}   [{row['note']}]")
