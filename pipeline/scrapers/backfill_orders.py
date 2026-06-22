"""
Historical order/shipped data backfill from ZOZO Back Office.

⚠️  ZOZO BO UI CONSTRAINT
    "直近1年以内のデータが閲覧できます"
    The web UI only stores the most recent 1 year. As of June 2026 this means:
      - ACCESSIBLE   : July 2025 ~ June 2026  (download via this script)
      - NOT ACCESSIBLE: July 2024 ~ June 2025 (request bulk export from ZOZO
                        partner support, then use --only-ingest to load)

Two operating modes
-------------------
1. SCRAPE + INGEST (default)
   Logs into ZOZO BO, downloads one CSV per month for the given date range,
   uploads each to GCS, then calls main.py --csv-ingest for each month.
   Only works for dates within the last 1 year.

   python backfill_orders.py --start-date 2025-07-01 --end-date 2026-06-15

2. INGEST ONLY  (--only-ingest)
   Skips scraping. Expects CSVs already uploaded to GCS under
     gs://{bucket}/uploads/zozo/orders/{YYYY-MM-DD}/
     gs://{bucket}/uploads/zozo/shipped/{YYYY-MM-DD}/
   Runs ETL ingest for each month in the range.
   Use this after ZOZO support provides the pre-2025 export.

   python backfill_orders.py --start-date 2024-07-01 --end-date 2025-06-30 --only-ingest

ENV vars (same as zozo_scraper.py):
  ZOZO_BASIC_USER, ZOZO_BASIC_PASSWORD, ZOZO_LOGIN_ID, ZOZO_LOGIN_PASSWORD
  GCS_RAW_BUCKET, GCP_PROJECT_ID
  GOOGLE_APPLICATION_CREDENTIALS
"""
from __future__ import annotations

import argparse
import calendar
import logging
import os
import subprocess
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("backfill_orders")

# ── Path helpers ──────────────────────────────────────────────────────────────

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PIPELINE  = _REPO_ROOT / "pipeline"
_MAIN_PY   = _PIPELINE / "main.py"

# ── Import the scraper's session/auth machinery ───────────────────────────────
sys.path.insert(0, str(_PIPELINE))
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from playwright.sync_api import sync_playwright, BrowserContext, Page
    _HAS_PLAYWRIGHT = True
except ImportError:
    _HAS_PLAYWRIGHT = False

try:
    from google.cloud import storage as gcs_storage
    _HAS_GCS = True
except ImportError:
    _HAS_GCS = False

# ── Date utilities ────────────────────────────────────────────────────────────

def _months_in_range(start: date, end: date) -> list[tuple[date, date]]:
    """Return list of (month_start, month_end) pairs covering [start, end]."""
    months: list[tuple[date, date]] = []
    cur = date(start.year, start.month, 1)
    while cur <= end:
        last_day = calendar.monthrange(cur.year, cur.month)[1]
        m_end = min(date(cur.year, cur.month, last_day), end)
        m_start = max(cur, start)
        months.append((m_start, m_end))
        # advance to first of next month
        if cur.month == 12:
            cur = date(cur.year + 1, 1, 1)
        else:
            cur = date(cur.year, cur.month + 1, 1)
    return months


def _zozo_date(d: date) -> str:
    """ZOZO BO date format used in POST body: YYYY%2FMM%2FDD"""
    return d.strftime("%Y%%2F%m%%2F%d")


def _accessible_via_ui(target: date) -> bool:
    """True if target date is within ZOZO BO's 1-year rolling window."""
    cutoff = date.today() - timedelta(days=365)
    return target >= cutoff


# ── GCS upload ────────────────────────────────────────────────────────────────

def _upload_to_gcs(
    data: bytes,
    bucket_name: str,
    gcs_prefix: str,        # e.g. "zozo/orders"
    month_start: date,
    filename: str,
    project_id: str,
) -> str:
    """Upload CSV bytes to GCS. Returns gs:// URI."""
    if not _HAS_GCS:
        raise RuntimeError("google-cloud-storage not installed")
    client = gcs_storage.Client(project=project_id)
    bucket = client.bucket(bucket_name)
    folder = month_start.strftime("%Y-%m-%d")
    blob_name = f"uploads/{gcs_prefix}/{folder}/{filename}"
    blob = bucket.blob(blob_name)
    blob.upload_from_string(data, content_type="text/csv")
    uri = f"gs://{bucket_name}/{blob_name}"
    logger.info("Uploaded %d bytes → %s", len(data), uri)
    return uri


# ── Scraping (Playwright) ─────────────────────────────────────────────────────

_DLB = "%83_%83E%83%93%83%8D%81%5B%83h"
BASE_URL  = "https://to.zozo.jp/to/"
LOGIN_URL = "https://to.zozo.jp/to/"

