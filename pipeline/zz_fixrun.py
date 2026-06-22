from google.cloud import bigquery
from pathlib import Path
c = bigquery.Client(project="mono-back-office-system")
sql = Path(r"C:\Users\Administrator\Downloads\system\pipeline\sql\dml\06_simple_mart_build.sql").read_text(encoding="utf-8")
# dry-run then run
c.query(sql, job_config=bigquery.QueryJobConfig(dry_run=True, query_parameters=[bigquery.ScalarQueryParameter("target_date","DATE","2026-06-18")]))
c.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("target_date","DATE","2026-06-18")])).result()
r=list(c.query("""SELECT COUNT(*) n, COUNTIF(gross_margin_pct < -100) ext, COUNTIF(gross_margin_pct<0) neg,
  COUNTIF(gross_margin_pct IS NULL) nul, ROUND(MIN(gross_margin_pct),1) mn, ROUND(MAX(gross_margin_pct),1) mx
  FROM `mart_layer.order_analysis` WHERE analysis_date='2026-06-18'""").result())[0]
print(f"✅ mart再構築: 全{r.n}  粗利率<-100%={r.ext}(0が正)  <0={r.neg}  NULL={r.nul}  範囲[{r.mn}%〜{r.mx}%]")
