import json, urllib.request
from google.cloud import bigquery
c = bigquery.Client(project="mono-back-office-system")
# MMS発注があり、売上もある品番を1つ
r=list(c.query("""SELECT o.product_code, MAX(o.order_date) d, COUNT(*) n
FROM `analytics_layer.mms_orders` o
JOIN (SELECT DISTINCT product_code FROM `analytics_layer.sales_daily` WHERE source_file='orders') s
  ON UPPER(TRIM(o.product_code))=UPPER(TRIM(s.product_code))
GROUP BY o.product_code ORDER BY n DESC LIMIT 1""").result())
pc=r[0].product_code
print(f"検証品番={pc}（MMS最新発注={r[0].d}）\n")
# sc1032 と この品番の両方をAPIで確認
for code in ["sc1032", pc]:
    url=f"http://localhost:3000/api/period-report?product_code={code}&start=2026-05-01&end=2026-05-31"
    j=json.load(urllib.request.urlopen(url, timeout=120))
    print(f"=== {code} ===")
    for row in j["data"]:
        if row["kind"]=="item" and row["label"] in ("前回発注日","前回原価","画像","CVR(%)","合計粗利率(%)"):
            v=row["value"]; v=(v[:48] if isinstance(v,str) else v)
            print(f"  {row['label']} = {v}")