_ORDER_POST_TEMPLATE = (
    "c=Download&ShopID=-1&SCategoryPID=0&SCategoryID=0"
    "&ost=order&TermFrom={FROM}&TermTo={TO}&MallCheck=0"
    f"&DL_BUTTON={_DLB}"
)
_SHIPPED_POST_TEMPLATE = (
    "c=Download&ShopID=-1&SCategoryPID=0&SCategoryID=0"
    "&ost=send&TermFrom={FROM}&TermTo={TO}&MallCheck=0"
    f"&DL_BUTTON={_DLB}"
)


def _do_login(page: Page) -> None:
    """2-stage ZOZO BO login (HTTP Basic → form login)."""
    basic_user = os.environ.get("ZOZO_BASIC_USER", "")
    basic_pass = os.environ.get("ZOZO_BASIC_PASSWORD", "")
    login_id   = os.environ.get("ZOZO_LOGIN_ID", "")
    login_pass = os.environ.get("ZOZO_LOGIN_PASSWORD", "")

    # Stage 1: HTTP Basic Auth embedded in URL
    auth_url = LOGIN_URL.replace("https://", f"https://{basic_user}:{basic_pass}@")
    page.goto(auth_url, timeout=30_000, wait_until="domcontentloaded")
    time.sleep(2)

    # Stage 2: Form login
    if page.locator('input[name="login_id"], input[name="ID"]').count() > 0:
        for sel in ('input[name="login_id"]', 'input[name="ID"]', 'input[type="text"]'):
            if page.locator(sel).count() > 0:
                page.fill(sel, login_id)
                break
        for sel in ('input[name="password"]', 'input[name="PASS"]', 'input[type="password"]'):
            if page.locator(sel).count() > 0:
                page.fill(sel, login_pass)
                break
        for sel in ('button[type="submit"]', 'input[type="submit"]', 'button:has-text("ログイン")'):
            if page.locator(sel).count() > 0:
                page.click(sel)
                break
        time.sleep(3)
    logger.info("Login complete")


def _fetch_monthly_csv(
    page: Page,
    source: str,   # "orders" or "shipped"
    month_start: date,
    month_end: date,
) -> Optional[bytes]:
    """POST to ZOZO BO and capture the downloaded CSV bytes."""
    from_enc = _zozo_date(month_start)
    to_enc   = _zozo_date(month_end)

    if source == "orders":
        body = _ORDER_POST_TEMPLATE.format(FROM=from_enc, TO=to_enc)
    else:
        body = _SHIPPED_POST_TEMPLATE.format(FROM=from_enc, TO=to_enc)

    post_url = f"{BASE_URL}order_csv.asp"

    # Use CDP network interception to capture the response bytes
    import tempfile, uuid
    dl_path = Path(tempfile.gettempdir()) / f"backfill_{uuid.uuid4().hex}.csv"

    # Set download dir and issue the POST
    page.context.set_default_timeout(120_000)
    with page.expect_download() as dl_info:
        page.evaluate(
            """([url, body]) => {
                const form = document.createElement('form');
                form.method = 'POST';
                form.action = url;
                const inp = document.createElement('input');
                inp.type = 'hidden';
                inp.name = '__raw_body__';
                // We'll use fetch instead for more control
                form.appendChild(inp);
                document.body.appendChild(form);
            }""",
            [post_url, body],
        )
        # Use fetch API via evaluate to trigger POST and blob download
        page.evaluate(
            """async ([url, body]) => {
                const resp = await fetch(url, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                    body: body,
                    credentials: 'include',
                });
                const blob = await resp.blob();
                const a = document.createElement('a');
                a.href = URL.createObjectURL(blob);
                a.download = 'download.csv';
                document.body.appendChild(a);
                a.click();
            }""",
            [post_url, body],
        )
        download = dl_info.value
    download.save_as(str(dl_path))
    data = dl_path.read_bytes()
    dl_path.unlink(missing_ok=True)
    logger.info("Downloaded %s for %s ~ %s: %d bytes", source, month_start, month_end, len(data))
    return data


# ── ETL ingest via subprocess ─────────────────────────────────────────────────

