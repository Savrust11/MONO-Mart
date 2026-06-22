from google.cloud import bigquery
from pathlib import Path
c = bigquery.Client(project="mono-back-office-system")
sql = Path(r"C:\Users\Administrator\Downloads\system\pipeline\sql\dml\06_simple_mart_build.sql").read_text(encoding="utf-8")
cfg = bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("target_date","DATE","2026-06-18")])
print("mart 再構築 実行中 (2026-06-18)...")
c.query(sql, job_config=cfg).result()
print("✅ mart 再構築 完了")
# verify cost
r=list(c.query("""SELECT COUNT(*) n, COUNTIF(cost_price>0) cp, ROUND(AVG(cost_price),2) avgc,
  ROUND(SUM(period_total_cost)) tot_cost, ROUND(AVG(gross_margin_pct),1) gm
  FROM `mart_layer.order_analysis` WHERE analysis_date='2026-06-18'""").result())[0]
print(f"  行数{r.n:,}  原価>0={r.cp:,}  平均SKU原価={r.avgc}  30日原価合計={r.tot_cost:,.0f}  平均粗利率={r.gm}%")
