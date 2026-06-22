"""
Central configuration. All values come from environment variables.
Never hardcode credentials or project IDs here.

Source-of-truth defaults reflect the current MONO-MART production environment.
Loads .env automatically if present (for local dev).
"""
import os
from pathlib import Path
from zoneinfo import ZoneInfo

# Auto-load .env from this file's directory (no python-dotenv dependency required)
_env_file = Path(__file__).resolve().parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _k, _v = _line.split("=", 1)
        # Don't override env vars already set (Cloud Run env vars take precedence)
        os.environ.setdefault(_k.strip(), _v.strip())

JST = ZoneInfo("Asia/Tokyo")

# ── GCP ──────────────────────────────────────────────────────────────────────
GCP_PROJECT_ID     = os.environ.get("GCP_PROJECT_ID", "mono-back-office-system")
GCS_RAW_BUCKET     = os.environ.get("GCS_RAW_BUCKET",     f"{GCP_PROJECT_ID}-raw-data")
GCS_INPUTS_BUCKET  = os.environ.get("GCS_INPUTS_BUCKET",  f"{GCP_PROJECT_ID}-inputs")
GCS_EXPORTS_BUCKET = os.environ.get("GCS_EXPORTS_BUCKET", f"{GCP_PROJECT_ID}-exports")

# Google client libraries (storage, bigquery, etc.) auto-detect the project from
# GOOGLE_CLOUD_PROJECT — bridge from our GCP_PROJECT_ID so callers don't have to
# pass project=... explicitly to every Client() call.
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", GCP_PROJECT_ID)

# BigQuery datasets
BQ_DATASET_RAW        = os.environ.get("BQ_DATASET_RAW",        "raw_layer")
BQ_DATASET_ANALYTICS  = os.environ.get("BQ_DATASET_ANALYTICS",  "analytics_layer")
BQ_DATASET_MART       = os.environ.get("BQ_DATASET_MART",       "mart_layer")
BQ_DATASET_MONITORING = os.environ.get("BQ_DATASET_MONITORING", "monitoring")
BQ_LOCATION           = os.environ.get("BQ_LOCATION",           "asia-northeast1")

# ── Business logic ────────────────────────────────────────────────────────────
TARGET_COVERAGE_WEEKS  = int(os.environ.get("TARGET_COVERAGE_WEEKS", "8"))
TREND_COEFF_MIN        = float(os.environ.get("TREND_COEFF_MIN", "0.5"))
TREND_COEFF_MAX        = float(os.environ.get("TREND_COEFF_MAX", "2.0"))
CRITICAL_STOCK_DAYS    = int(os.environ.get("CRITICAL_STOCK_DAYS", "0"))   # stockout
WARNING_STOCK_DAYS     = int(os.environ.get("WARNING_STOCK_DAYS",  "14"))  # < 2 weeks
OVERSTOCK_STOCK_DAYS   = int(os.environ.get("OVERSTOCK_STOCK_DAYS","90"))  # > 3 months

# ── External alerts ──────────────────────────────────────────────────────────
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")

# ── Google Sheets — 予約管理表 (Reservation Management) ─────────────────────
# Default reflects the URL provided by the client on 2026-05-08:
# https://docs.google.com/spreadsheets/d/1x8frf-cK8nrC6JYB2gZs9emjat0prNpH5x6Zqqb55jg/edit
SHEETS_SPREADSHEET_ID  = os.environ.get(
    "SHEETS_SPREADSHEET_ID",
    "1x8frf-cK8nrC6JYB2gZs9emjat0prNpH5x6Zqqb55jg",
)
SHEETS_RESERVATION_TAB = os.environ.get("SHEETS_RESERVATION_TAB", "予約確認")

# ── Google Sheets — PF手数料表 (Platform Fee Table) ─────────────────────────
# Default reflects the URL provided by the client on 2026-05-08:
# https://docs.google.com/spreadsheets/d/1fsZMRgYeJfR3w7NbPXCtp3JWfyp4yBKKsXaKspUfNaE/edit
SHEETS_PF_FEE_SPREADSHEET_ID = os.environ.get(
    "SHEETS_PF_FEE_SPREADSHEET_ID",
    "1fsZMRgYeJfR3w7NbPXCtp3JWfyp4yBKKsXaKspUfNaE",
)
SHEETS_PF_FEE_TAB            = os.environ.get("SHEETS_PF_FEE_TAB", "PF品番一覧")

# ── ZOZO Partner API ─────────────────────────────────────────────────────────
ZOZO_API_BASE_URL = os.environ.get("ZOZO_API_BASE_URL", "https://api.partner.zozo.com/v1")
ZOZO_API_KEY      = os.environ.get("ZOZO_API_KEY", "")

# ── Manus integration ────────────────────────────────────────────────────────
MANUS_API_BASE_URL  = os.environ.get("MANUS_API_BASE_URL", "https://api.manus.space")
MANUS_API_KEY       = os.environ.get("MANUS_API_KEY", "")
MANUS_WORKSPACE_ID  = os.environ.get("MANUS_WORKSPACE_ID", "")
