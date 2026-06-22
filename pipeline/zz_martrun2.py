from google.cloud import bigquery
from pathlib import Path
c = bigquery.Client(project="mono-back-office-system")
sql = Path(r"C:\Users\Administrator\Downloads\system\pipeline\sql\dml\06_simple_mart_build.sql").read_text(encoding="utf-8")
cfg = bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("target_date","DATE","2026-06-18")])
print("mart 再構築 実行中 (2026-06-18, 異常値ガード撤回版)...")
c.query(sql, job_config=cfg).result()
print("OK mart 再構築 完了")
r=list(c.query("""SELECT COUNT(*) n, COUNTIF(gross_margin_pct < -100) lt100,
  COUNTIF(gross_margin_pct < 0) ltz, COUNTIF(gross_margin_pct IS NULL) nullc,
  ROUND(MIN(gross_margin_pct),0) mn, ROUND(MAX(gross_margin_pct),0) mx
  FROM `mart_layer.order_analysis` WHERE analysis_date='2026-06-18'""").result())[0]
print(f"  全{r.n:,}  粗利率<-100%={r.lt100}(本物の損失が復活)  <0={r.ltz}  NULL={r.nullc}  範囲[{r.mn}% ~ {r.mx}%]")
