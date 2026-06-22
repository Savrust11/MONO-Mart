"""Quick test: rebuild mart for 2026-05-05 and show urgency counts."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from loaders.bigquery_loader import BigQueryLoader
from transformers.kpi_calculator import run_mart_refresh

bq = BigQueryLoader(project=config.GCP_PROJECT_ID)

print("=" * 60)
print(f"Rebuilding mart_layer.order_analysis for 2026-05-05 ...")
print("=" * 60)

run_mart_refresh(bq, "2026-05-05")
print("✅ Mart rebuild SUCCESS")
print()

sql = f"""
SELECT order_urgency, COUNT(*) AS n
FROM `{config.GCP_PROJECT_ID}.mart_layer.order_analysis`
WHERE analysis_date = DATE('2026-05-05')
GROUP BY order_urgency
ORDER BY n DESC
"""
print("Urgency distribution for 2026-05-05:")
for row in bq.client.query(sql).result():
    print(f"  {row.order_urgency:<12} {row.n:>12,} SKUs")
