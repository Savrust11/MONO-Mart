# -*- coding: utf-8 -*-
"""
fetch_sitateru.py -- Sitateru Cloud item list auto-download.

Flow per search query:
  1. Navigate to /sewing/brand/productions?keyword=<query>
  2. Read result count from div.total  ("表示中 X - Y 件 / 全 N 件")
  3. If 0: skip.  If 1-2000: trigger export.  If >2000: expand query.
  4. Export: 一括処理 → 相談アイテムの一括登録・変更 → 登録・更新用CSVのエクスポート
  5. Email sent to IMAP_USER; poll inbox for Sitateru email with download URL.
  6. Download CSV via browser session.  Save to temp dir.
  7. After all queries: merge CSVs (dedup by アイテムID), upload to GCS, run ETL.

Search strategy (spec sheet: search-items-proposal):
  Layer 1 (24 queries): division x season x status
  Layer 2 (>2000 hits): + display_flag
  Layer 3 (>2000 hits): + order_type

Season switching (dynamic):
  month >= 10: current-year AW start  (e.g. 26AW, 27SS, 27AW, 28SS)
  month >=  3: current-year SS start  (e.g. 26SS, 26AW, 27SS, 27AW)
  month <   3: prev-year    AW start  (e.g. 25AW, 26SS, 26AW, 27SS)

Required env vars:
  IMAP_HOST      default: imap.gmail.com
  IMAP_USER      yujin-yamaguchi@mono-mart.jp
  IMAP_PASS      Gmail app-password (or IMAP password)
  GCS_RAW_BUCKET default: mono-back-office-system-raw-data
  GCP_PROJECT_ID default: mono-back-office-system

Optional:
  SITATERU_USER / SITATERU_PASS  (only needed if session state expired)
  HEADLESS  0 = show browser  (default 1)

Output:
  GCS: gs://{bucket}/uploads/sitateru/itemlist/{date}/item_list_{yyyymmdd}.csv
  BQ:  analytics_layer.sitateru_item_master (via main.py --csv-ingest)

Usage:
  python fetch_sitateru.py                    # yesterday JST
  python fetch_sitateru.py --date 2026-06-15  # specific date
  python fetch_sitateru.py --dry-run          # plan only, no browser
"""
from __future__ import annotations

import argparse
import csv
import email as email_lib
import email.policy
import email.utils
import imaplib
import io
import json
import logging
import os
import re
import subprocess
import sys
import time
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("fetch_sitateru")

_HERE     = Path(__file__).resolve().parent
_PIPELINE = _HERE.parent
_MAIN_PY  = _PIPELINE / "main.py"
_SESS_DIR = _HERE / "sessions"
_STATE    = _SESS_DIR / "sitateru_state.json"

JST = timezone(timedelta(hours=9))

# ---------------------------------------------------------------------------
# Sitateru URL
# ---------------------------------------------------------------------------
BASE_URL  = "https://direct.sitateru.com"
ITEMS_URL = f"{BASE_URL}/sewing/brand/productions"

def _search_url(keyword: str) -> str:
    kw = urllib.parse.quote(keyword)
    return f"{ITEMS_URL}?keyword={kw}&sort_priority=updated_at&sort_desc=desc&archive_mode=&button="

# ---------------------------------------------------------------------------
# Search constants  (spec sheet: search-items-proposal)
# ---------------------------------------------------------------------------

DIVISIONS = [
    "プロダクト1部",
    "プロダクト2部",
]

STATUSES = [
    "進行中",
    "仮発注済",
    "本発注済",
]

FLAGS = [
    "企画進行用/納品用",
    "企画進行用",
    "納品用",
    "生機",
    "見積用",
]

ORDER_TYPES = [
    "新品番",
    "新色",
    "リピート",
    "新サイズ",
    "新色/新サイズ",
    "新色＆リピート",
    "新サイズ＆リピート",
    "移管新規",
    "その他（生機/バックオーダー）",
]

RESULT_CAP = 2000


# ---------------------------------------------------------------------------
# Season calculation
# ---------------------------------------------------------------------------

def get_active_seasons(today: Optional[date] = None) -> list[str]:
    """Return 4 active seasons as ["yy/SS", "yy/AW", ...] strings."""
    if today is None:
        today = datetime.now(JST).date()
    m, y = today.month, today.year

    if m >= 10:
        start_y, start_s = y, "AW"
    elif m >= 3:
        start_y, start_s = y, "SS"
    else:
        start_y, start_s = y - 1, "AW"

    seasons: list[str] = []
    cy, cs = start_y, start_s
    for _ in range(4):
        seasons.append(f"{str(cy)[-2:]}/{cs}")
        if cs == "SS":
            cs = "AW"
        else:
            cs = "SS"
            cy += 1
    return seasons


# ---------------------------------------------------------------------------
# Playwright helpers
# ---------------------------------------------------------------------------

def _get_account_email(page) -> Optional[str]:
    """Navigate to Sitateru account settings and read the logged-in email address."""
    try:
        page.goto(f"{BASE_URL}/s/account/user", timeout=20_000, wait_until="domcontentloaded")
        time.sleep(2)
        # Try input[type=email] first
        for sel in [
            "input[type='email']",
            "input[name='email']",
            "#email",
        ]:
            try:
                val = page.locator(sel).first.input_value(timeout=3_000)
                if val and "@" in val:
                    return val.strip()
            except Exception:
                pass
        # Try any text node containing @
        try:
            text = page.locator("body").inner_text()
            m = re.search(r"[\w.+\-]+@[\w.\-]+\.\w+", text)
            if m:
                return m.group(0)
        except Exception:
            pass
    except Exception:
        pass
    return None


