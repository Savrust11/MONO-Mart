"""
Excel cost master extractor.

Reads the latest cost Excel file uploaded to GCS by staff.
Expected columns (configurable via COST_COLUMN_MAP):
  品番, カラー, 原価, 売価, 発注数
"""
from __future__ import annotations

import io
import logging
import re
from datetime import date
from typing import Any

import openpyxl
from google.cloud import storage

from config import GCS_INPUTS_BUCKET

logger = logging.getLogger(__name__)

# Map Excel column header → our field name
COST_COLUMN_MAP: dict[str, str] = {
    "品番":           "product_code",
    "商品コード":     "product_code",
    "カラー":         "color_code",
    "カラーコード":   "color_code",
    "原価":           "cost_price",
    "仕入れ単価":     "cost_price",
    "売価":           "retail_price",
    "販売単価":       "retail_price",
    "発注数":         "production_lot_size",
    "生産数":         "production_lot_size",
    # English fallbacks
    "product_code":        "product_code",
    "color_code":          "color_code",
    "cost_price":          "cost_price",
    "retail_price":        "retail_price",
    "production_lot_size": "production_lot_size",
}


class ExcelCostExtractor:
    """
    Scans GCS inputs bucket for the newest Excel cost file,
    downloads it, and parses it into a list of dicts.
    """

    def __init__(
        self,
        bucket_name: str = GCS_INPUTS_BUCKET,
        prefix: str = "cost/",
    ):
        from config import GCP_PROJECT_ID
        self.gcs_client = storage.Client(project=GCP_PROJECT_ID)
        self.bucket_name = bucket_name
        self.prefix = prefix

    def load_latest(self) -> list[dict[str, Any]]:
        """
        Finds the most recently uploaded .xlsx file under the cost/ prefix
        and parses it.
        """
        blob = self._find_latest_blob()
        if blob is None:
            logger.warning("No cost Excel file found in gs://%s/%s", self.bucket_name, self.prefix)
            return []

        logger.info("Loading cost master from gs://%s/%s", self.bucket_name, blob.name)
        data = blob.download_as_bytes()
        rows = self._parse_excel(data, blob.name)
        logger.info("Parsed %d cost rows from %s", len(rows), blob.name)
        return rows

    def load_from_path(self, gcs_path: str) -> list[dict[str, Any]]:
        """Load a specific GCS path (e.g. gs://bucket/cost/file.xlsx)."""
        path = gcs_path.replace(f"gs://{self.bucket_name}/", "")
        bucket = self.gcs_client.bucket(self.bucket_name)
        blob = bucket.blob(path)
        data = blob.download_as_bytes()
        return self._parse_excel(data, gcs_path)

    def _find_latest_blob(self):
        bucket = self.gcs_client.bucket(self.bucket_name)
        blobs = list(bucket.list_blobs(prefix=self.prefix))
        xlsx_blobs = [b for b in blobs if b.name.endswith((".xlsx", ".xlsm"))]
        if not xlsx_blobs:
            return None
        return max(xlsx_blobs, key=lambda b: b.updated)

    def _parse_excel(self, data: bytes, source_file: str) -> list[dict[str, Any]]:
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        ws = wb.active  # use first (active) sheet

        rows_iter = ws.iter_rows(values_only=True)

        # Find header row — search first 5 rows for a row containing 品番 or product_code
        header_map: dict[int, str] = {}
        for _ in range(5):
            row_values = next(rows_iter, None)
            if row_values is None:
                break
            for col_idx, cell_val in enumerate(row_values):
                if cell_val is None:
                    continue
                cell_str = str(cell_val).strip()
                if cell_str in COST_COLUMN_MAP:
                    header_map[col_idx] = COST_COLUMN_MAP[cell_str]
            if "product_code" in header_map.values():
                break  # found the header row

        if "product_code" not in header_map.values():
            logger.error("Could not find header row with 品番 in %s", source_file)
            return []

        today = date.today().isoformat()
        results = []
        for row_values in rows_iter:
            if all(v is None for v in row_values):
                continue  # skip blank rows

            record: dict[str, Any] = {
                "valid_from":  today,
                "valid_to":    None,
                "source_file": source_file,
            }
            for col_idx, field_name in header_map.items():
                if col_idx < len(row_values):
                    record[field_name] = row_values[col_idx]

            # Skip rows without a product code
            product_code = record.get("product_code")
            if not product_code or str(product_code).strip() == "":
                continue

            # Type coercions
            record["product_code"] = str(record["product_code"]).strip()
            record["color_code"]   = str(record.get("color_code") or "").strip() or None
            record["cost_price"]   = self._to_float(record.get("cost_price"))
            record["retail_price"] = self._to_float(record.get("retail_price"))
            record["production_lot_size"] = self._to_int(record.get("production_lot_size"))

            results.append(record)

        wb.close()
        return results

    @staticmethod
    def _to_float(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(str(value).replace(",", "").replace("¥", "").strip())
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _to_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(float(str(value).replace(",", "").strip()))
        except (ValueError, TypeError):
            return None
