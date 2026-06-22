"""
Pipeline monitoring — Slack alerts + BigQuery audit log.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import requests
from google.cloud import bigquery

from config import GCP_PROJECT_ID, BQ_DATASET_MONITORING, SLACK_WEBHOOK_URL

logger = logging.getLogger(__name__)


class PipelineMonitor:
    def __init__(self, run_date: str):
        self.run_id = str(uuid.uuid4())
        self.run_date = run_date
        self.bq = bigquery.Client(project=GCP_PROJECT_ID)
        self._table = f"{GCP_PROJECT_ID}.{BQ_DATASET_MONITORING}.pipeline_runs"

    def record_start(self, step: str) -> datetime:
        started_at = datetime.now(timezone.utc)
        self._write_row({
            "run_id":      self.run_id,
            "run_date":    self.run_date,
            "step":        step,
            "status":      "running",
            "started_at":  started_at.isoformat(),
            "finished_at": None,
            "rows_processed": None,
            "duration_ms":    None,
            "error_message":  None,
        })
        return started_at

    def record_success(self, step: str, started_at: datetime, rows: int) -> None:
        finished_at = datetime.now(timezone.utc)
        duration_ms = int((finished_at - started_at).total_seconds() * 1000)
        logger.info("[%s] %s completed — %d rows in %dms", self.run_id, step, rows, duration_ms)
        self._write_row({
            "run_id":         self.run_id,
            "run_date":       self.run_date,
            "step":           step,
            "status":         "success",
            "rows_processed": rows,
            "duration_ms":    duration_ms,
            "started_at":     started_at.isoformat(),
            "finished_at":    finished_at.isoformat(),
            "error_message":  None,
        })

    def record_failure(self, step: str, started_at: datetime, error: Exception) -> None:
        finished_at = datetime.now(timezone.utc)
        duration_ms = int((finished_at - started_at).total_seconds() * 1000)
        error_msg = f"{type(error).__name__}: {error}"
        logger.error("[%s] %s FAILED after %dms: %s", self.run_id, step, duration_ms, error_msg)

        self._write_row({
            "run_id":         self.run_id,
            "run_date":       self.run_date,
            "step":           step,
            "status":         "failed",
            "rows_processed": 0,
            "duration_ms":    duration_ms,
            "started_at":     started_at.isoformat(),
            "finished_at":    finished_at.isoformat(),
            "error_message":  error_msg,
        })
        self._slack_alert(step, error_msg)

    def _write_row(self, row: dict[str, Any]) -> None:
        try:
            errors = self.bq.insert_rows_json(self._table, [row])
            if errors:
                logger.warning("Failed to write monitoring row: %s", errors)
        except Exception as exc:
            logger.warning("Monitoring write error (non-fatal): %s", exc)

    def _slack_alert(self, step: str, error_msg: str) -> None:
        if not SLACK_WEBHOOK_URL:
            return
        try:
            payload = {
                "text": (
                    f":x: *ETL Pipeline Failure* [{self.run_date}]\n"
                    f"*Step:* `{step}`\n"
                    f"*Error:* ```{error_msg[:500]}```\n"
                    f"*Run ID:* `{self.run_id}`"
                )
            }
            requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=5)
        except Exception as exc:
            logger.warning("Slack alert failed (non-fatal): %s", exc)
