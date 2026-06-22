"""
ZOZO API extractor.

⚠️ The actual ZOZO partner API endpoints must be confirmed with the client.
   This implementation follows a typical REST pattern. Adjust BASE_URL,
   auth headers, and response field names once the real API docs are received.
"""
from __future__ import annotations

import logging
import time
from datetime import date
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import ZOZO_API_BASE_URL, ZOZO_API_KEY

logger = logging.getLogger(__name__)

# Retry on 429 (rate limit) and 5xx server errors
_RETRY_STRATEGY = Retry(
    total=5,
    backoff_factor=2,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"],
    raise_on_status=False,
)


class ZOZOExtractor:
    """Fetches daily sales and inventory snapshots from the ZOZO partner API."""

    PAGE_SIZE = 1000  # adjust to API's max per_page

    def __init__(self, api_key: str = ZOZO_API_KEY, base_url: str = ZOZO_API_BASE_URL):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        adapter = HTTPAdapter(max_retries=_RETRY_STRATEGY)
        self.session.mount("https://", adapter)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def fetch_sales(self, target_date: date | str) -> list[dict[str, Any]]:
        """
        Fetch all SKU-level sales for a given date.
        Returns a list of dicts normalised to our schema.
        """
        target_str = str(target_date)
        logger.info("Fetching ZOZO sales for %s", target_str)
        raw_items = self._paginate("/sales/daily", {"date": target_str})
        return [self._normalize_sale(item, target_str) for item in raw_items]

    def fetch_inventory(self, target_date: date | str) -> list[dict[str, Any]]:
        """
        Fetch inventory snapshot for all SKUs as of target_date.
        Returns a list of dicts normalised to our schema.
        """
        target_str = str(target_date)
        logger.info("Fetching ZOZO inventory snapshot for %s", target_str)
        raw_items = self._paginate("/inventory", {"date": target_str})
        return [self._normalize_inventory(item, target_str) for item in raw_items]

    def fetch_product_master(self) -> list[dict[str, Any]]:
        """Fetch full product/SKU catalogue."""
        logger.info("Fetching ZOZO product master")
        raw_items = self._paginate("/products", {"status": "active"})
        return [self._normalize_product(item) for item in raw_items]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _paginate(self, path: str, params: dict) -> list[dict]:
        """Cursor-based pagination. Returns all pages concatenated."""
        items: list[dict] = []
        cursor: str | None = None

        while True:
            if cursor:
                params = {**params, "cursor": cursor}
            params["per_page"] = self.PAGE_SIZE

            resp = self._get(path, params)
            batch = resp.get("items") or resp.get("data") or []
            items.extend(batch)

            cursor = resp.get("next_cursor") or resp.get("pagination", {}).get("next_cursor")
            if not cursor or len(batch) < self.PAGE_SIZE:
                break

            # Respect rate limit headers if present
            if "X-RateLimit-Remaining" in resp.get("_headers", {}):
                remaining = int(resp["_headers"]["X-RateLimit-Remaining"])
                if remaining < 10:
                    time.sleep(2)

        logger.debug("Fetched %d items from %s", len(items), path)
        return items

    def _get(self, path: str, params: dict) -> dict:
        url = f"{self.base_url}{path}"
        resp = self.session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        data["_headers"] = dict(resp.headers)  # pass rate-limit headers through
        return data

    # ------------------------------------------------------------------
    # Field normalization — map ZOZO API field names → our schema
    # ⚠️ Adjust field names once real API docs are confirmed
    # ------------------------------------------------------------------

    def _normalize_sale(self, item: dict, target_date: str) -> dict:
        return {
            "source_date":    target_date,
            "sku_code":       item.get("sku_id") or item.get("sku_code"),
            "product_code":   item.get("product_id") or item.get("item_code"),
            "color_code":     item.get("color_id") or item.get("color_code"),
            "size":           item.get("size"),
            "sales_qty":      int(item.get("sales_count") or item.get("quantity_sold") or 0),
            "sales_amount":   float(item.get("sales_amount") or 0),
            "favorites_total": int(item.get("wishlist_count") or item.get("favorites") or 0),
            "view_count":     int(item.get("view_count") or 0),
        }

    def _normalize_inventory(self, item: dict, target_date: str) -> dict:
        return {
            "snapshot_date":    target_date,
            "sku_code":         item.get("sku_id") or item.get("sku_code"),
            "product_code":     item.get("product_id") or item.get("item_code"),
            "color_code":       item.get("color_id") or item.get("color_code"),
            "size":             item.get("size"),
            "stock_quantity":   int(item.get("stock") or item.get("quantity") or 0),
            "reserved_quantity": int(item.get("reserved") or item.get("allocated") or 0),
            "incoming_quantity": int(item.get("incoming") or item.get("in_transit") or 0),
            "shelf_type":       item.get("shelf_type") or "通常",
        }

    def _normalize_product(self, item: dict) -> dict:
        return {
            "product_code":     item.get("product_id") or item.get("item_code"),
            "color_code":       item.get("color_id") or item.get("color_code"),
            "size":             item.get("size"),
            "sku_code":         item.get("sku_id") or item.get("sku_code"),
            "product_name":     item.get("name") or item.get("product_name"),
            "maker_color_code": item.get("maker_color_code") or item.get("color_id"),
            "color_name":       item.get("color_name"),
            "shelf_type":       item.get("shelf_type") or "通常",
            "is_active":        bool(item.get("is_active", True)),
        }
