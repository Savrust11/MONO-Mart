from google.cloud import bigquery
from pathlib import Path
c = bigquery.Client(project="mono-back-office-system")
sql = Path(r"C:\Users\Administrator\Downloads\system\pipeline\sql\dml\06_simple_mart_build.sql").read_text(encoding="utf-8")
c.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("target_date","DATE","2026-06-18")])).result()
r=list(c.query("""SELECT COUNT(*) n, COUNTIF(arrival_date IS NOT NULL) arr FROM `mart_layer.order_analysis` WHERE analysis_date='2026-06-18'""").result())[0]
print(f"✅ mart再構築: {r.n}行 / 最終入荷日あり {r.arr}行")
