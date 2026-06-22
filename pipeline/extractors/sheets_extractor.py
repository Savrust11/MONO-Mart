"""
Google Sheets extractor — reads reservation data from the client's spreadsheet.

Expected sheet layout (予約管理 tab):
  A: reservation_id
  B: product_code (品番)
  C: color_code
  D: size
  E: quantity
  F: status  (pending / confirmed / cancelled / shipped)
  G: created_date (YYYY/MM/DD or YYYY-MM-DD)
  H: updated_date

Column positions can be adjusted via SHEETS_COLUMN_MAP env var or here.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Any

import gspread
from google.oauth2.service_account import Credentials

from config import SHEETS_SPREADSHEET_ID, SHEETS_RESERVATION_TAB

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

# Map sheet column name (header row) → our field name
# Adjust these to match the actual sheet headers
COLUMN_MAP: dict[str, str] = {
    "予約ID":        "reservation_id",
    "品番":          "product_code",
    "カラーコード":  "color_code",
    "サイズ":        "size",
    "数量":          "quantity",
    "ステータス":    "status",
    "作成日":        "created_date",
    "更新日":        "updated_date",
    # Fallback English headers (for dev/testing)
    "reservation_id": "reservation_id",
    "product_code":   "product_code",
    "color_code":     "color_code",
    "size":           "size",
    "quantity":       "quantity",
    "status":         "status",
    "created_date":   "created_date",
    "updated_date":   "updated_date",
}

STATUS_NORMALIZER: dict[str, str] = {
    "未処理":    "pending",
    "確認済":    "confirmed",
    "キャンセル": "cancelled",
    "出荷済":    "shipped",
    "pending":   "pending",
    "confirmed": "confirmed",
    "cancelled": "cancelled",
    "shipped":   "shipped",
}


class SheetsExtractor:
    def __init__(self, service_account_json: str, spreadsheet_id: str = SHEETS_SPREADSHEET_ID):
        """
        Args:
            service_account_json: JSON string of service account key
                                  (fetched from Secret Manager by the caller)
            spreadsheet_id: Google Sheets ID
        """
        creds_dict = json.loads(service_account_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        self.client = gspread.authorize(creds)
        self.spreadsheet_id = spreadsheet_id

    def fetch_reservations(self, tab_name: str = SHEETS_RESERVATION_TAB) -> list[dict[str, Any]]:
        """
        Reads all rows from the reservation tab.
        Returns a list of dicts normalised to our schema.
        """
        logger.info("Fetching reservations from Sheets tab '%s'", tab_name)
        sh = self.client.open_by_key(self.spreadsheet_id)
        ws = sh.worksheet(tab_name)

        all_values = ws.get_all_records(head=1, default_blank=None)
        logger.info("Found %d reservation rows", len(all_values))

        today = date.today().isoformat()
        results = []
        for i, row in enumerate(all_values, start=2):  # start=2 because row 1 is header
            try:
                normalized = self._normalize_row(row, today)
                if normalized:
                    results.append(normalized)
            except Exception as exc:
                logger.warning("Skipping row %d — parse error: %s", i, exc)

        return results

    def _normalize_row(self, row: dict, today: str) -> dict | None:
        # Map sheet headers → our field names
        mapped: dict[str, Any] = {}
        for sheet_col, value in row.items():
            field = COLUMN_MAP.get(str(sheet_col).strip())
            if field:
                mapped[field] = value

        reservation_id = str(mapped.get("reservation_id") or "").strip()
        product_code   = str(mapped.get("product_code") or "").strip()
        if not reservation_id or not product_code:
            return None  # skip empty rows

        qty = mapped.get("quantity")
        try:
            qty = int(qty) if qty not in (None, "", "NULL") else 0
        except (ValueError, TypeError):
            qty = 0

        raw_status = str(mapped.get("status") or "pending").strip()
        status = STATUS_NORMALIZER.get(raw_status, "pending")

        return {
            "reservation_id": reservation_id,
            "product_code":   product_code,
            "color_code":     str(mapped.get("color_code") or "").strip() or None,
            "size":           str(mapped.get("size") or "").strip() or None,
            "quantity":       qty,
            "status":         status,
            "created_date":   self._parse_date(mapped.get("created_date")) or today,
            "updated_date":   self._parse_date(mapped.get("updated_date")) or today,
            "source":         "sheets",
        }

    @staticmethod
    def _parse_date(value: Any) -> str | None:
        if not value:
            return None
        for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%m/%d/%Y"):
            try:
                return datetime.strptime(str(value).strip(), fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return None
