"""
BigQuery loader — handles raw-layer ingestion and analytics-layer MERGE operations.
"""
from __future__ import annotations

import logging
import uuid
from datetime import date
from typing import Any

from google.cloud import bigquery
from google.cloud.bigquery import QueryJobConfig, ScalarQueryParameter

from config import GCP_PROJECT_ID, BQ_DATASET_RAW, BQ_DATASET_ANALYTICS

logger = logging.getLogger(__name__)


class BigQueryLoader:
    def __init__(self, project: str = GCP_PROJECT_ID):
        self.client = bigquery.Client(project=project)
        self.project = project

    # ------------------------------------------------------------------
    # Raw layer — append-only inserts
    # ------------------------------------------------------------------

    def insert_raw_sales(self, rows: list[dict], source_date: str, source_file: str) -> int:
        """Append sales rows to raw_layer.zozo_sales_raw."""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        enriched = [
            {**row, "ingested_at": now, "raw_json": None, "source_file": source_file}
            for row in rows
        ]
        return self._stream_insert(f"{BQ_DATASET_RAW}.zozo_sales_raw", enriched)

    def insert_raw_inventory(self, rows: list[dict], source_date: str, source_file: str) -> int:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        enriched = [
            {**row, "ingested_at": now, "raw_json": None, "source_file": source_file}
            for row in rows
        ]
        return self._stream_insert(f"{BQ_DATASET_RAW}.zozo_inventory_raw", enriched)

    def insert_raw_reservations(self, rows: list[dict], source_date: str, source_file: str) -> int:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        enriched = [
            {**row, "ingested_at": now, "source_date": source_date,
             "raw_json": None, "source_file": source_file}
            for row in rows
        ]
        return self._stream_insert(f"{BQ_DATASET_RAW}.sheets_reservations_raw", enriched)

    def insert_raw_cost(self, rows: list[dict], source_date: str, source_file: str) -> int:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        enriched = [
            {**row, "ingested_at": now, "source_date": source_date,
             "raw_json": None, "source_file": source_file}
            for row in rows
        ]
        return self._stream_insert(f"{BQ_DATASET_RAW}.excel_cost_raw", enriched)

    # ------------------------------------------------------------------
    # Analytics layer — upsert via MERGE
    # ------------------------------------------------------------------

    def upsert_sales_daily(self, rows: list[dict], target_date: str) -> None:
        """
        Insert or replace sales_daily rows. DELETE is scoped to the actual
        (sale_date, source_file) combinations present in `rows` so the
        orders → shipped → performance pipeline steps don't clobber each
        other when they share the same target_date.

        Bug fix (2026-05-28): the previous implementation deleted by
        sale_date=@target_date alone. csv_performance carries sale_dates 2
        days behind target_date, so its DELETE @target_date wiped the
        csv_orders / csv_shipped rows just inserted for that target_date.
        """
        if not rows:
            return
        table = f"{self.project}.{BQ_DATASET_ANALYTICS}.sales_daily"

        pairs = {(r.get("sale_date"), r.get("source_file"))
                 for r in rows
                 if r.get("sale_date") and r.get("source_file")}
        if pairs:
            sale_dates = sorted({sd for sd, _ in pairs})
            source_files = sorted({sf for _, sf in pairs})
            # Cast date strings via inline literals — IN UNNEST(ARRAY<DATE>)
            # with parametrised STRING array doesn't auto-coerce.
            date_list = ",".join(f"DATE '{d}'" for d in sale_dates)
            self._run_query(f"""
                DELETE FROM `{table}`
                WHERE sale_date IN ({date_list})
                  AND source_file IN UNNEST(@source_files)
            """, {"source_files": source_files})
        self._stream_insert(f"{BQ_DATASET_ANALYTICS}.sales_daily", rows)

    def upsert_inventory_snapshot(self, rows: list[dict], target_date: str) -> None:
        table = f"{self.project}.{BQ_DATASET_ANALYTICS}.inventory_snapshot"
        self._run_query(f"DELETE FROM `{table}` WHERE snapshot_date = @target_date", {
            "target_date": target_date
        })
        if rows:
            self._stream_insert(f"{BQ_DATASET_ANALYTICS}.inventory_snapshot", rows)

    def upsert_reservations(self, rows: list[dict], source_date: str) -> None:
        """
        Replace all reservations for source_date (partition overwrite).
        ZOZO ReserveList rows don't have reservation_id, so we use simple
        DELETE + INSERT by reservation_date.
        """
        table = f"{self.project}.{BQ_DATASET_ANALYTICS}.reservations"
        self._run_query(f"DELETE FROM `{table}` WHERE reservation_date = @target_date", {
            "target_date": source_date
        })
        if rows:
            self._stream_insert(f"{BQ_DATASET_ANALYTICS}.reservations", rows)

    def upsert_pf_fee_master(self, rows: list[dict], snapshot_date: str) -> None:
        """PF手数料 — 品番別下代 (snapshot per date)."""
        table = f"{self.project}.{BQ_DATASET_ANALYTICS}.pf_fee_master"
        self._run_query(
            f"DELETE FROM `{table}` WHERE snapshot_date = @snapshot_date",
            {"snapshot_date": snapshot_date})
        if rows:
            # Strip ingested_at since BQ default fills it
            for r in rows:
                r.pop("ingested_at", None)
            self._stream_insert(f"{BQ_DATASET_ANALYTICS}.pf_fee_master", rows)

    def upsert_cost_master(self, rows: list[dict]) -> None:
        """
        Expire old cost records and insert new ones.
        """
        if not rows:
            return
        today = date.today().isoformat()
        # Close out previously active records for products in this batch
        product_codes = list({r["product_code"] for r in rows})
        placeholders = ", ".join(f"'{pc}'" for pc in product_codes)
        self._run_query(f"""
            UPDATE `{self.project}.{BQ_DATASET_ANALYTICS}.cost_master`
            SET valid_to = DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY)
            WHERE product_code IN ({placeholders})
              AND valid_to IS NULL
        """)
        self._stream_insert(f"{BQ_DATASET_ANALYTICS}.cost_master", rows)

    def upsert_stock_analysis(self, rows: list[dict], target_date: str) -> None:
        """在庫分析データ (No.6) — available_qty per SKU for target_date."""
        table = f"{self.project}.{BQ_DATASET_ANALYTICS}.stock_analysis"
        self._run_query(f"DELETE FROM `{table}` WHERE snapshot_date = @target_date", {
            "target_date": target_date
        })
        if rows:
            self._stream_insert(f"{BQ_DATASET_ANALYTICS}.stock_analysis", rows)

    def upsert_incoming_stock(self, rows: list[dict], target_date: str) -> None:
        """MMS着荷データ — incoming_qty per SKU, aggregated from open POs."""
        table = f"{self.project}.{BQ_DATASET_ANALYTICS}.incoming_stock"
        self._run_query(f"DELETE FROM `{table}` WHERE source_date = @target_date", {
            "target_date": target_date
        })
        if rows:
            self._stream_insert(f"{BQ_DATASET_ANALYTICS}.incoming_stock", rows)

    def upsert_sitateru_item_master(self, rows: list[dict], target_date: str) -> None:
        """sitateru No.12 — daily product master snapshot."""
        table = f"{self.project}.{BQ_DATASET_ANALYTICS}.sitateru_item_master"
        self._run_query(f"DELETE FROM `{table}` WHERE snapshot_date = @target_date", {
            "target_date": target_date
        })
        if rows:
            self._stream_insert(f"{BQ_DATASET_ANALYTICS}.sitateru_item_master", rows)

    def upsert_zozoad_daily(self, rows: list[dict], target_date: str) -> None:
        """ZOZOAD No.7 — ad performance per item per day."""
        table = f"{self.project}.{BQ_DATASET_ANALYTICS}.zozoad_daily"
        self._run_query(f"DELETE FROM `{table}` WHERE record_date = @target_date", {
            "target_date": target_date
        })
        if rows:
            self._stream_insert(f"{BQ_DATASET_ANALYTICS}.zozoad_daily", rows)

    def upsert_sale_settings(self, rows: list[dict], target_date: str) -> None:
        """セール設定 No.17 — current sale configurations snapshot."""
        table = f"{self.project}.{BQ_DATASET_ANALYTICS}.sale_settings"
        self._run_query(f"DELETE FROM `{table}` WHERE snapshot_date = @target_date", {
            "target_date": target_date
        })
        if rows:
            self._stream_insert(f"{BQ_DATASET_ANALYTICS}.sale_settings", rows)

    def upsert_search_keyword_daily(self, rows: list[dict], target_date: str) -> None:
        """検索キーワード経由 No.20 — daily TOP keywords per shop."""
        table = f"{self.project}.{BQ_DATASET_ANALYTICS}.search_keyword_daily"
        # Looker exports may include multiple dates within the latest week;
        # delete all dates present in the payload so each run is idempotent.
        dates = sorted({r.get("record_date") for r in rows if r.get("record_date")})
        if dates:
            date_list = ",".join(f"DATE '{d}'" for d in dates)
            self._run_query(
                f"DELETE FROM `{table}` WHERE record_date IN ({date_list})")
        if rows:
            self._stream_insert(f"{BQ_DATASET_ANALYTICS}.search_keyword_daily", rows)

    def upsert_access_log_daily(self, rows: list[dict], target_date: str) -> None:
        """アクセス実績(新) No.19 — daily PV/DAU per shop × device."""
        table = f"{self.project}.{BQ_DATASET_ANALYTICS}.access_log_daily"
        dates = sorted({r.get("record_date") for r in rows if r.get("record_date")})
        if dates:
            date_list = ",".join(f"DATE '{d}'" for d in dates)
            self._run_query(
                f"DELETE FROM `{table}` WHERE record_date IN ({date_list})")
        if rows:
            self._stream_insert(f"{BQ_DATASET_ANALYTICS}.access_log_daily", rows)

    def upsert_product_reviews(self, rows: list[dict], target_date: str) -> None:
        """商品レビュー No.15 — daily delta of reviews.

        ZOZO BO の検索結果は per-shop TOP50 を返すため、target_date 当日以外の
        レビューも混ざる (例: 当日に投稿が 30 件 + 直近の 20 件)。target_date
        だけ DELETE すると、結果に含まれる過去日の行が翌日も重複 INSERT される。
        payload に登場する review_date 集合を DELETE してから INSERT する形に
        変更 (search_keyword / access_log / coupon と同じ idempotent パターン)。
        """
        table = f"{self.project}.{BQ_DATASET_ANALYTICS}.product_reviews"
        dates = sorted({r.get("review_date") for r in rows
                        if r.get("review_date")})
        if dates:
            date_list = ",".join(f"DATE '{d}'" for d in dates)
            self._run_query(
                f"DELETE FROM `{table}` WHERE review_date IN ({date_list})")
        if rows:
            self._stream_insert(f"{BQ_DATASET_ANALYTICS}.product_reviews", rows)

    def upsert_coupon_exclusion(self, rows: list[dict], target_date: str) -> None:
        """クーポン除外 No.18 — products excluded from coupon on a given day."""
        table = f"{self.project}.{BQ_DATASET_ANALYTICS}.coupon_exclusion"
        self._run_query(f"DELETE FROM `{table}` WHERE exclusion_date = @target_date", {
            "target_date": target_date
        })
        if rows:
            self._stream_insert(f"{BQ_DATASET_ANALYTICS}.coupon_exclusion", rows)

    def upsert_product_master(self, rows: list[dict]) -> None:
        """
        Replace all product_master rows with the latest goods_cs.csv contents.
        Uses TRUNCATE + INSERT (instead of MERGE) since goods_cs.csv contains
        the full active SKU list — no need to preserve old rows.
        """
        if not rows:
            return
        table = f"{self.project}.{BQ_DATASET_ANALYTICS}.product_master"
        # Truncate first to avoid duplicates
        self._run_query(f"TRUNCATE TABLE `{table}`")
        # Then load with explicit destination schema (prevents barcode autodetect as INT)
        self._stream_insert(f"{BQ_DATASET_ANALYTICS}.product_master", rows)

    # ------------------------------------------------------------------
    # Query execution
    # ------------------------------------------------------------------

    def run_sql_file(self, sql_path: str, params: dict[str, Any] | None = None) -> bigquery.QueryJob:
        """Execute a .sql file with optional named parameters."""
        with open(sql_path, encoding="utf-8") as f:
            sql = f.read()
        return self._run_query(sql, params)

    def _run_query(self, sql: str, params: dict[str, Any] | None = None) -> bigquery.QueryJob:
        from google.cloud.bigquery import ArrayQueryParameter
        bq_params = []
        if params:
            for name, value in params.items():
                if isinstance(value, list):
                    sample = value[0] if value else ""
                    elem_type = ("INT64" if isinstance(sample, int)
                                 else "FLOAT64" if isinstance(sample, float)
                                 else "STRING")
                    bq_params.append(ArrayQueryParameter(name, elem_type, value))
                elif isinstance(value, str):
                    bq_params.append(ScalarQueryParameter(name, "STRING", value))
                elif isinstance(value, int):
                    bq_params.append(ScalarQueryParameter(name, "INT64", value))
                elif isinstance(value, float):
                    bq_params.append(ScalarQueryParameter(name, "FLOAT64", value))

        config = QueryJobConfig(query_parameters=bq_params) if bq_params else QueryJobConfig()
        job = self.client.query(sql, job_config=config)
        job.result()  # wait for completion
        if job.errors:
            raise RuntimeError(f"BQ query failed: {job.errors}")
        return job

    def _stream_insert(
        self,
        table_ref: str,
        rows: list[dict],
        create_disposition: str = "CREATE_NEVER",
    ) -> int:
        """
        Insert rows into BigQuery using batch load (load_table_from_json).
        Always uses batch load to avoid streaming buffer conflicts with
        DELETE/MERGE operations that follow shortly after.
        Explicitly fetches table schema to prevent autodetect from coercing
        string fields (like barcode) to integers.
        """
        if not rows:
            return 0

        full_table = f"{self.project}.{table_ref}"

        # Fetch existing table schema to force correct types (prevents autodetect)
        schema = None
        if create_disposition == "CREATE_NEVER":
            try:
                table = self.client.get_table(full_table)
                schema = table.schema
            except Exception:
                schema = None

        job_config = bigquery.LoadJobConfig(
            write_disposition="WRITE_APPEND",
            source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
            create_disposition=create_disposition,
            autodetect=(schema is None and create_disposition == "CREATE_IF_NEEDED"),
            ignore_unknown_values=True,  # tolerate extra fields from extractor
            schema=schema,
        )
        job = self.client.load_table_from_json(rows, full_table, job_config=job_config)
        job.result()
        if job.errors:
            raise RuntimeError(f"BQ load failed: {job.errors}")

        logger.info("Loaded %d rows into %s", len(rows), full_table)
        return len(rows)