def _shot(page, tag: str) -> None:
    try:
        page.screenshot(path=str(_SESS_DIR / f"sitateru_fetch_{tag}.png"))
    except Exception:
        pass


def _is_logged_in(page) -> bool:
    url = page.url.lower()
    return (
        "direct.sitateru.com" in url
        and "login" not in url
        and "oauth" not in url
        and "atelier" not in url
    )


def _login(page, user: str, pw: str) -> bool:
    """Full browser login for Sitateru."""
    logger.info("Logging in to Sitateru...")

    page.goto(f"{BASE_URL}/", timeout=30_000, wait_until="domcontentloaded")
    time.sleep(3)
    _shot(page, "login_01_landing")

    for sel in [
        "input[type='submit']",
        "button:has-text('ログイン')",
        "a:has-text('ログイン')",
    ]:
        try:
            loc = page.locator(sel).first
            if loc.count() > 0 and loc.is_visible(timeout=3_000):
                loc.click(timeout=8_000)
                try:
                    page.wait_for_url("**/my_id/login**", timeout=15_000)
                except Exception:
                    pass
                page.wait_for_load_state("domcontentloaded", timeout=15_000)
                time.sleep(3)
                break
        except Exception:
            continue

    email_sels = [
        "input[type='email']", "input[placeholder*='メール']",
        "input[name='email']", "#email", "form input:first-of-type",
    ]
    email_ok = False
    for sel in email_sels:
        try:
            loc = page.locator(sel).first
            if loc.count() > 0 and loc.is_visible(timeout=5_000):
                loc.triple_click(timeout=5_000)
                loc.fill(user, timeout=10_000)
                email_ok = True
                break
        except Exception:
            continue

    if not email_ok:
        _shot(page, "login_err_email")
        return False

    for sel in ["input[type='password']", "input[name='password']", "#password"]:
        try:
            loc = page.locator(sel).first
            if loc.count() > 0:
                loc.fill(pw, timeout=10_000)
                break
        except Exception:
            continue

    for sel in ["input[name='commit']", "button[type='submit']", "input[type='submit']"]:
        try:
            btn = page.locator(sel).first
            if btn.count() > 0:
                btn.click(timeout=10_000)
                break
        except Exception:
            continue
    else:
        page.keyboard.press("Enter")

    page.wait_for_load_state("domcontentloaded", timeout=20_000)
    time.sleep(5)
    _shot(page, "login_02_after")
    ok = _is_logged_in(page)
    if ok:
        logger.info("Login successful")
        try:
            page.context.storage_state(path=str(_STATE))
        except Exception as exc:
            logger.warning("Session save failed: %s", exc)
    else:
        logger.error("Login failed: %s", page.url)
    return ok


def _get_count(page) -> Optional[int]:
    """Read result count from div.total → '全 N 件'."""
    try:
        text = page.locator(".total").first.inner_text()
        m = re.search(r"全\s*([\d,]+)\s*件", text)
        if m:
            return int(m.group(1).replace(",", ""))
    except Exception:
        pass
    return None


def _trigger_export(page, query: str) -> bool:
    """
    Navigate to search results for query, then trigger:
      一括処理 → 相談アイテムの一括登録・変更 → 登録・更新用CSVのエクスポート

    Handles both GET and POST (data-method) export links.
    Returns True if export was triggered.
    """
    logger.info("    Triggering export for: %r", query)

    # Navigate to filtered results
    page.goto(_search_url(query), timeout=30_000, wait_until="networkidle")
    time.sleep(3)

    # Scroll to top so menu-toggle is in view
    page.evaluate("window.scrollTo(0, 0)")
    time.sleep(1)

    # Open 一括処理 menu (div.menu-toggle)
    toggle = page.locator("div.menu-toggle").first
    if toggle.count() == 0:
        logger.warning("    一括処理 button not found")
        _shot(page, f"no_toggle_{query[:10]}")
        return False
    toggle.click(timeout=5_000)
    time.sleep(1)

    # Click 相談アイテムの一括登録・変更 (data-target="import")
    modal_link = page.locator("a[data-target='import']").first
    if modal_link.count() == 0:
        logger.warning("    相談アイテム modal link not found")
        page.keyboard.press("Escape")
        return False
    modal_link.click(timeout=5_000)
    time.sleep(2)

    # Find export link inside modal
    export_link = page.locator("a[href*='productions/export']").first
    if export_link.count() == 0:
        export_link = page.locator("a[href*='stock_keeping_units/export']").first
    if export_link.count() == 0:
        logger.warning("    Export link not found in modal")
        page.keyboard.press("Escape")
        _shot(page, f"no_export_{query[:10]}")
        return False

    # Read all relevant attributes before clicking
    href        = export_link.get_attribute("href") or ""
    data_method = (export_link.get_attribute("data-method") or "get").lower()
    data_confirm = export_link.get_attribute("data-confirm") or ""
    logger.info("    Export link : %s", href)
    logger.info("    data-method : %s  data-confirm: %r", data_method, data_confirm[:60])

    # Screenshot of the open modal so we can see its content
    _shot(page, f"modal_{query[:8]}")

    # Capture network requests during the export trigger
    captured: list[str] = []
    def _on_req(r):
        if "export" in r.url or "production" in r.url:
            captured.append(f"{r.method} {r.url[:120]}")
    page.on("request", _on_req)

    if data_method == "post":
        # Rails UJS would normally create a hidden form for data-method="post" links.
        # We replicate that here to guarantee the POST goes with the CSRF token.
        csrf = page.evaluate(
            "document.querySelector('meta[name=\"csrf-token\"]')?.content || ''"
        )
        abs_href = href if href.startswith("http") else f"{BASE_URL}{href}"
        logger.info("    Submitting POST with CSRF token to: %s", abs_href[:100])
        page.evaluate(
            """([url, token]) => {
                var f = document.createElement('form');
                f.method = 'POST';
                f.action = url;
                var t = document.createElement('input');
                t.type = 'hidden';
                t.name = 'authenticity_token';
                t.value = token;
                f.appendChild(t);
                document.body.appendChild(f);
                f.submit();
            }""",
            [abs_href, csrf],
        )
    else:
        # GET link — plain click (or dismiss data-confirm dialog automatically)
        if data_confirm:
            page.on("dialog", lambda d: d.accept())
        export_link.click(timeout=10_000)

    page.wait_for_load_state("networkidle", timeout=20_000)
    time.sleep(2)

    try:
        page.remove_listener("request", _on_req)
    except Exception:
        pass

    logger.info("    Network requests captured: %s", captured[:6])
    logger.info("    Page after export: %s", page.url[:100])

    # Read any flash / notice / alert on the resulting page
    for sel in [
        ".flash-message", ".notice", ".alert", ".alert-success",
        "[class*='flash']", "[class*='notice']", "[class*='alert']",
        "[class*='success']", "[class*='error']",
    ]:
        try:
            el = page.locator(sel).first
            if el.count() > 0 and el.is_visible(timeout=2_000):
                logger.info("    Flash [%s]: %r", sel, el.inner_text()[:120])
                break
        except Exception:
            pass

    _shot(page, f"after_export_{query[:8]}")
    return True


