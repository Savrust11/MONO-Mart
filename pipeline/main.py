"""
ETL Pipeline entry point — runs as a Cloud Run Job triggered nightly.

Usage:
  python main.py                           # process yesterday (JST)
  python main.py --date 2025-11-03         # process specific date
  python main.py --serve                   # HTTP server mode for Cloud Run Job trigger
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timedelta

from flask import Flask, jsonify, request
from google.cloud import secretmanager

import config
from config import JST, GCP_PROJECT_ID
from extractors.zozo_extractor import ZOZOExtractor
from extractors.zozo_csv_extractor import ZOZOCsvExtractor
from extractors.mms_extractor import MMSExtractor
from extractors.sheets_extractor import SheetsExtractor
from extractors.excel_extractor import ExcelCostExtractor
from extractors.sitateru_extractor import SitateruExtractor
from extractors.tableau_extractor import TableauExtractor
from loaders.gcs_loader import GCSLoader
from loaders.bigquery_loader import BigQueryLoader
from transformers.kpi_calculator import run_mart_refresh
from monitoring import PipelineMonitor
from validators.data_validator import DataValidator, write_quality_report

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)


def get_secret(secret_id: str) -> str:
    """Fetch a secret value from Google Secret Manager."""
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{GCP_PROJECT_ID}/secrets/{secret_id}/versions/latest"
    resp = client.access_secret_version(request={"name": name})
    return resp.payload.data.decode("utf-8")


def run_pipeline(target_date: str) -> dict:
    """
    Full ETL pipeline for a single date.
    Returns a summary dict with step results.
    """
    logger.info("=" * 60)
    logger.info("Starting ETL pipeline for date: %s", target_date)
    logger.info("=" * 60)

    monitor   = PipelineMonitor(run_date=target_date)
    validator = DataValidator()
    gcs = GCSLoader(bucket_name=config.GCS_RAW_BUCKET)
    bq  = BigQueryLoader(project=GCP_PROJECT_ID)
    summary = {"date": target_date, "steps": {}, "quality": {}}

    # ------------------------------------------------------------------
    # Step 1: Extract ZOZO sales
    # ------------------------------------------------------------------
    step = "extract_zozo_sales"
    started = monitor.record_start(step)
    try:
        zozo_api_key = get_secret("ZOZO_API_KEY")
        zozo = ZOZOExtractor(api_key=zozo_api_key)
        sales_data = zozo.fetch_sales(target_date)
        gcs_path = gcs.save_daily_sales(sales_data, target_date)
        bq.insert_raw_sales(sales_data, target_date, gcs_path)
        bq.upsert_sales_daily(
            [{"sale_date": target_date, **r} for r in sales_data],
            target_date,
        )
        # Validate
        qr = validator.validate_sales(sales_data, target_date)
        write_quality_report(bq.client, GCP_PROJECT_ID, qr)
        monitor.record_success(step, started, len(sales_data))
        summary["steps"][step] = {"rows": len(sales_data), "status": "ok"}
        summary["quality"]["zozo_sales"] = qr.summary()
    except Exception as exc:
        monitor.record_failure(step, started, exc)
        summary["steps"][step] = {"status": "failed", "error": str(exc)}
        raise  # abort pipeline on critical step failure

    # ------------------------------------------------------------------
    # Step 2: Extract ZOZO inventory
    # ------------------------------------------------------------------
    step = "extract_zozo_inventory"
    started = monitor.record_start(step)
    try:
        inventory_data = zozo.fetch_inventory(target_date)
        gcs_path = gcs.save_daily_inventory(inventory_data, target_date)
        bq.insert_raw_inventory(inventory_data, target_date, gcs_path)
        bq.upsert_inventory_snapshot(
            [{"snapshot_date": target_date, **r} for r in inventory_data],
            target_date,
        )
        qr = validator.validate_inventory(inventory_data, target_date)
        write_quality_report(bq.client, GCP_PROJECT_ID, qr)
        monitor.record_success(step, started, len(inventory_data))
        summary["steps"][step] = {"rows": len(inventory_data), "status": "ok"}
        summary["quality"]["zozo_inventory"] = qr.summary()
    except Exception as exc:
        monitor.record_failure(step, started, exc)
        summary["steps"][step] = {"status": "failed", "error": str(exc)}
        raise

    # ------------------------------------------------------------------
    # Step 3: Extract reservations from Google Sheets
    # ------------------------------------------------------------------
    step = "extract_sheets_reservations"
    started = monitor.record_start(step)
    try:
        sheets_sa_json = get_secret("GOOGLE_SA_JSON")
        sheets_id      = get_secret("SHEETS_SPREADSHEET_ID")
        sheets = SheetsExtractor(service_account_json=sheets_sa_json, spreadsheet_id=sheets_id)
        reservations = sheets.fetch_reservations()
        gcs_path = gcs.save_reservations(reservations, target_date)
        bq.insert_raw_reservations(reservations, target_date, gcs_path)
        bq.upsert_reservations(reservations, target_date)
        qr = validator.validate_reservations(reservations, target_date)
        write_quality_report(bq.client, GCP_PROJECT_ID, qr)
        monitor.record_success(step, started, len(reservations))
        summary["steps"][step] = {"rows": len(reservations), "status": "ok"}
        summary["quality"]["sheets_reservations"] = qr.summary()
    except Exception as exc:
        monitor.record_failure(step, started, exc)
        summary["steps"][step] = {"status": "failed", "error": str(exc)}
        logger.warning("Reservations step failed — continuing with stale data: %s", exc)

    # ------------------------------------------------------------------
    # Step 4: Extract cost master from Excel
    # ------------------------------------------------------------------
    step = "extract_cost_excel"
    started = monitor.record_start(step)
    try:
        excel = ExcelCostExtractor()
        cost_data = excel.load_latest()
        if cost_data:
            gcs_path = gcs.save_cost_master(cost_data, target_date)
            bq.insert_raw_cost(cost_data, target_date, gcs_path)
            bq.upsert_cost_master(cost_data)
        qr = validator.validate_cost_master(cost_data, target_date)
        write_quality_report(bq.client, GCP_PROJECT_ID, qr)
        monitor.record_success(step, started, len(cost_data))
        summary["steps"][step] = {"rows": len(cost_data), "status": "ok"}
        summary["quality"]["excel_cost_master"] = qr.summary()
    except Exception as exc:
        monitor.record_failure(step, started, exc)
        summary["steps"][step] = {"status": "failed", "error": str(exc)}
        logger.warning("Cost master step failed — continuing with existing cost data: %s", exc)

    # ------------------------------------------------------------------
    # Step 5: Update product master
    # ------------------------------------------------------------------
    step = "sync_product_master"
    started = monitor.record_start(step)
    try:
        products = zozo.fetch_product_master()
        bq.upsert_product_master(products)
        monitor.record_success(step, started, len(products))
        summary["steps"][step] = {"rows": len(products), "status": "ok"}
    except Exception as exc:
        monitor.record_failure(step, started, exc)
        summary["steps"][step] = {"status": "failed", "error": str(exc)}
        logger.warning("Product master sync failed — using existing master: %s", exc)

    # ------------------------------------------------------------------
    # Step 6: Rebuild KPI mart (BigQuery SQL)
    # ------------------------------------------------------------------
    step = "rebuild_kpi_mart"
    started = monitor.record_start(step)
    try:
        run_mart_refresh(bq, target_date)
        monitor.record_success(step, started, 0)
        summary["steps"][step] = {"status": "ok"}
    except Exception as exc:
        monitor.record_failure(step, started, exc)
        summary["steps"][step] = {"status": "failed", "error": str(exc)}
        raise

    logger.info("Pipeline complete: %s", json.dumps(summary, ensure_ascii=False))
    return summary


def run_csv_ingestion(gcs_prefix: str, target_date: str) -> dict:
    """
    CSV ingestion mode — process manually uploaded ZOZOBO / MMS CSV files.

    Upload convention:
      gs://{bucket}/uploads/zozo/orders/{date}/yyyy_mm_dd.csv
      gs://{bucket}/uploads/zozo/shipped/{date}/yyyy_mm_dd.csv
      gs://{bucket}/uploads/zozo/reservations/{date}/yyyymmdd_ReserveList.csv
      gs://{bucket}/uploads/zozo/inventory_sku/{date}/syyyymmdd.csv
      gs://{bucket}/uploads/zozo/stock_analysis/{date}/yyyymmdd.csv
      gs://{bucket}/uploads/zozo/zozoad/{date}/Detail.csv
      gs://{bucket}/uploads/zozo/performance/{date}/商品別実績_yyyymmdd.csv
      gs://{bucket}/uploads/zozo/product_master/{date}/goods_cs.csv
      gs://{bucket}/uploads/zozo/sale/{date}/salegoods.csv
      gs://{bucket}/uploads/zozo/coupon/{date}/{brand_name}_yyyymmdd.csv
      gs://{bucket}/uploads/mms/cost/{date}/評価額一覧-MMS.csv
      gs://{bucket}/uploads/mms/incoming/{date}/mms_order_data.*.csv

    After loading, rebuilds the KPI mart for target_date.
    """
    logger.info("CSV ingestion mode: prefix=%s date=%s", gcs_prefix, target_date)

    from google.cloud import storage as gcs_storage
    gcs_client = gcs_storage.Client(project=GCP_PROJECT_ID)
    bq = BigQueryLoader(project=GCP_PROJECT_ID)
    monitor = PipelineMonitor(run_date=target_date)
    zozo_csv = ZOZOCsvExtractor()
    mms_csv = MMSExtractor()
    sitateru_csv = SitateruExtractor()
    tableau_csv = TableauExtractor()
    summary: dict = {"date": target_date, "steps": {}}

    bucket_name = config.GCS_RAW_BUCKET
    bucket = gcs_client.bucket(bucket_name)

    def _load_blobs(subfolder: str) -> list:
        prefix = f"{gcs_prefix.rstrip('/')}/{subfolder}/{target_date}/"
        return list(bucket.list_blobs(prefix=prefix))

    # Orders (受注)
    step = "csv_orders"
    started = monitor.record_start(step)
    try:
        rows: list = []
        for blob in _load_blobs("zozo/orders"):
            rows.extend(zozo_csv.parse_orders(blob.download_as_bytes(), target_date))
        if rows:
            bq.upsert_sales_daily(rows, target_date)
        monitor.record_success(step, started, len(rows))
        summary["steps"][step] = {"rows": len(rows), "status": "ok"}
    except Exception as exc:
        monitor.record_failure(step, started, exc)
        summary["steps"][step] = {"status": "failed", "error": str(exc)}

    # Shipped (発送)
    step = "csv_shipped"
    started = monitor.record_start(step)
    try:
        rows = []
        for blob in _load_blobs("zozo/shipped"):
            rows.extend(zozo_csv.parse_orders(blob.download_as_bytes(), target_date, is_shipped=True))
        if rows:
            bq.upsert_sales_daily(rows, target_date)
        monitor.record_success(step, started, len(rows))
        summary["steps"][step] = {"rows": len(rows), "status": "ok"}
    except Exception as exc:
        monitor.record_failure(step, started, exc)
        summary["steps"][step] = {"status": "failed", "error": str(exc)}

    # Reservations (予約管理一覧)
    step = "csv_reservations"
    started = monitor.record_start(step)
    try:
        rows = []
        for blob in _load_blobs("zozo/reservations"):
            rows.extend(zozo_csv.parse_reservations(blob.download_as_bytes(), target_date))
        if rows:
            bq.upsert_reservations(rows, target_date)
        monitor.record_success(step, started, len(rows))
        summary["steps"][step] = {"rows": len(rows), "status": "ok"}
    except Exception as exc:
        monitor.record_failure(step, started, exc)
        summary["steps"][step] = {"status": "failed", "error": str(exc)}

    # Inventory SKU (倉庫在庫：SKU毎)
    step = "csv_inventory_sku"
    started = monitor.record_start(step)
    try:
        rows = []
        for blob in _load_blobs("zozo/inventory_sku"):
            rows.extend(zozo_csv.parse_inventory_sku(blob.download_as_bytes(), target_date))
        if rows:
            bq.upsert_inventory_snapshot(rows, target_date)
        monitor.record_success(step, started, len(rows))
        summary["steps"][step] = {"rows": len(rows), "status": "ok"}
    except Exception as exc:
        monitor.record_failure(step, started, exc)
        summary["steps"][step] = {"status": "failed", "error": str(exc)}

    # Stock analysis (在庫分析)
    step = "csv_stock_analysis"
    started = monitor.record_start(step)
    try:
        rows = []
        for blob in _load_blobs("zozo/stock_analysis"):
            rows.extend(zozo_csv.parse_inventory_analysis(blob.download_as_bytes(), target_date))
        if rows:
            bq.upsert_stock_analysis(rows, target_date)
        monitor.record_success(step, started, len(rows))
        summary["steps"][step] = {"rows": len(rows), "status": "ok"}
    except Exception as exc:
        monitor.record_failure(step, started, exc)
        summary["steps"][step] = {"status": "failed", "error": str(exc)}

    # Performance (商品別実績)
    step = "csv_performance"
    started = monitor.record_start(step)
    try:
        rows = []
        for blob in _load_blobs("zozo/performance"):
            rows.extend(zozo_csv.parse_performance(blob.download_as_bytes(), target_date))
        if rows:
            bq.upsert_sales_daily(rows, target_date)
        monitor.record_success(step, started, len(rows))
        summary["steps"][step] = {"rows": len(rows), "status": "ok"}
    except Exception as exc:
        monitor.record_failure(step, started, exc)
        summary["steps"][step] = {"status": "failed", "error": str(exc)}

    # Product master (goods_cs)
    step = "csv_product_master"
    started = monitor.record_start(step)
    try:
        rows = []
        for blob in _load_blobs("zozo/product_master"):
            rows.extend(zozo_csv.parse_product_master(blob.download_as_bytes()))
        if rows:
            bq.upsert_product_master(rows)
        monitor.record_success(step, started, len(rows))
        summary["steps"][step] = {"rows": len(rows), "status": "ok"}
    except Exception as exc:
        monitor.record_failure(step, started, exc)
        summary["steps"][step] = {"status": "failed", "error": str(exc)}

    # Search keyword (No.20) - Looker TSV (merged 7-shop per-run)
    step = "csv_search_keyword"
    started = monitor.record_start(step)
    try:
        rows = []
        for blob in _load_blobs("zozo/search_keyword"):
            if not blob.name.lower().endswith((".tsv", ".csv")):
                continue
            rows.extend(zozo_csv.parse_search_keyword(
                blob.download_as_bytes(), target_date))
        if rows:
            bq.upsert_search_keyword_daily(rows, target_date)
        monitor.record_success(step, started, len(rows))
        summary["steps"][step] = {"rows": len(rows), "status": "ok"}
    except Exception as exc:
        monitor.record_failure(step, started, exc)
        summary["steps"][step] = {"status": "failed", "error": str(exc)}

    # Access log (No.19) — dashboard CSV from 2 Looker tabs:
    #   ・access_log_app   = 「App(ショップ親カテゴリ)」    → device_type='App'
    #   ・access_log_pcsp  = 「PC/SP(ショップ親カテゴリ)」  → device_type='PC/SP'
    # 47列の wide CSV (per-shop × per-親カテゴリ × per-経路の PV/UU). Each row
    # represents one (date, shop, parent_category) combo. The 旧 `access_log`
    # folder (PV推移 tile経由 — 装置不明) is kept for backward compat as a 集計
    # rollup row.
    step = "csv_access_log"
    started = monitor.record_start(step)
    try:
        rows = []
        # Dashboard-DL (App / PC/SP) — wide CSV with 47 columns
        for sub, dev_hint in (("zozo/access_log_app",  "App"),
                              ("zozo/access_log_pcsp", "PC/SP")):
            for blob in _load_blobs(sub):
                if not blob.name.lower().endswith((".tsv", ".csv")):
                    continue
                rows.extend(zozo_csv.parse_access_log_dashboard(
                    blob.download_as_bytes(), target_date,
                    device_hint=dev_hint))
        # Legacy PV推移 (older format, kept for back-compat)
        for blob in _load_blobs("zozo/access_log"):
            if not blob.name.lower().endswith((".tsv", ".csv")):
                continue
            rows.extend(zozo_csv.parse_access_log(
                blob.download_as_bytes(), target_date))
        if rows:
            bq.upsert_access_log_daily(rows, target_date)
        monitor.record_success(step, started, len(rows))
        summary["steps"][step] = {"rows": len(rows), "status": "ok"}
    except Exception as exc:
        monitor.record_failure(step, started, exc)
        summary["steps"][step] = {"status": "failed", "error": str(exc)}

    # Product reviews (No.15) - UTF-8 BOM CSV from fetch_product_reviews.py
    step = "csv_product_reviews"
    started = monitor.record_start(step)
    try:
        rows = []
        for blob in _load_blobs("zozo/reviews"):
            if not blob.name.lower().endswith(".csv"):
                continue
            rows.extend(zozo_csv.parse_product_reviews(
                blob.download_as_bytes(), target_date))
        if rows:
            bq.upsert_product_reviews(rows, target_date)
        monitor.record_success(step, started, len(rows))
        summary["steps"][step] = {"rows": len(rows), "status": "ok"}
    except Exception as exc:
        monitor.record_failure(step, started, exc)
        summary["steps"][step] = {"status": "failed", "error": str(exc)}

    # ZOZOAD (Detail.csv) — per-fetch-date subfolders (ZOZO BO publishes ad
    # numbers with ~2-day lag, so fetch_zozoad_report.py uploads to a path
    # keyed by the actual fetch_date, not the run target_date). Scan all
    # subfolders under uploads/zozo/zozoad/ and ingest each independently.
    step = "csv_zozoad"
    started = monitor.record_start(step)
    try:
        prefix = f"{gcs_prefix.rstrip('/')}/zozo/zozoad/"
        all_blobs = list(bucket.list_blobs(prefix=prefix))
        per_date: dict[str, list] = {}
        for blob in all_blobs:
            parts = blob.name.split("/")
            if len(parts) < 5 or not blob.name.lower().endswith(".csv"):
                continue
            fetch_date = parts[-2]
            per_date.setdefault(fetch_date, []).append(blob)
        total_rows = 0
        per_date_summary = {}
        for fetch_date, blobs in sorted(per_date.items()):
            rows = []
            for blob in blobs:
                rows.extend(zozo_csv.parse_zozoad(
                    blob.download_as_bytes(), fetch_date))
            if rows:
                bq.upsert_zozoad_daily(rows, fetch_date)
            total_rows += len(rows)
            per_date_summary[fetch_date] = len(rows)
        monitor.record_success(step, started, total_rows)
        summary["steps"][step] = {
            "rows": total_rows, "status": "ok",
            "by_fetch_date": per_date_summary,
        }
    except Exception as exc:
        monitor.record_failure(step, started, exc)
        summary["steps"][step] = {"status": "failed", "error": str(exc)}

    # Sale settings (salegoods)
    step = "csv_sale_settings"
    started = monitor.record_start(step)
    try:
        rows = []
        for blob in _load_blobs("zozo/sale"):
            # captured_at = ダウンロード時刻 (GCS blob 作成時刻)。「常時タイムセール」で
            # 価格が変動するため、いつ時点の価格かを保持する (client 2026)。
            captured_at = blob.time_created.isoformat() if blob.time_created else None
            rows.extend(zozo_csv.parse_sale_settings(
                blob.download_as_bytes(), target_date, captured_at=captured_at))
        if rows:
            bq.upsert_sale_settings(rows, target_date)
        monitor.record_success(step, started, len(rows))
        summary["steps"][step] = {"rows": len(rows), "status": "ok"}
    except Exception as exc:
        monitor.record_failure(step, started, exc)
        summary["steps"][step] = {"status": "failed", "error": str(exc)}

    # Coupon exclusion (per-brand, per-event-date files).
    #
    # クーポン除外 CSVs are uploaded under the クーポン EVENT date (future-
    # dated), not under the run target_date — the daily scraper at run_daily
    # [1e] sweeps all upcoming events visible on the EventCalendar. So this
    # step scans every `uploads/zozo/coupon/{YYYY-MM-DD}/` folder available
    # and ingests each event date independently, keyed by the path's date.
    step = "csv_coupon_exclusion"
    started = monitor.record_start(step)
    try:
        prefix = f"{gcs_prefix.rstrip('/')}/zozo/coupon/"
        # delimiter='/' returns just the immediate subfolders.
        all_blobs = list(bucket.list_blobs(prefix=prefix))
        per_date: dict[str, list] = {}
        for blob in all_blobs:
            # Path layout: uploads/zozo/coupon/{YYYY-MM-DD}/{brand}_yyyymmdd.csv
            parts = blob.name.split("/")
            if len(parts) < 5 or not blob.name.lower().endswith(".csv"):
                continue
            event_date = parts[-2]  # YYYY-MM-DD folder
            per_date.setdefault(event_date, []).append(blob)

        total_rows = 0
        per_date_summary = {}
        for event_date, blobs in sorted(per_date.items()):
            rows = []
            for blob in blobs:
                filename = blob.name.split("/")[-1]
                brand = ZOZOCsvExtractor.extract_brand_from_filename(filename)
                rows.extend(
                    zozo_csv.parse_coupon_exclusion(
                        blob.download_as_bytes(),
                        event_date,
                        brand_name=brand,
                    )
                )
            if rows:
                bq.upsert_coupon_exclusion(rows, event_date)
            total_rows += len(rows)
            per_date_summary[event_date] = len(rows)
        monitor.record_success(step, started, total_rows)
        summary["steps"][step] = {
            "rows": total_rows, "status": "ok",
            "by_event_date": per_date_summary,
        }
    except Exception as exc:
        monitor.record_failure(step, started, exc)
        summary["steps"][step] = {"status": "failed", "error": str(exc)}

    # MMS cost master (原価)
    step = "csv_mms_cost"
    started = monitor.record_start(step)
    try:
        rows = []
        for blob in _load_blobs("mms/cost"):
            rows.extend(mms_csv.parse_cost_master(blob.download_as_bytes(), target_date))
        if rows:
            bq.upsert_cost_master(rows)
        monitor.record_success(step, started, len(rows))
        summary["steps"][step] = {"rows": len(rows), "status": "ok"}
    except Exception as exc:
        monitor.record_failure(step, started, exc)
        summary["steps"][step] = {"status": "failed", "error": str(exc)}

    # MMS incoming stock (着荷データ)
    step = "csv_mms_incoming"
    started = monitor.record_start(step)
    try:
        rows = []
        for blob in _load_blobs("mms/incoming"):
            rows.extend(mms_csv.parse_incoming_stock(blob.download_as_bytes(), target_date))
        if rows:
            bq.upsert_incoming_stock(rows, target_date)
        monitor.record_success(step, started, len(rows))
        summary["steps"][step] = {"rows": len(rows), "status": "ok"}
    except Exception as exc:
        monitor.record_failure(step, started, exc)
        summary["steps"][step] = {"status": "failed", "error": str(exc)}

    # PF手数料 (Google Sheet — per-product 下代 + 手数料率)
    # Primary cost source for the order mart (falls back to MMS).
    step = "csv_pf_fee"
    started = monitor.record_start(step)
    try:
        rows = []
        for blob in bucket.list_blobs(
                prefix=f"{gcs_prefix.rstrip('/')}/sheets/pf_fee/"):
            if not blob.name.lower().endswith(".csv"):
                continue
            # Path: uploads/sheets/pf_fee/{YYYY-MM-DD}/pf_fee.csv —
            # ingest only the LATEST snapshot we have.
            pass
        # Use the latest snapshot folder
        all_pf_blobs = list(bucket.list_blobs(
            prefix=f"{gcs_prefix.rstrip('/')}/sheets/pf_fee/"))
        if all_pf_blobs:
            # Pick the latest folder (sorted by name = date)
            latest_date = max(
                blob.name.split("/")[-2] for blob in all_pf_blobs
                if "/sheets/pf_fee/" in blob.name and blob.name.endswith(".csv"))
            for blob in all_pf_blobs:
                parts = blob.name.split("/")
                if (len(parts) >= 5 and parts[-2] == latest_date
                        and blob.name.endswith(".csv")):
                    rows.extend(zozo_csv.parse_pf_fee(
                        blob.download_as_bytes(), latest_date))
            if rows:
                bq.upsert_pf_fee_master(rows, latest_date)
        monitor.record_success(step, started, len(rows))
        summary["steps"][step] = {"rows": len(rows), "status": "ok"}
    except Exception as exc:
        monitor.record_failure(step, started, exc)
        summary["steps"][step] = {"status": "failed", "error": str(exc)}

    # Tableau 発注明細 (incoming stock from POs)
    step = "csv_tableau_hacchu"
    started = monitor.record_start(step)
    try:
        rows = []
        for blob in _load_blobs("tableau/hacchu"):
            rows.extend(tableau_csv.parse_hacchu_meisai(blob.download_as_bytes(), target_date))
        if rows:
            bq.upsert_incoming_stock(rows, target_date)
        monitor.record_success(step, started, len(rows))
        summary["steps"][step] = {"rows": len(rows), "status": "ok"}
    except Exception as exc:
        monitor.record_failure(step, started, exc)
        summary["steps"][step] = {"status": "failed", "error": str(exc)}

    # Tableau 予約管理 (incoming stock from production reservations)
    step = "csv_tableau_yoyaku"
    started = monitor.record_start(step)
    try:
        rows = []
        for blob in _load_blobs("tableau/yoyaku"):
            rows.extend(tableau_csv.parse_yoyaku_kanri(blob.download_as_bytes(), target_date))
        if rows:
            bq.upsert_incoming_stock(rows, target_date)
        monitor.record_success(step, started, len(rows))
        summary["steps"][step] = {"rows": len(rows), "status": "ok"}
    except Exception as exc:
        monitor.record_failure(step, started, exc)
        summary["steps"][step] = {"status": "failed", "error": str(exc)}

    # sitateru アイテムリスト (No.12 product metadata)
    step = "csv_sitateru_itemlist"
    started = monitor.record_start(step)
    try:
        rows = []
        for blob in _load_blobs("sitateru/itemlist"):
            rows.extend(sitateru_csv.parse_item_list(blob.download_as_bytes(), target_date))
        if rows:
            bq.upsert_sitateru_item_master(rows, target_date)
        monitor.record_success(step, started, len(rows))
        summary["steps"][step] = {"rows": len(rows), "status": "ok"}
    except Exception as exc:
        monitor.record_failure(step, started, exc)
        summary["steps"][step] = {"status": "failed", "error": str(exc)}

    # Rebuild KPI mart (non-blocking — SQL needs schema realignment)
    step = "rebuild_kpi_mart"
    started = monitor.record_start(step)
    try:
        run_mart_refresh(bq, target_date)
        monitor.record_success(step, started, 0)
        summary["steps"][step] = {"status": "ok"}
    except Exception as exc:
        monitor.record_failure(step, started, exc)
        summary["steps"][step] = {"status": "failed", "error": str(exc)}
        logger.warning("KPI mart step failed (non-blocking): %s", exc)

    logger.info("CSV ingestion complete: %s", json.dumps(summary, ensure_ascii=False))
    return summary


# ------------------------------------------------------------------
# HTTP server mode (Cloud Run Job uses HTTP trigger)
# ------------------------------------------------------------------

@app.route("/run", methods=["POST"])
def trigger_pipeline():
    body = request.get_json(silent=True) or {}
    target_date = body.get("date") or _yesterday_jst()
    try:
        summary = run_pipeline(target_date)
        return jsonify({"status": "ok", "summary": summary}), 200
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500


@app.route("/ingest-csv", methods=["POST"])
def trigger_csv_ingestion():
    """HTTP trigger for CSV ingestion (called after GCS upload via Cloud Functions or manually)."""
    body = request.get_json(silent=True) or {}
    target_date = body.get("date") or _yesterday_jst()
    prefix = body.get("prefix") or "uploads"
    try:
        summary = run_csv_ingestion(prefix, target_date)
        return jsonify({"status": "ok", "summary": summary}), 200
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


def _yesterday_jst() -> str:
    return (datetime.now(JST) - timedelta(days=1)).strftime("%Y-%m-%d")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None)
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--csv-ingest", action="store_true",
                        help="Process manually uploaded ZOZOBO/MMS CSV files from GCS")
    parser.add_argument("--csv-prefix", default="uploads",
                        help="GCS folder prefix for uploaded CSV files (default: uploads)")
    args = parser.parse_args()

    if args.serve:
        port = int(os.environ.get("PORT", 8080))
        app.run(host="0.0.0.0", port=port)
    elif args.csv_ingest:
        target = args.date or _yesterday_jst()
        prefix = args.csv_prefix or "uploads"
        run_csv_ingestion(prefix, target)
    else:
        target = args.date or _yesterday_jst()
        run_pipeline(target)
