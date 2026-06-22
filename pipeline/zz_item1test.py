import json, urllib.request
url="http://localhost:3000/api/period-report?product_code=sc1032&start=2026-05-01&end=2026-05-31"
j=json.load(urllib.request.urlopen(url, timeout=120))
want=["ブランド","販売タイプ","推奨発注数","現在庫数","フリー在庫数","30日 販売数","合計販売数"]
for row in j["data"]:
    if row["kind"]=="item" and any(w in row["label"] for w in want):
        v=row["value"]; v=(v[:40] if isinstance(v,str) else v)
        print(f"  {row['label']} = {v}   [{row['note'][:40]}]")
