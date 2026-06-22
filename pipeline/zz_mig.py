from google.cloud import bigquery
from pathlib import Path
c = bigquery.Client(project="mono-back-office-system")
# add column
c.query("ALTER TABLE `mart_layer.order_analysis` ADD COLUMN IF NOT EXISTS arrival_date STRING").result()
print("✅ ALTER TABLE arrival_date 追加")
# dry-run mart
sql = Path(r"C:\Users\Administrator\Downloads\system\pipeline\sql\dml\06_simple_mart_build.sql").read_text(encoding="utf-8")
cfg = bigquery.QueryJobConfig(dry_run=True, query_parameters=[bigquery.ScalarQueryParameter("target_date","DATE","2026-06-18")])
job = c.query(sql, job_config=cfg)
print(f"✅ mart SQL dry-run OK ({job.total_bytes_processed/1024/1024:.0f}MB)")
