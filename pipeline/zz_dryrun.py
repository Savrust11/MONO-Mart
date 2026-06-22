from google.cloud import bigquery
from pathlib import Path
c = bigquery.Client(project="mono-back-office-system")
sql = Path(r"C:\Users\Administrator\Downloads\system\pipeline\sql\dml\06_simple_mart_build.sql").read_text(encoding="utf-8")
cfg = bigquery.QueryJobConfig(
    dry_run=True, use_query_cache=False,
    query_parameters=[bigquery.ScalarQueryParameter("target_date","DATE","2026-06-18")])
try:
    job = c.query(sql, job_config=cfg)
    print(f"✅ DRY-RUN OK: 構文エラーなし。処理予定 {job.total_bytes_processed/1024/1024:.1f} MB")
except Exception as e:
    print("❌ SQLエラー:", str(e)[:400])