def _download_export_direct(page, query: str, tmp_dir: Path, label: str) -> tuple[Optional[Path], bool]:
    """
    Attempt to download the export CSV by navigating directly to the export URL,
    bypassing the modal.  This works whether the export is synchronous (returns
    a CSV attachment immediately) or asynchronous (server queues the job and
    redirects back to the list page — email will be sent later).

    Returns
    -------
    (Path, True)   – file was downloaded directly (fast path, no email needed)
    (None, True)   – export triggered asynchronously (page redirected to list); email pending
    (None, False)  – navigation failed unexpectedly; caller should fall back to modal click
    """
    kw = urllib.parse.quote(query)
    url = f"{BASE_URL}/sewing/brand/productions/export?keyword={kw}"
    logger.info("    Direct export URL: %s", url[:120])

    try:
        with page.expect_download(timeout=8_000) as dl_info:
            page.goto(url, wait_until="commit", timeout=20_000)
        dl = dl_info.value
        fname = dl.suggested_filename or f"{label}.csv"
        out = tmp_dir / f"{label}_direct_{fname}"
        dl.save_as(str(out))
        sz = out.stat().st_size
        if sz > 50:
            logger.info("    Direct download OK: %s  (%d bytes)", fname, sz)
            return out, True
        out.unlink(missing_ok=True)
        logger.info("    Direct download empty — treating as async")
        return None, True
    except Exception:
        pass

    # No download intercepted — check whether export was triggered (async redirect)
    cur_url = page.url
    if "/sewing/brand/productions" in cur_url and "/export" not in cur_url:
        # Redirected to list page — export was triggered (async), email pending
        logger.info("    Async export triggered (redirected to list page)")
        return None, True

    if "/export" in cur_url:
        # Page stayed at export URL — server returned a confirmation/processing page.
        # The export job WAS triggered but is asynchronous.
        # We fall back to modal click (proven mechanism) to ensure the trigger fires.
        logger.info(
            "    Export URL returned HTML (no redirect, no download). "
            "Falling back to modal click."
        )
        return None, False

    logger.warning("    Direct export: unexpected URL=%s", cur_url[:80])
    return None, False


# ---------------------------------------------------------------------------
# IMAP email polling
# ---------------------------------------------------------------------------