def _run_etl(month_start: date, dry_run: bool) -> int:
    """Run main.py --csv-ingest for the given month (keyed by month_start)."""
    date_str = month_start.strftime("%Y-%m-%d")
    cmd = [sys.executable, str(_MAIN_PY), "--csv-ingest", "--date", date_str]
    logger.info("ETL ingest: %s", " ".join(cmd))
    if dry_run:
        logger.info("[dry-run] skipping ETL")
        return 0
    result = subprocess.run(cmd, cwd=str(_PIPELINE))
    return result.returncode


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill historical ZOZO order data")
    parser.add_argument("--start-date", required=True,
                        help="Start of date range (YYYY-MM-DD). Min: 2024-07-01")
    parser.add_argument("--end-date",   required=True,
                        help="End of date range   (YYYY-MM-DD). Max: today")
    parser.add_argument("--only-ingest", action="store_true",
                        help="Skip scraping; only run ETL on already-uploaded GCS files")
    parser.add_argument("--dry-run", action="store_true",
                        help="Plan only — no scraping, no GCS uploads, no ETL")
    parser.add_argument("--sources", default="orders,shipped",
                        help="Comma-separated sources to download: orders,shipped")
    parser.add_argument("--skip-ingest", action="store_true",
                        help="Scrape + upload to GCS only; skip the BigQuery ETL phase "
                             "(全期間まとめて後で取り込む運用向け)")
    args = parser.parse_args()

    start = date.fromisoformat(args.start_date)
    end   = date.fromisoformat(args.end_date)
    sources = [s.strip() for s in args.sources.split(",")]

    months = _months_in_range(start, end)
    logger.info("Backfill plan: %d months from %s to %s", len(months), start, end)

    bucket_name = os.environ.get("GCS_RAW_BUCKET",
                                 "mono-back-office-system-raw-data")
    project_id  = os.environ.get("GCP_PROJECT_ID",
                                 "mono-back-office-system")

    # Warn about inaccessible months
    inaccessible = [(s, e) for s, e in months if not _accessible_via_ui(s)]
    if inaccessible and not args.only_ingest:
        logger.warning(
            "⚠️  %d month(s) are OLDER THAN 1 YEAR and cannot be downloaded "
            "via the ZOZO BO web UI:\n%s\n"
            "For these months, request a bulk CSV export from ZOZO partner "
            "support, upload the files to GCS manually under:\n"
            "  gs://%s/uploads/zozo/orders/YYYY-MM-DD/filename.csv\n"
            "Then re-run with --only-ingest to ingest them.",
            len(inaccessible),
            "\n".join(f"  {s} ~ {e}" for s, e in inaccessible),
            bucket_name,
        )

    accessible = [(s, e) for s, e in months if _accessible_via_ui(s)]

    results: list[dict] = []

    # ── Scraping phase (skip if --only-ingest) ────────────────────────────────
    if not args.only_ingest and accessible and not args.dry_run:
        if not _HAS_PLAYWRIGHT:
            logger.error("playwright not installed. Run: pip install playwright && playwright install chromium")
            sys.exit(1)

        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=(os.environ.get("HEADLESS", "1") == "1"),
                args=["--disable-blink-features=AutomationControlled",
                      "--no-sandbox"],
            )
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                accept_downloads=True,
            )
            page = context.new_page()
            _do_login(page)

            for m_start, m_end in accessible:
                for src in sources:
                    try:
                        data = _fetch_monthly_csv(page, src, m_start, m_end)
                        if data:
                            filename = f"{m_start.strftime('%Y_%m_%d')}_{src}.csv"
                            gcs_prefix = f"zozo/{src}s"  # orders → zozo/orders
                            uri = _upload_to_gcs(
                                data, bucket_name, f"zozo/{src}",
                                m_start, filename, project_id,
                            )
                            results.append({
                                "month": str(m_start),
                                "source": src,
                                "status": "uploaded",
                                "gcs": uri,
                                "bytes": len(data),
                            })
                    except Exception as exc:
                        logger.error("Failed %s %s~%s: %s", src, m_start, m_end, exc)
                        results.append({
                            "month": str(m_start),
                            "source": src,
                            "status": "failed",
                            "error": str(exc),
                        })
                    time.sleep(3)  # polite pause

            browser.close()

    elif not args.only_ingest and accessible and args.dry_run:
        for m_start, m_end in accessible:
            logger.info("[dry-run] would download %s sources for %s ~ %s",
                        sources, m_start, m_end)

    # ── ETL ingest phase ──────────────────────────────────────────────────────
    if args.skip_ingest:
        logger.info("── ETL ingest フェーズをスキップ (--skip-ingest) ──")
        months = []
    else:
        logger.info("── ETL ingest phase ──────────────────────────────────────")
    for m_start, m_end in months:
        rc = _run_etl(m_start, args.dry_run)
        results.append({
            "month": str(m_start),
            "source": "etl",
            "status": "ok" if rc == 0 else f"exit={rc}",
        })
        if rc != 0:
            logger.warning("ETL returned %d for %s — continuing", rc, m_start)
        time.sleep(2)

    # ── Summary ───────────────────────────────────────────────────────────────
    logger.info("══ BACKFILL SUMMARY ══════════════════════════════════════")
    for r in results:
        logger.info("  %s  %-10s  %s%s",
                    r["month"], r["source"], r["status"],
                    f"  ({r.get('bytes', '')} bytes)" if r.get("bytes") else "")

    failed = [r for r in results if "fail" in r.get("status", "")]
    if failed:
        logger.warning("%d step(s) failed — review logs above", len(failed))
        sys.exit(1)
    logger.info("Backfill complete.")


if __name__ == "__main__":
    main()
