"""
GCS loader — saves raw data to Cloud Storage before BigQuery ingestion.
Acts as the immutable audit log / reprocessing source.
"""
from __future__ import annotations

import gzip
import json
import logging
from datetime import date, datetime
from typing import Any

from google.cloud import storage

from config import GCP_PROJECT_ID

logger = logging.getLogger(__name__)


class GCSLoader:
    def __init__(self, bucket_name: str, project: str | None = None):
        self.client = storage.Client(project=project or GCP_PROJECT_ID)
        self.bucket = self.client.bucket(bucket_name)

    def save_json(
        self,
        data: list[dict[str, Any]],
        gcs_path: str,
        compress: bool = True,
    ) -> str:
        """
        Serialise data as newline-delimited JSON and upload to GCS.
        Returns the full gs:// URI.
        """
        ndjson = "\n".join(json.dumps(row, ensure_ascii=False, default=str) for row in data)
        raw_bytes = ndjson.encode("utf-8")

        if compress:
            content = gzip.compress(raw_bytes)
            content_type = "application/x-ndjson+gzip"
            if not gcs_path.endswith(".gz"):
                gcs_path += ".gz"
        else:
            content = raw_bytes
            content_type = "application/x-ndjson"

        blob = self.bucket.blob(gcs_path)
        blob.upload_from_string(content, content_type=content_type)

        uri = f"gs://{self.bucket.name}/{gcs_path}"
        logger.info("Uploaded %d rows → %s", len(data), uri)
        return uri

    def save_daily_sales(self, data: list[dict], run_date: date | str) -> str:
        path = f"raw/zozo/sales/{run_date}/sales.ndjson"
        return self.save_json(data, path)

    def save_daily_inventory(self, data: list[dict], run_date: date | str) -> str:
        path = f"raw/zozo/inventory/{run_date}/inventory.ndjson"
        return self.save_json(data, path)

    def save_reservations(self, data: list[dict], run_date: date | str) -> str:
        path = f"raw/sheets/reservations/{run_date}/reservations.ndjson"
        return self.save_json(data, path)

    def save_cost_master(self, data: list[dict], run_date: date | str) -> str:
        path = f"raw/cost/{run_date}/cost_master.ndjson"
        return self.save_json(data, path)
