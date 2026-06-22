"""
KPI calculator — orchestrates BigQuery SQL transformations.
Runs after raw ingestion to rebuild mart_layer.order_analysis.
"""
from __future__ import annotations

import logging
from pathlib import Path

from loaders.bigquery_loader import BigQueryLoader
from config import (
    GCP_PROJECT_ID,
    BQ_DATASET_ANALYTICS,
    BQ_DATASET_MART,
    TARGET_COVERAGE_WEEKS,
    TREND_COEFF_MIN,
    TREND_COEFF_MAX,
    CRITICAL_STOCK_DAYS,
    WARNING_STOCK_DAYS,
    OVERSTOCK_STOCK_DAYS,
)

logger = logging.getLogger(__name__)
SQL_DIR = Path(__file__).parent.parent / "sql" / "dml"


def run_mart_refresh(bq: BigQueryLoader, target_date: str) -> None:
    """
    Build mart_layer.order_analysis for target_date.
    Idempotent — safe to re-run for the same date.

    Uses the simple Phase-1 SQL (06_simple_mart_build.sql) which only depends
    on the analytics tables that have data populated. The richer
    01_clean_sales / 02_clean_inventory / 03_kpi_metrics chain still references
    legacy color_code and is reserved for Phase 2 once the schema is finalized.
    """
    params = {
        "target_date":          target_date,
        "project_id":           GCP_PROJECT_ID,
        "dataset_analytics":    BQ_DATASET_ANALYTICS,
        "dataset_mart":         BQ_DATASET_MART,
        "coverage_weeks":       TARGET_COVERAGE_WEEKS,
        "trend_coeff_min":      TREND_COEFF_MIN,
        "trend_coeff_max":      TREND_COEFF_MAX,
        "critical_stock_days":  CRITICAL_STOCK_DAYS,
        "warning_stock_days":   WARNING_STOCK_DAYS,
        "overstock_stock_days": OVERSTOCK_STOCK_DAYS,
    }

    steps = [
        # Phase 1 production: simple mart build that works with current schema.
        ("06_simple_mart_build", "06_simple_mart_build.sql"),
    ]

    for step_name, sql_file in steps:
        logger.info("Running transformation step: %s", step_name)
        sql_path = SQL_DIR / sql_file
        bq.run_sql_file(str(sql_path), params)
        logger.info("Completed: %s", step_name)
