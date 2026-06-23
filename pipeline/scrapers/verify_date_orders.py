"""Verify that a given date's 受注(orders) import landed in BigQuery.

Used by run_recover_dates.ps1 after each backfilled date to PROVE the whole day
loaded for EVERY part number (not just the one the customer noticed).

It reports DAY-LEVEL totals across all products:
  rows, total qty, total amount, and distinct product_code count.
Exit 0 if rows > 0 (day is present), else 1 (still missing -> investigate).

Optionally pass a product_code to additionally spot-check one part number.

Usage:
  python verify_date_orders.py 2026-05-23
  python verify_date_orders.py 2026-05-23 sc1032   # + spot-check SC1032

ENV: GCP_PROJECT_ID (default mono-back-office-system), GOOGLE_APPLICATION_CREDENTIALS
"""
from __future__ import annotations
import os
import sys

from google.cloud import bigquery

PROJECT = os.getenv("GCP_PROJECT_ID", "mono-back-office-system")
DS = os.getenv("BQ_DATASET_ANALYTICS", "analytics_layer")
LOC = os.getenv("BQ_LOCATION", "asia-northeast1")


def _day_totals(bq: bigquery.Client, date: str, product_code: str | None) -> dict:
    where = "source_file = 'orders' AND sale_date = DATE(@d)"
    params = [bigquery.ScalarQueryParameter("d", "STRING", date)]
    if product_code:
        where += " AND UPPER(TRIM(product_code)) = UPPER(TRIM(@pc))"
        params.append(bigquery.ScalarQueryParameter("pc", "STRING", product_code))
    # NB: `rows` is a reserved keyword in BigQuery -> alias must be n_rows.
    q = f"""
      SELECT COUNT(*)                       AS n_rows,
             IFNULL(SUM(sales_quantity), 0) AS qty,
             IFNULL(SUM(sales_amount), 0)   AS amount,
             COUNT(DISTINCT product_code)   AS products
      FROM `{PROJECT}.{DS}.sales_daily`
      WHERE {where}
    """
    job = bq.query(q, job_config=bigquery.QueryJobConfig(query_parameters=params), location=LOC)
    r = list(job)[0]
    return {"rows": r.n_rows, "qty": r.qty, "amount": r.amount, "products": r.products}


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python verify_date_orders.py <YYYY-MM-DD> [product_code]")
        return 2
    date = sys.argv[1]
    pc = sys.argv[2] if len(sys.argv) > 2 else None

    bq = bigquery.Client(project=PROJECT)

    # DAY-LEVEL (all part numbers) — this is what proves the import covered everything.
    day = _day_totals(bq, date, None)
    print(f"VERIFY {date} [ALL products]: rows={day['rows']} "
          f"qty={day['qty']} amount={day['amount']} distinct_products={day['products']}")

    # Optional single-product spot check.
    if pc:
        one = _day_totals(bq, date, pc)
        print(f"VERIFY {date} [{pc}]: rows={one['rows']} qty={one['qty']} amount={one['amount']}")

    # Day is considered recovered only if the whole-day load has rows.
    return 0 if day["rows"] > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
