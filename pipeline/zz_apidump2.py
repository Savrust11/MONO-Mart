import json, urllib.request
from google.cloud import bigquery
c = bigquery.Client(project="mono-back-office-system")
# sitateruに実原価があり、かつ売上もある品番を1つ
r=list(c.query("""
SELECT s.product_code, ANY_VALUE(s.actual_cost) ac
FROM `analytics_layer.sitateru_item_master` s
JOIN (SELECT DISTINCT product_code FROM `analytics_layer.sales_daily`
      WHERE source_file='orders' AND sale_date BETWEEN '2026-06-01' AND '2026-06-18') d
  ON UPPER(TRIM(s.product_code))=UPPER(TRIM(d.product_code))
WHERE s.actual_cost>0 GROUP BY s.product_code LIMIT 1""").result())
if not r: print("該当品番なし"); raise SystemExit
pc=r[0].product_code; print(f"検証品番={pc}（sitatera実原価={r[0].ac}）\n")
url=f"http://localhost:3000/api/period-report?product_code={pc}&start=2026-06-01&end=2026-06-18"
j=json.load(urllib.request.urlopen(url, timeout=120))
want=["前回原価","CVR","お気に率","CP対象枚数比","入荷数量","合計販売数","粗利率"]
for row in j["data"]:
    if row["kind"]=="item" and any(w in row["label"] and "合計粗利" not in row["label"] for w in want):
        print(f"  {row['label']} = {row['value']}   [{row['note']}]")
