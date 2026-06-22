from google.cloud import bigquery
c = bigquery.Client(project="mono-back-office-system")
q = """
SELECT source_file, COUNT(DISTINCT sale_date) days, MIN(sale_date) lo, MAX(sale_date) hi, COUNT(*) n
FROM `analytics_layer.sales_daily`
WHERE sale_date BETWEEN '2024-07-01' AND '2024-07-31'
GROUP BY source_file ORDER BY source_file
"""
rows=list(c.query(q).result())
if not rows: print("(nothing for July 2024 yet)")
for r in rows:
    print(f"  {r.source_file:8s} days={r.days}/31  {r.lo}..{r.hi}  rows={r.n}")