def _poll_email(
    imap_host: str,
    imap_user: str,
    imap_pass: str,
    after_dt: datetime,
    timeout: int = 600,
    interval: int = 30,
) -> Optional[str]:
    """
    Poll INBOX and Spam for a Sitateru export-completion email received after after_dt.
    Returns the first download URL found in the email body, or None.

    Skips:
      - Non-Sitateru senders
      - [新着] notification emails (item activity alerts, not export emails)
      - Item detail page URLs (/productions/<digits>...)
    """
    deadline = time.time() + timeout
    logger.info(
        "    Polling email (%s) for download URL (timeout %ds, interval %ds)...",
        imap_user, timeout, interval,
    )

    since_str = after_dt.strftime("%d-%b-%Y")
    # (mailbox, uid) pairs already processed in this call
    seen: set[tuple] = set()

    MAILBOXES = ["INBOX", "[Gmail]/Spam"]

    while time.time() < deadline:
        time.sleep(interval)
        try:
            with imaplib.IMAP4_SSL(imap_host, 993) as conn:
                conn.login(imap_user, imap_pass)

                for mailbox in MAILBOXES:
                    # Select readonly so we don't mark anything as read
                    try:
                        typ, _ = conn.select(mailbox, readonly=True)
                        if typ != "OK":
                            continue
                    except imaplib.IMAP4.error:
                        continue  # folder may not exist on non-Gmail

                    _, msg_ids = conn.search(None, f'SINCE "{since_str}"')
                    uids = msg_ids[0].split()
                    if not uids:
                        continue

                    for uid in reversed(uids):  # newest first
                        key = (mailbox, uid)
                        if key in seen:
                            continue

                        # Fetch headers only (PEEK = don't set \Seen flag)
                        _, hdata = conn.fetch(uid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
                        if not hdata or not hdata[0]:
                            seen.add(key)
                            continue
                        hdr = email_lib.message_from_bytes(
                            hdata[0][1], policy=email_lib.policy.default
                        )

                        from_addr = str(hdr.get("From", "")).lower()
                        subject   = str(hdr.get("Subject", ""))
                        date_hdr  = str(hdr.get("Date", ""))

                        # Must be from a Sitateru domain
                        if "sitateru" not in from_addr:
                            seen.add(key)
                            continue

                        # Date guard: must have arrived after we triggered the export
                        try:
                            msg_dt = email.utils.parsedate_to_datetime(date_hdr)
                            if msg_dt.timestamp() < after_dt.timestamp():
                                seen.add(key)
                                continue
                        except Exception:
                            pass

                        # Log every Sitateru email we find (helps diagnose missing export mail)
                        logger.info(
                            "    [%s] Sitateru email: %r (from=%s)",
                            mailbox, subject[:70], from_addr[:50],
                        )

                        # Skip all bracket-prefix notification types:
                        #   [新着]  = new message on item
                        #   [通知]  = join / participation alert
                        # Export completion emails do NOT have these prefixes.
                        if subject.startswith("[新着]") or subject.startswith("[通知]"):
                            seen.add(key)
                            continue

                        # Fetch full body (still PEEK)
                        _, bdata = conn.fetch(uid, "(BODY.PEEK[])")
                        if not bdata or not bdata[0]:
                            seen.add(key)
                            continue
                        msg = email_lib.message_from_bytes(
                            bdata[0][1], policy=email_lib.policy.default
                        )

                        body = ""
                        try:
                            if msg.is_multipart():
                                for part in msg.walk():
                                    ct = part.get_content_type()
                                    if ct in ("text/plain", "text/html"):
                                        try:
                                            body += part.get_content()
                                        except Exception:
                                            body += part.get_payload(decode=True).decode(
                                                "utf-8", errors="replace"
                                            )
                            else:
                                try:
                                    body = msg.get_content()
                                except Exception:
                                    body = msg.get_payload(decode=True).decode(
                                        "utf-8", errors="replace"
                                    )
                        except Exception as exc:
                            logger.warning("    Body parse error: %s", exc)

                        # Find download URL in the body.
                        # URL must look like a real file download, NOT a UI page.
                        # We exclude:
                        #   - item detail pages  (/productions/<digits>)
                        #   - the export-trigger URL itself (/productions/export?keyword=)
                        #   - generic account / notification page URLs
                        # We accept:
                        #   - S3 / GCS URLs (amazonaws, storage.googleapis)
                        #   - URLs whose PATH contains download / csv / export
                        #     but NOT the trigger-URL query string
                        urls = re.findall(r'https?://[^\s<>"\'）]+', body)
                        logger.info(
                            "    Body URLs (%d found): %s",
                            len(urls), [u[:80] for u in urls[:8]],
                        )
                        matched = None
                        for raw_url in urls:
                            raw_url = raw_url.rstrip("。、）>")
                            u = raw_url.lower()
                            # Skip item detail pages
                            if re.search(r"/productions/\d+", u):
                                continue
                            # Skip the export trigger URL (redirects to list, not a file)
                            if re.search(r"/productions/export\?keyword=", u):
                                continue
                            # Skip generic Sitateru UI pages
                            if any(skip in u for skip in [
                                "/s/account", "/s/notification", "/s/login",
                                "unsubscribe", "privacy", "terms",
                            ]):
                                continue
                            # Must look like an actual file download
                            if any(k in u for k in [
                                "amazonaws.com",
                                "storage.googleapis",
                                "storage.google",
                                "/download",
                                "/csv",
                                "export",          # covers /export/download, /exports/, etc.
                                ".csv",
                                "token=",          # time-limited presigned URL
                            ]):
                                matched = raw_url
                                break

                        if matched:
                            logger.info("    Download URL: %s", matched[:120])
                            return matched

                        logger.info("    No download URL matched in this email.")
                        seen.add(key)

        except imaplib.IMAP4.error as exc:
            logger.warning("    IMAP error: %s", exc)
        except OSError as exc:
            logger.warning("    Connection error (will retry): %s", exc)
        except Exception as exc:
            logger.warning("    Email poll error: %s", exc)

    logger.warning("    No download email found within %ds", timeout)
    return None


# ---------------------------------------------------------------------------
# Batch email collector (2-phase architecture)
# ---------------------------------------------------------------------------

def _discover_imap_folders(conn: imaplib.IMAP4_SSL) -> dict:
    """
    Run IMAP LIST and return {attr_lowercase: folder_name} for known RFC 6154 attrs.
    Handles Japanese Gmail where '[Gmail]/All Mail' is '[Gmail]/&MFkweTBmMG4w4TD8MOs-'.
    """
    result: dict = {}
    try:
        _, folder_list = conn.list()
        for item in folder_list:
            if not item:
                continue
            decoded = item.decode("ascii", errors="replace") if isinstance(item, bytes) else item
            m = re.match(r'\(([^)]+)\)\s+"[^"]+"\s+"?([^"\r\n]+)"?', decoded.strip())
            if not m:
                continue
            flags_str, name = m.group(1), m.group(2).strip().strip('"')
            for flag in flags_str.split():
                attr = flag.lstrip("\\").lower()
                if attr in ("all", "junk", "trash", "drafts", "sent", "important", "flagged"):
                    result.setdefault(attr, name)
    except Exception as exc:
        logger.warning("  _discover_imap_folders: %s", exc)
    return result


def _collect_all_export_emails(
    imap_host: str,
    imap_user: str,
    imap_pass: str,
    after_dt: datetime,
    expected_count: int,
    timeout: int = 1800,
    interval: int = 60,
) -> list[str]:
    """
    Poll INBOX + All Mail + Spam for up to `timeout` seconds, collecting ALL Sitateru
    export-completion email download URLs received after `after_dt`.

    Stops early when `expected_count` URLs have been found.
    Returns list of download URLs (may be fewer than expected if emails are late).
    """
    deadline = time.time() + timeout
    since_str = after_dt.strftime("%d-%b-%Y")          # IMAP SINCE format: 16-Jun-2026
    since_gmail = after_dt.strftime("%Y/%m/%d")        # Gmail X-GM-RAW format: 2026/06/16
    seen: set[tuple] = set()
    collected_urls: list[str] = []

    # Discover actual folder names via IMAP LIST (Japanese Gmail uses Modified UTF-7).
    # '[Gmail]/All Mail' does not exist — the real name is '[Gmail]/&MFkweTBmMG4w4TD8MOs-'.
    use_gmail_search = "gmail" in imap_host.lower()
    MAILBOXES = ["INBOX"]
    try:
        with imaplib.IMAP4_SSL(imap_host, 993) as _disc:
            _disc.login(imap_user, imap_pass)
            folder_map = _discover_imap_folders(_disc)
            all_mail = folder_map.get("all", "")
            spam     = folder_map.get("junk", "")
            if all_mail:
                MAILBOXES.append(all_mail)
                logger.info("  Discovered All Mail folder: %r", all_mail)
            if spam and spam not in MAILBOXES:
                MAILBOXES.append(spam)
                logger.info("  Discovered Spam folder: %r", spam)
    except Exception as exc:
        logger.warning("  Folder discovery failed: %s — using INBOX only", exc)

    logger.info(
        "  Phase 2: waiting up to %ds (%.0f min) for %d export email(s) "
        "(interval %ds, mailboxes=%s, gmail_search=%s) ...",
        timeout, timeout / 60, expected_count, interval, MAILBOXES, use_gmail_search,
    )

    while time.time() < deadline:
        elapsed   = int(time.time() - (deadline - timeout))
        remaining = int(deadline - time.time())
        logger.info(
            "  [email poll] collected=%d/%d  elapsed=%ds  remaining=%ds",
            len(collected_urls), expected_count, elapsed, remaining,
        )

        if len(collected_urls) >= expected_count:
            logger.info("  All %d download URL(s) collected.", expected_count)
            break

        time.sleep(interval)

        try:
            with imaplib.IMAP4_SSL(imap_host, 993) as conn:
                conn.login(imap_user, imap_pass)

                for mailbox in MAILBOXES:
                    try:
                        typ, _ = conn.select(mailbox, readonly=True)
                        if typ != "OK":
                            continue
                    except imaplib.IMAP4.error:
                        continue

                    # On Gmail use X-GM-RAW to return only Sitateru sender emails —
                    # avoids iterating 600+ unrelated notification headers per cycle.
                    if use_gmail_search:
                        try:
                            _, msg_ids = conn.search(
                                None,
                                f'X-GM-RAW "after:{since_gmail} from:sitateru"',
                            )
                        except imaplib.IMAP4.error:
                            _, msg_ids = conn.search(None, f'SINCE "{since_str}"')
                    else:
                        _, msg_ids = conn.search(None, f'SINCE "{since_str}"')
                    uids = msg_ids[0].split()
                    logger.info(
                        "  [%s] %d sitateru email(s) after %s",
                        mailbox, len(uids), since_gmail if use_gmail_search else since_str,
                    )
                    if not uids:
                        continue

                    for uid in reversed(uids):
                        key = (mailbox, uid)
                        if key in seen:
                            continue

                        _, hdata = conn.fetch(uid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
                        if not hdata or not hdata[0]:
                            seen.add(key)
                            continue

                        hdr = email_lib.message_from_bytes(
                            hdata[0][1], policy=email_lib.policy.default
                        )
                        from_addr = str(hdr.get("From", "")).lower()
                        subject   = str(hdr.get("Subject", ""))
                        date_hdr  = str(hdr.get("Date", ""))

                        # Date guard: skip emails older than the trigger time
                        try:
                            msg_dt = email.utils.parsedate_to_datetime(date_hdr)
                            if msg_dt.timestamp() < after_dt.timestamp():
                                seen.add(key)
                                continue
                        except Exception:
                            pass

                        # Log EVERY new email for diagnosis (helps find unexpected sender domains)
                        logger.info(
                            "  [%s] New email: from=%r  subject=%r",
                            mailbox, from_addr[:60], subject[:70],
                        )

                        # Skip notification-type subjects (not export completion emails)
                        if subject.startswith("[新着]") or subject.startswith("[通知]"):
                            seen.add(key)
                            continue

                        _, bdata = conn.fetch(uid, "(BODY.PEEK[])")
                        seen.add(key)
                        if not bdata or not bdata[0]:
                            continue

                        msg = email_lib.message_from_bytes(
                            bdata[0][1], policy=email_lib.policy.default
                        )
                        body = ""
                        try:
                            if msg.is_multipart():
                                for part in msg.walk():
                                    ct = part.get_content_type()
                                    if ct in ("text/plain", "text/html"):
                                        try:
                                            body += part.get_content()
                                        except Exception:
                                            body += part.get_payload(decode=True).decode(
                                                "utf-8", errors="replace"
                                            )
                            else:
                                try:
                                    body = msg.get_content()
                                except Exception:
                                    body = msg.get_payload(decode=True).decode(
                                        "utf-8", errors="replace"
                                    )
                        except Exception as exc:
                            logger.warning("  Body parse error: %s", exc)

                        urls = re.findall(r'https?://[^\s<>"\'）]+', body)
                        logger.info(
                            "  Body URLs (%d found): %s",
                            len(urls), [u[:80] for u in urls[:8]],
                        )
                        for raw_url in urls:
                            raw_url = raw_url.rstrip("。、）>")
                            u = raw_url.lower()
                            if re.search(r"/productions/\d+", u):
                                continue
                            if re.search(r"/productions/export\?keyword=", u):
                                continue
                            if any(skip in u for skip in [
                                "/s/account", "/s/notification", "/s/login",
                                "unsubscribe", "privacy", "terms",
                            ]):
                                continue
                            if any(k in u for k in [
                                "amazonaws.com", "storage.googleapis", "storage.google",
                                "/download", "/csv", "export", ".csv", "token=",
                            ]):
                                logger.info("  Found download URL: %s", raw_url[:120])
                                collected_urls.append(raw_url)
                                break


        except imaplib.IMAP4.error as exc:
            logger.warning("  IMAP error: %s", exc)
        except OSError as exc:
            logger.warning("  Connection error (will retry): %s", exc)
        except Exception as exc:
            logger.warning("  Email poll error: %s", exc)

    if len(collected_urls) < expected_count:
        logger.warning(
            "  Timeout: collected %d/%d download URL(s) after %ds",
            len(collected_urls), expected_count, timeout,
        )
    return collected_urls


# ---------------------------------------------------------------------------
# CSV download
# ---------------------------------------------------------------------------

def _download_url(page, url: str, tmp_dir: Path, label: str) -> Optional[Path]:
    """Download a file from url using the browser (maintains session cookies)."""
    # Sanity check: item detail pages are never file downloads
    if re.search(r"/productions/\d+", url) and "/export" not in url:
        logger.warning("    Skipping item detail page URL (not a download): %s", url[:80])
        return None
    logger.info("    Downloading: %s", url[:80])
    try:
        with page.expect_download(timeout=120_000) as dl_info:
            page.goto(url, timeout=60_000)
        dl    = dl_info.value
        fname = dl.suggested_filename or f"sitateru_{label}.csv"
        out   = tmp_dir / f"{label}_{fname}"
        dl.save_as(str(out))
        logger.info("    Saved: %s (%d bytes)", out.name, out.stat().st_size)
        return out
    except Exception as exc:
        logger.warning("    Download failed (%s): %s", url[:60], str(exc)[:80])

    # Fallback: urllib with session cookies
    try:
        import ssl, urllib.request
        cookies = page.context.cookies()
        cookie_hdr = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode   = ssl.CERT_NONE
        req = urllib.request.Request(url, headers={
            "Cookie": cookie_hdr,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0",
        })
        with urllib.request.urlopen(req, timeout=60, context=ssl_ctx) as resp:
            raw = resp.read()
        out = tmp_dir / f"{label}_download.csv"
        out.write_bytes(raw)
        logger.info("    Fallback download: %s (%d bytes)", out.name, len(raw))
        return out
    except Exception as exc2:
        logger.warning("    Fallback download failed: %s", str(exc2)[:80])
    return None


# ---------------------------------------------------------------------------
# CSV merge
# ---------------------------------------------------------------------------

def _merge_csvs(csv_files: list[Path]) -> bytes:
    """Merge CSVs, dedup by アイテムID (or first column)."""
    all_rows: dict[str, dict] = {}
    header: Optional[list[str]] = None

    for f in csv_files:
        raw = f.read_bytes()
        text: Optional[str] = None
        for enc in ("utf-8-sig", "utf-8", "cp932"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            logger.warning("Cannot decode: %s", f.name)
            continue

        reader = csv.DictReader(io.StringIO(text))
        if header is None:
            header = list(reader.fieldnames or [])
        for row in reader:
            item_id = (
                row.get("アイテムID")
                or row.get("sitateru_item_id")
                or row.get("item_id", "")
                or next(iter(row.values()), "")
            )
            if item_id:
                all_rows[str(item_id)] = row

    if not header or not all_rows:
        return b""

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=header, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(all_rows.values())
    return ("﻿" + buf.getvalue()).encode("utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(dry_run: bool = False, target_date: Optional[date] = None) -> None:
    import tempfile

    today_jst = datetime.now(JST).date()
    if target_date is None:
        target_date = today_jst - timedelta(days=1)
    date_str = target_date.strftime("%Y-%m-%d")

    seasons = get_active_seasons(today_jst)
    base_queries = [
        f"{div} {season} {status}"
        for div in DIVISIONS
        for season in seasons
        for status in STATUSES
    ]

    logger.info("=" * 60)
    logger.info("Sitateru item list fetch")
    logger.info("  target date : %s", date_str)
    logger.info("  seasons     : %s", seasons)
    logger.info("  Layer1 queries: %d", len(base_queries))

    if dry_run:
        logger.info("[DRY RUN] Query plan:")
        for q in base_queries:
            logger.info("  %r", q)
        return

    # -- Credentials --
    user         = (os.environ.get("SITATERU_USER") or os.environ.get("LOGIN_USER", "")).strip()
    pw           = (os.environ.get("SITATERU_PASS") or os.environ.get("LOGIN_PASS", "")).strip()
    imap_host    = os.environ.get("IMAP_HOST", "imap.gmail.com")
    imap_user    = os.environ.get("IMAP_USER", "").strip()
    imap_pass    = os.environ.get("IMAP_PASS", "").strip()
    bucket_name  = os.environ.get("GCS_RAW_BUCKET", "mono-back-office-system-raw-data")
    project_id   = os.environ.get("GCP_PROJECT_ID",  "mono-back-office-system")

    if not imap_user or not imap_pass:
        logger.error(
            "IMAP_USER / IMAP_PASS not set.\n"
            "  Set them before running:\n"
            "    $env:IMAP_USER = 'yujin-yamaguchi@mono-mart.jp'\n"
            "    $env:IMAP_PASS = '<gmail-app-password>'"
        )
        sys.exit(2)

    # -- GCP credentials: auto-detect ADC file or fall back to SA key --
    if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        adc_path = os.path.join(
            os.environ.get("APPDATA", ""), r"gcloud\application_default_credentials.json"
        )
        sa_path = str(_PIPELINE / "sheets-sa-key.json")
        if os.path.exists(adc_path):
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = adc_path
            logger.info("GCP credentials: ADC (%s)", adc_path)
        elif os.path.exists(sa_path):
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = sa_path
            logger.info("GCP credentials: SA key (%s)", sa_path)
        else:
            logger.warning("No GCP credentials found — GCS upload will fail")

    if not os.environ.get("GOOGLE_CLOUD_PROJECT"):
        os.environ["GOOGLE_CLOUD_PROJECT"] = project_id

    try:
        from playwright.sync_api import sync_playwright
        from google.cloud import storage as gcs_storage
    except ImportError as exc:
        logger.error("Missing dependency: %s", exc)
        sys.exit(1)

    downloaded: list[Path] = []

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        with sync_playwright() as pw_ctx:
            browser = pw_ctx.chromium.launch(
                headless=(os.environ.get("HEADLESS", "1") == "1"),
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            )
            state_file = str(_STATE) if _STATE.exists() else None
            ctx = browser.new_context(
                storage_state=state_file,
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                accept_downloads=True,
                locale="ja-JP",
            )
            page = ctx.new_page()

            # -- Auth check --
            page.goto(f"{BASE_URL}/s/", timeout=30_000, wait_until="domcontentloaded")
            time.sleep(4)
            _shot(page, "01_initial")

            if not _is_logged_in(page):
                logger.info("Session expired -- re-logging in")
                if not user or not pw:
                    logger.error("SITATERU_USER / SITATERU_PASS not set")
                    sys.exit(2)
                if not _login(page, user, pw):
                    sys.exit(2)
            else:
                logger.info("Session valid: %s", page.url)

            # -- Check which Sitateru account is logged in --
            # Export completion emails go to THIS address, not necessarily IMAP_USER.
            acct_email = _get_account_email(page)
            if acct_email:
                logger.info("Sitateru account email : %s", acct_email)
                if acct_email.lower() != imap_user.lower():
                    logger.warning(
                        "ACCOUNT MISMATCH: Sitateru exports will be emailed to %s "
                        "but IMAP_USER=%s. Set IMAP_USER=%s to receive them.",
                        acct_email, imap_user, acct_email,
                    )
            else:
                logger.warning("Could not read Sitateru account email (screenshot: sitateru_account.png)")
                _shot(page, "account")

            # -- Phase 1a: Enumerate all queries, expand L2/L3, build export list --
            pending_exports: list[tuple[str, str]] = []  # (query, label)
            label_idx = 0
            total_q   = len(base_queries)

            for qi, query in enumerate(base_queries):
                logger.info("[%d/%d] %r", qi + 1, total_q, query)
                page.goto(_search_url(query), timeout=30_000, wait_until="networkidle")
                time.sleep(3)
                count = _get_count(page)
                logger.info("  count=%s", count)

                if count is None:
                    logger.warning("  count unknown -- skipping")
                    continue
                if count == 0:
                    logger.info("  0 hits -- skipping")
                    continue

                if count <= RESULT_CAP:
                    pending_exports.append((query, f"{label_idx:04d}"))
                    label_idx += 1
                else:
                    logger.info("  %d > %d -- expanding to Layer 2", count, RESULT_CAP)
                    for flag in FLAGS:
                        l2_query = f"{query} {flag}"
                        page.goto(_search_url(l2_query), timeout=20_000, wait_until="networkidle")
                        time.sleep(2)
                        l2_count = _get_count(page)
                        if not l2_count or l2_count == 0:
                            continue
                        if l2_count <= RESULT_CAP:
                            pending_exports.append((l2_query, f"{label_idx:04d}"))
                            label_idx += 1
                        else:
                            logger.info("  Layer2 %d > %d -- expanding to Layer 3", l2_count, RESULT_CAP)
                            for otype in ORDER_TYPES:
                                l3_query = f"{l2_query} {otype}"
                                page.goto(_search_url(l3_query), timeout=20_000, wait_until="networkidle")
                                time.sleep(2)
                                l3_count = _get_count(page)
                                if not l3_count or l3_count == 0:
                                    continue
                                if l3_count > RESULT_CAP:
                                    logger.warning("  Layer3 still %d > cap: %r", l3_count, l3_query)
                                pending_exports.append((l3_query, f"{label_idx:04d}"))
                                label_idx += 1

            logger.info("Phase 1a complete: %d export(s) queued", len(pending_exports))

            if not pending_exports:
                logger.warning("No queries produced results -- nothing to export")
                ctx.close()
                browser.close()
                sys.exit(0)

            # -- Phase 1b: Trigger ALL exports; try direct download first --
            # Primary path: navigate directly to /productions/export URL.
            #   - If the server responds with a CSV attachment → save immediately.
            #   - If the server queues the job and redirects → email will be sent.
            # Fallback: modal click (_trigger_export) if direct navigation fails.
            earliest_trigger_dt = datetime.now(JST)
            triggered_count = 0
            for exp_query, exp_lbl in pending_exports:
                dl, triggered = _download_export_direct(page, exp_query, tmp, exp_lbl)
                if dl:
                    downloaded.append(dl)
                    logger.info("    [direct] saved %s", dl.name)
                elif triggered:
                    triggered_count += 1   # async — email pending
                else:
                    # Direct navigation failed; fall back to modal click
                    logger.info("    Falling back to modal click for %r", exp_query[:40])
                    if _trigger_export(page, exp_query):
                        triggered_count += 1
                time.sleep(2)

            logger.info(
                "Phase 1b complete: %d direct  %d async-email  (of %d) at %s JST",
                len(downloaded), triggered_count, len(pending_exports),
                earliest_trigger_dt.strftime("%H:%M:%S"),
            )

            # Save session state before closing browser
            try:
                page.context.storage_state(path=str(_STATE))
                logger.info("Session state saved to %s", _STATE)
            except Exception as exc:
                logger.warning("Session save failed: %s", exc)

            ctx.close()
            browser.close()

            if triggered_count == 0 and not downloaded:
                logger.warning("No exports triggered and no direct downloads -- nothing to do")
                sys.exit(0)

            download_urls: list[str] = []

            if triggered_count > 0:
                # -- Phase 2: Collect ALL export completion emails (up to 60 min) --
                download_urls = _collect_all_export_emails(
                    imap_host, imap_user, imap_pass,
                    earliest_trigger_dt,
                    expected_count=triggered_count,
                    timeout=3600,
                    interval=60,
                )
                logger.info(
                    "Phase 2 complete: %d email URL(s)  +  %d direct download(s)",
                    len(download_urls), len(downloaded),
                )
                if not download_urls and not downloaded:
                    logger.warning("No download URLs and no direct downloads -- skipping upload")
                    sys.exit(0)
            else:
                logger.info(
                    "All %d export(s) downloaded directly — skipping Phase 2 email poll",
                    len(downloaded),
                )

            # -- Phase 3: Download CSVs from email URLs (only if any found) --
            if download_urls:
                browser3 = pw_ctx.chromium.launch(
                    headless=(os.environ.get("HEADLESS", "1") == "1"),
                    args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
                )
                state_file3 = str(_STATE) if _STATE.exists() else None
                ctx3 = browser3.new_context(
                    storage_state=state_file3,
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                    accept_downloads=True,
                    locale="ja-JP",
                )
                page3 = ctx3.new_page()

                for i, url in enumerate(download_urls):
                    dl = _download_url(page3, url, tmp, f"{i:04d}")
                    if dl:
                        downloaded.append(dl)

                ctx3.close()
                browser3.close()

        # -- Merge + GCS upload --
        if not downloaded:
            logger.warning("No CSVs downloaded -- skipping ETL")
            sys.exit(0)

        logger.info("Merging %d CSV file(s)...", len(downloaded))
        merged = _merge_csvs(downloaded)

        if not merged:
            logger.warning("Merged CSV is empty -- check downloaded files")
            sys.exit(0)

        # Lazy GCS client (credentials must be ready by now)
        gcs_client = gcs_storage.Client(project=project_id)
        bucket_obj = gcs_client.bucket(bucket_name)

        yyyymmdd  = date_str.replace("-", "")
        filename  = f"item_list_{yyyymmdd}.csv"
        blob_name = f"uploads/sitateru/itemlist/{date_str}/{filename}"
        blob      = bucket_obj.blob(blob_name)
        blob.upload_from_string(merged, content_type="text/csv; charset=utf-8")
        uri = f"gs://{bucket_name}/{blob_name}"
        row_count = len(merged.decode("utf-8-sig").splitlines()) - 1
        logger.info("Uploaded: %s  (%d bytes, %d rows)", uri, len(merged), row_count)

    # -- ETL --
    logger.info("Running ETL ingest...")
    rc = subprocess.run(
        [sys.executable, str(_MAIN_PY), "--csv-ingest", "--date", date_str],
        cwd=str(_PIPELINE),
    ).returncode
    if rc == 0:
        logger.info("ETL ingest complete")
    else:
        logger.warning("ETL ingest exit=%d (non-fatal)", rc)

    logger.info("=" * 60)


def main() -> None:
    ap = argparse.ArgumentParser(description="Sitateru item list auto-download")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--date", help="Target date YYYY-MM-DD (default: yesterday JST)")
    args = ap.parse_args()
    run(dry_run=args.dry_run, target_date=date.fromisoformat(args.date) if args.date else None)


if __name__ == "__main__":
    main()
