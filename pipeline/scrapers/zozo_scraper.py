"""
ZOZO Back Office automated scraper (production-ready).

Handles 2-stage authentication and downloads 9 CSV file types daily,
uploading them to GCS for the existing ETL pipeline to consume.

Session management:
  ZOZO BO sessions expire quickly during automated browsing. The scraper
  detects "タイムアウトしました" / login page and re-authenticates as needed.

ENV vars (Secret Manager preferred for production):
  ZOZO_BASIC_USER          stage 1 HTTP Basic auth
  ZOZO_BASIC_PASSWORD
  ZOZO_LOGIN_ID            stage 2 form login
  ZOZO_LOGIN_PASSWORD
  GCS_RAW_BUCKET           target bucket
  GCP_PROJECT_ID
  TARGET_DATE              optional (default: yesterday JST)
  HEADLESS                 "1" / "0" (default 1)
  ONLY                     comma-separated list to limit which sources to run

Run:
  pip install playwright google-cloud-storage google-cloud-bigquery
  playwright install chromium
  python pipeline/scrapers/zozo_scraper.py
"""
from __future__ import annotations

import logging
import os
import sys
import time
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

from google.cloud import storage

try:
    from playwright.sync_api import sync_playwright, BrowserContext, Page
    from playwright.sync_api import TimeoutError as PWTimeout
except ImportError:
    print("Error: playwright not installed. Run: pip install playwright && playwright install chromium")
    sys.exit(1)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("zozo_scraper")

JST = timezone(timedelta(hours=9))
LOGIN_URL = "https://to.zozo.jp/to/"
BASE_URL  = "https://to.zozo.jp/to/"

# Session expiry detection — these strings on the page mean we got logged out
SESSION_EXPIRED_MARKERS = [
    "タイムアウトしました",
    "セッションが切れました",
    "再度ログイン",
]

# Resilience tuning — directly addresses the アシロボ pain points the client
# reported (ZOZOBO timeouts stopping scenarios, one error blocking the rest).
MAX_RETRIES_PER_SOURCE = int(os.getenv("MAX_RETRIES_PER_SOURCE", "3"))
RETRY_BACKOFF_BASE_SEC = float(os.getenv("RETRY_BACKOFF_BASE_SEC", "5"))
PARALLEL_WORKERS       = int(os.getenv("PARALLEL_WORKERS", "1"))  # >1 → run sources concurrently


# ──────────────────────────────────────────────────────────────────────────────
# Per-source configuration
#
# Each entry defines how to download one CSV. Three patterns supported:
#
#   strategy = "form_submit"    Visit page_url, fill form, click trigger
#                                button, capture download.
#   strategy = "direct_link"    Visit page_url, click ダウンロード dropdown
#                                link directly (force).
#   strategy = "session_get"    Visit setup_url first to seed session,
#                                then issue GET on download_url with cookies.
#
# Selectors and URLs are best-effort — many will need refinement against
# the actual ZOZO UI when running for the first time.
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class SourceConfig:
    name: str                    # internal identifier
    label: str                   # human-readable name
    page_url: str                # URL to navigate to
    gcs_prefix: str              # GCS folder under uploads/
    strategy: str = "direct_link"
    download_url: Optional[str]  = None    # for session_get strategy
    download_selector: str       = "a.dropdown-link[href*='download']"
    submit_button: str           = "button:has-text('ダウンロード')"
    filename_default: str        = "data.csv"
    apply_filters: Optional[Callable[["Page", str], None]] = None
    has_2day_lag: bool           = False   # No.8 商品別実績 has 2-day lag
    # form_post strategy: replay the exact CSV-generating POST captured from
    # the live site. {D} is substituted with the URL-encoded target date
    # (YYYY%2FMM%2FDD). This is the most robust path — no fragile UI clicks.
    post_url: Optional[str]      = None
    post_template: Optional[str] = None
    # looker_performance strategy: dashboard link text on LookerDashboards.asp
    # ('商品別実績(新)', 'アクセス実績(新)', '検索キーワード経由アクセス実績', etc.).
    looker_link_text: Optional[str] = None
    # Looker: which tile's data to download. Substring match on aria-label.
    # None (商品別実績の場合) → default per-shop loop with the single results tile.
    # 'DL用' → match a tile whose aria-label contains "DL用" (e.g. 日別検索キーワードTOP20_DL用)
    looker_tile_label: Optional[str] = None
    # Looker: skip per-shop filter loop when filter is "任意の値である" by default
    looker_skip_shop_filter: bool = False
    # Looker: click a tab BEFORE looking for the DL tile. Tab buttons live
    # in the EXTENSION iframe (extensions.cloud.looker.com); clicking one
    # replaces the dashboard iframe (its URL changes from ::dashboard_X to
    # ::dashboard_Y), so the flow has to re-locate `dash` after the click.
    looker_tab_label: Optional[str] = None
    # Looker: download via the DASHBOARD-level menu instead of a per-tile
    # kebab. Some dashboards (rpid=9 App/PC-SP tabs) expose the「ダウンロード」
    # link in the top-right「ダッシュボード アクション」menu rather than on
    # individual tiles. When True the scraper:
    #   1. Sets ショップ名 filter via multi-select (clicks each of 7 options)
    #   2. Clicks the button[aria-label="ダッシュボード アクション"]
    #   3. Clicks the「ダウンロード」menu item that appears
    looker_use_dashboard_dl: bool = False


# ── Filter functions ──────────────────────────────────────────────────────────

def filter_yesterday(page: Page, target_date: str) -> None:
    """Click '前日' button if present."""
    for sel in ['label:has-text("前日")', 'input[value="yesterday"]',
                'button:has-text("前日")']:
        try:
            if page.locator(sel).count() > 0:
                page.locator(sel).first.click(timeout=3_000)
                return
        except Exception:
            continue


def filter_all_shops(page: Page, target_date: str) -> None:
    """Select 全店 (all shops) if available."""
    for sel in ['label:has-text("全店")', 'input[value="-1"]',
                'select[name*="shop"] option[value="-1"]']:
        try:
            if page.locator(sel).count() > 0:
                page.locator(sel).first.click(timeout=3_000)
                return
        except Exception:
            continue


def filter_reservations(page: Page, target_date: str) -> None:
    """予約管理一覧 (Reserve.asp) 専用フィルタ.

    Bug fix 2026-06-09: Reserve.asp の form は `SEARCH_ArriveDT` (入荷予定日
    フィルタ) がデフォルト ON で 2026/05/上旬〜2026/07/上旬 (≈ 2ヶ月) に絞られ
    ていた。これが原因で「2026/08/上旬」の予約棚が CSV から欠落していた.
    クライアントが言う「全て指定なし」状態に揃えるため、入荷予定日フィルタを
    無効化する.
    """
    # 全店 (ShopID=-1)
    try:
        page.evaluate(r"""() => {
          for (const s of document.querySelectorAll('select[name*="hop"]')) {
            for (const o of s.options) {
              if (o.value === '-1') { s.value = '-1';
                s.dispatchEvent(new Event('change', {bubbles: true}));
                break; }
            }
          }
        }""")
    except Exception:
        pass
    # 入荷予定日フィルタを OFF (= 全期間)
    try:
        page.evaluate(r"""() => {
          // Uncheck SEARCH_ArriveDT so the form posts without the
          // ArriveDT(From|To)Year/Month/Day constraints.
          for (const cb of document.querySelectorAll(
                'input[name="SEARCH_ArriveDT"]')) {
            cb.checked = false;
            cb.dispatchEvent(new Event('change', {bubbles: true}));
          }
        }""")
    except Exception:
        pass
    time.sleep(0.5)


def filter_2day_lag(page: Page, target_date: str) -> None:
    """For 商品別実績: select 前々日 (2 days ago)."""
    target_2day = (datetime.fromisoformat(target_date) - timedelta(days=1)).strftime("%Y-%m-%d")
    try:
        page.locator('label:has-text("カスタム")').first.click(timeout=3_000)
        page.fill('input[type="date"]', target_2day)
    except Exception:
        pass


def set_looker_date_last7(dash) -> bool:
    """商品別実績などLooker日付フィルタを「最後 7 日間」に設定。
    既定が「前週」だと先週(〜先週末)までしか取れず最新日が欠ける（顧客2026）。
    最後7日間にすると2日ラグ込みの最新まで取得できる。"""
    try:
        time.sleep(3)
        # 1) 日付チップを開く（既定「前週」。将来変わる可能性に備え複数候補を順に試す）
        clicked = False
        for label in ("前週", "最後 7 日間", "最後 14 日間", "今週", "前日", "昨日", "今日", "年初来"):
            try:
                loc = dash.get_by_text(label, exact=True)
                if loc.count() > 0:
                    loc.first.click(timeout=4_000)
                    clicked = True
                    break
            except Exception:
                continue
        if not clicked:
            return False
        time.sleep(2)
        # 2) 「最後 7 日間」を選択（ドロップダウン内）
        dash.get_by_text("最後 7 日間").first.click(timeout=5_000)
        time.sleep(2)
        # 3) 更新/適用（あれば）
        for sel in ("button:has-text('更新')", "button:has-text('適用')"):
            loc = dash.locator(sel)
            if loc.count() > 0 and loc.first.is_visible():
                loc.first.click(timeout=3_000)
                break
        time.sleep(8)
        return True
    except Exception:
        return False


def filter_stock_analysis_options(page: Page, target_date: str) -> None:
    """Enable ALL optional display columns in 在庫分析データ (StockAnalysis.asp).

    Client request 2026-06-17/18: check ALL optional columns — not just
    お気に入り登録数 but also 最終入荷日(=継続入荷日, ArriveDT) と バーコード(Barcode).

    お気に入り登録数の期間指定 (client 2026-06-18):
      期間指定をチェックしないと「直近30日」のお気に入り数になってしまう。
      仕様は「前日分だけ」を取得すること。日次実行の target_date は既に前日なので、
      期間 = target_date 〜 target_date (単日) を指定する。

    Confirmed field names from cap_stock_analysis.json:
      ArriveDT      checkbox  最終入荷日 (継続入荷日)
      FavoriteList  checkbox  お気に入り登録数
      FavoriteListDT checkbox 期間指定する
      FavoriteDTFrom text     期間FROM  (YYYY/MM/DD)
      FavoriteDTTo   text     期間TO    (YYYY/MM/DD)
      Barcode       checkbox  バーコード
    """
    # 前日分のみ: from = to = target_date (= 前日)。30日窓ではない (client 2026-06-18)。
    dt_to   = target_date.replace("-", "/")
    dt_from = dt_to
    try:
        page.evaluate(f"""() => {{
          for (const name of ['ArriveDT', 'FavoriteList', 'FavoriteListDT', 'Barcode']) {{
            const cb = document.querySelector('input[type="checkbox"][name="' + name + '"]');
            if (cb && !cb.checked) {{
              cb.checked = true;
              cb.dispatchEvent(new Event('change', {{bubbles: true}}));
            }}
          }}
          const dtFrom = document.querySelector('input[name="FavoriteDTFrom"]');
          const dtTo   = document.querySelector('input[name="FavoriteDTTo"]');
          if (dtFrom) dtFrom.value = '{dt_from}';
          if (dtTo)   dtTo.value   = '{dt_to}';
        }}""")
    except Exception:
        pass


# ── 9 file types ──────────────────────────────────────────────────────────────

# DL_BUTTON value is the Shift-JIS bytes of "ダウンロード" (ZOZO BO is Shift_JIS).
_DLB = "%83_%83E%83%93%83%8D%81%5B%83h"

# Recipes below were reverse-engineered from the LIVE site on 2026-05-15 by
# capturing the exact CSV-generating POST (see explore/probe scripts).
#   {D} → URL-encoded target date  YYYY%2FMM%2FDD
SOURCES: list[SourceConfig] = [
    # ✅ verified live: 9.3 MB CSV
    SourceConfig(
        name="orders", label="受注 (No.1)",
        page_url="order_csv.asp?c=Order_CSV",
        gcs_prefix="zozo/orders",
        strategy="form_post",
        post_url="https://to.zozo.jp/to/order_csv.asp",
        post_template=(f"c=Download&ShopID=-1&SCategoryPID=0&SCategoryID=0"
                       f"&ost=order&TermFrom={{D}}&TermTo={{D}}&MallCheck=0"
                       f"&DL_BUTTON={_DLB}"),
        filename_default="orders.csv",
    ),
    # ✅ verified live: 588 KB CSV (same endpoint, ost=send)
    SourceConfig(
        name="shipped", label="発送 (No.2)",
        page_url="order_csv.asp?c=Order_CSV",
        gcs_prefix="zozo/shipped",
        strategy="form_post",
        post_url="https://to.zozo.jp/to/order_csv.asp",
        post_template=(f"c=Download&ShopID=-1&SCategoryPID=0&SCategoryID=0"
                       f"&ost=send&TermFrom={{D}}&TermTo={{D}}&MallCheck=0"
                       f"&DL_BUTTON={_DLB}"),
        filename_default="shipped.csv",
    ),
    # 予約管理一覧 — no static CSV trigger; falls through robust cascade.
    # `filter_reservations` clears the default 2-month ArriveDT filter so the
    # CSV includes ALL arrival batches (e.g., 2026/08/上旬 in addition to
    # 2026/06/下旬). Fixed 2026-06-09.
    SourceConfig(
        name="reservations", label="予約管理一覧 (No.3)",
        page_url="Reserve.asp?c=ReserveList",
        gcs_prefix="zozo/reservations",
        strategy="cascade",
        filename_default="reservations.csv",
        apply_filters=filter_reservations,
    ),
    # ✅ verified recipe: zaiko_csv2.asp POST (SelectListType=1 → SKU毎)
    SourceConfig(
        name="inventory_sku", label="倉庫在庫 SKU毎 (No.4)",
        page_url="zaiko_csv2.asp?c=Zaiko",
        gcs_prefix="zozo/inventory_sku",
        strategy="form_post",
        post_url="https://to.zozo.jp/to/zaiko_csv2.asp",
        post_template=(f"c=ZaikoDownload&ShopID=-1&SCategoryPID=0&SCategoryID=0"
                       f"&BrandGoodsCode=&SelectPriceType=0&SEARCH_ArriveDT=0"
                       f"&TermFrom={{D}}&TermTo={{D}}&ArriveTerm=180"
                       f"&SelectListType=1&DL_BUTTON={_DLB}"),
        filename_default="inventory_sku.csv",
    ),
    # ✅ verified recipe: same zaiko_csv2.asp endpoint, SelectListType=2 →
    #   倉庫在庫:入荷日毎 (No.5). Client: this supersedes SKU毎 for 発注管理表.
    SourceConfig(
        name="inventory_arrival", label="倉庫在庫 入荷日毎 (No.5)",
        page_url="zaiko_csv2.asp?c=Zaiko",
        gcs_prefix="zozo/inventory_arrival",
        strategy="form_post",
        post_url="https://to.zozo.jp/to/zaiko_csv2.asp",
        post_template=(f"c=ZaikoDownload&ShopID=-1&SCategoryPID=0&SCategoryID=0"
                       f"&BrandGoodsCode=&SelectPriceType=0&SEARCH_ArriveDT=0"
                       f"&TermFrom={{D}}&TermTo={{D}}&ArriveTerm=180"
                       f"&SelectListType=2&DL_BUTTON={_DLB}"),
        filename_default="inventory_arrival.csv",
    ),
    # ✅ works via cascade (6 MB) — keep it
    # 2026-06-17: enable ALL optional columns per client request:
    #   継続入荷日 (ArriveDT), お気に入り登録数 (FavoriteList), バーコード (Barcode)
    SourceConfig(
        name="stock_analysis", label="在庫分析 (No.6)",
        page_url="StockAnalysis.asp?c=init",
        gcs_prefix="zozo/stock_analysis",
        strategy="cascade",
        filename_default="stock_analysis.csv",
        apply_filters=lambda p, d: (filter_all_shops(p, d), filter_stock_analysis_options(p, d)),
    ),
    # ZOZOAD (No.7) — handled by dedicated fetcher (fetch_zozoad_report.py)
    # invoked from run_daily.ps1 [1f]. Advertisement.asp itself is the budget
    # config page; the actual 品番別CSV lives behind the ZOZOAD>レポート sub-
    # navigation which requires its own discovery flow. Removed from this
    # cascade list to avoid HTML-instead-of-CSV writes corrupting the ETL.
    # ✅ Looker embed: per-shop UI download (filter → render → kebab → modal →
    #   download). Requires stealth Chromium flags (Looker iframe refuses to
    #   load otherwise). Output is UTF-8 TSV; downstream parser converts to CSV.
    SourceConfig(
        name="performance", label="商品別実績(新) (No.8)",
        page_url="LookerDashboards.asp",
        gcs_prefix="zozo/performance",
        strategy="looker_performance",
        filename_default="商品別実績.tsv",
        looker_link_text="商品別実績(新)",
        has_2day_lag=True,
    ),
    # ✅ 検索キーワード経由アクセス実績 (No.20) — Looker rpid=11
    # Updated 2026-06-09 per client request:
    #   ・「ショップ親カテゴリ別」tab (NOT ショップ別 — the latter biases
    #     top keywords toward dominant parent categories)
    #   ・dashboard-level「ダウンロード」 (NOT tile-level kebab) to capture
    #     ALL keywords (not just TOP20)
    #   ・format CSV + expand-tables「すべての結果」flow same as access_log
    SourceConfig(
        name="search_keyword", label="検索キーワード経由 (No.20)",
        page_url="LookerDashboards.asp",
        gcs_prefix="zozo/search_keyword",
        strategy="looker_performance",
        filename_default="search_keyword.csv",
        looker_link_text="検索キーワード経由アクセス実績",
        looker_tab_label="ショップ親カテゴリ別",
        looker_tile_label="日別検索キーワードTOP20(ショップ親カテゴリ)_DL用",
        looker_use_dashboard_dl=True,
        looker_skip_shop_filter=True,
    ),
    # ✅ アクセス実績(新) App(ショップ親カテゴリ) (No.19a) — Looker rpid=9 / tab App
    # Confirmed 2026-06-05: click「App(ショップ親カテゴリ)」tab → multi-select
    # all 7 shops in ショップ名 filter → click dashboard-level「ダウンロード」 in
    # 「ダッシュボード アクション」menu → change format from PDF to CSV →
    # final ダウンロード → ZIP containing per-tile CSVs.
    # `looker_tile_label` here is used to pick the target CSV out of the ZIP.
    SourceConfig(
        name="access_log_app", label="アクセス実績 App (No.19a)",
        page_url="LookerDashboards.asp",
        gcs_prefix="zozo/access_log_app",
        strategy="looker_performance",
        filename_default="access_log_app.csv",
        looker_link_text="アクセス実績(新)",
        looker_tab_label="App(ショップ親カテゴリ)",
        looker_tile_label="アクセス実績_App_DL用",
        looker_use_dashboard_dl=True,
        looker_skip_shop_filter=True,  # we apply our own multi-select
    ),
    # ✅ アクセス実績(新) PC/SP(ショップ親カテゴリ) (No.19b) — same flow
    SourceConfig(
        name="access_log_pcsp", label="アクセス実績 PC/SP (No.19b)",
        page_url="LookerDashboards.asp",
        gcs_prefix="zozo/access_log_pcsp",
        strategy="looker_performance",
        filename_default="access_log_pcsp.csv",
        looker_link_text="アクセス実績(新)",
        looker_tab_label="PC/SP(ショップ親カテゴリ)",
        looker_tile_label="アクセス実績_PC/SP_DL用",
        looker_use_dashboard_dl=True,
        looker_skip_shop_filter=True,
    ),
    # ✅ verified recipe: GoodsSearch.asp POST(c=Search) + GET(c=ListDownLoadCS),
    #   per shop. ZOZO BO rejects ShopID=0/-1/empty (HTML error), so we MUST
    #   loop the 7 user shops and concatenate (header kept once).
    SourceConfig(
        name="product_master", label="登録商品 SKU単位 (No.9)",
        page_url="GoodsSearch.asp?c=Init",
        gcs_prefix="zozo/product_master",
        strategy="goods_search",
        post_url="https://to.zozo.jp/to/GoodsSearch.asp",
        filename_default="goods_cs.csv",
    ),
    # ✅ recipe known: Sales_download.asp central center (needs csrf+FileName)
    SourceConfig(
        name="sale_settings", label="セール設定 (No.17)",
        page_url="Sales_download.asp",
        gcs_prefix="zozo/sale",
        strategy="sales_center",
        post_url="https://to.zozo.jp/to/Sales_download.asp",
        filename_default="salegoods.csv",
    ),
]


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def get_target_date() -> str:
    env = os.getenv("TARGET_DATE")
    if env:
        return env
    return (datetime.now(JST) - timedelta(days=1)).strftime("%Y-%m-%d")


# Logical credential name → list of candidate Secret Manager secret IDs.
# The secrets in this project are named ZOZO_BASIC_USER / ZOZO_BASIC_PASS /
# ZOZO_USER / ZOZO_PASS — NOT the longer env-var style names. Try every
# known alias so the scraper works regardless of which convention is used.
SECRET_ALIASES: dict[str, list[str]] = {
    "ZOZO_BASIC_USER":     ["ZOZO_BASIC_USER"],
    "ZOZO_BASIC_PASSWORD": ["ZOZO_BASIC_PASSWORD", "ZOZO_BASIC_PASS"],
    "ZOZO_LOGIN_ID":       ["ZOZO_LOGIN_ID", "ZOZO_USER"],
    "ZOZO_LOGIN_PASSWORD": ["ZOZO_LOGIN_PASSWORD", "ZOZO_PASS"],
}


def get_secret(name: str) -> Optional[str]:
    # 1) env var under the canonical name or any alias
    for candidate in [name] + SECRET_ALIASES.get(name, []):
        val = os.getenv(candidate)
        if val:
            return val
    # 2) Secret Manager — try every alias until one resolves
    try:
        from google.cloud import secretmanager
        client = secretmanager.SecretManagerServiceClient()
        project = os.getenv("GCP_PROJECT_ID", "mono-back-office-system")
        for candidate in [name] + SECRET_ALIASES.get(name, []):
            try:
                resp = client.access_secret_version(request={
                    "name": f"projects/{project}/secrets/{candidate}/versions/latest"})
                return resp.payload.data.decode("utf-8")
            except Exception:
                continue
    except Exception:
        return None
    return None


def _safe_body_len(frame) -> int:
    """Return the inner text length of a Looker frame, or -1 if detached."""
    try:
        return frame.evaluate(
            "() => document.body ? document.body.innerText.length : 0") or 0
    except Exception:
        return -1


def is_session_expired(page: Page) -> bool:
    try:
        body = page.inner_text("body")
        return any(m in body for m in SESSION_EXPIRED_MARKERS)
    except Exception:
        return False


# ──────────────────────────────────────────────────────────────────────────────
# Scraper
# ──────────────────────────────────────────────────────────────────────────────

class ZOZOScraper:
    def __init__(self, basic_user: str, basic_pw: str,
                 login_id: str, password: str, headless: bool = True):
        self.basic_user = basic_user
        self.basic_pw   = basic_pw
        self.login_id   = login_id
        self.password   = password
        self.headless   = headless
        self.target_date = get_target_date()
        self.gcs_bucket  = os.getenv("GCS_RAW_BUCKET", "mono-back-office-system-raw-data")
        self.gcs_client  = storage.Client()
        self.run_id      = uuid.uuid4().hex[:12]

    def run(self, only: Optional[list[str]] = None) -> dict:
        """Main entry. Returns summary.

        Every source runs in its OWN browser + session, so a timeout, crash
        or expired session in one source can never stop the others. Sources
        can also run concurrently (PARALLEL_WORKERS > 1). This is the direct
        answer to the アシロボ problems the client described:
          ・ZOZOBOタイムアウト   → per-source retry with backoff + re-login
          ・1エラーで全停止       → full per-source isolation
          ・複数シナリオ同時不可  → optional parallel execution
        """
        summary: dict = {
            "run_id":      self.run_id,
            "target_date": self.target_date,
            "started_at":  datetime.now(timezone.utc).isoformat(),
            "results":     [],
        }
        sources_to_run = SOURCES if not only else [s for s in SOURCES if s.name in only]
        workers = max(1, min(PARALLEL_WORKERS, len(sources_to_run)))
        logger.info("Scraping %d sources for date %s (workers=%d, retries=%d)",
                    len(sources_to_run), self.target_date, workers, MAX_RETRIES_PER_SOURCE)

        if workers == 1:
            for src in sources_to_run:
                summary["results"].append(self._scrape_one_source(src))
        else:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futs = {pool.submit(self._scrape_one_source, s): s
                        for s in sources_to_run}
                for fut in as_completed(futs):
                    src = futs[fut]
                    try:
                        summary["results"].append(fut.result())
                    except Exception as exc:  # belt-and-braces: never let a worker kill the run
                        logger.exception("[%s] worker crashed: %s", src.name, exc)
                        summary["results"].append({
                            "name": src.name, "label": src.label,
                            "status": "failed", "error": f"worker crashed: {exc}"[:300],
                            "started_at": datetime.now(timezone.utc).isoformat(),
                            "finished_at": datetime.now(timezone.utc).isoformat(),
                        })

        summary["finished_at"] = datetime.now(timezone.utc).isoformat()
        ok   = sum(1 for r in summary["results"] if r["status"] == "ok")
        fail = len(summary["results"]) - ok
        logger.info("=" * 60)
        logger.info("DONE: %d ok / %d failed", ok, fail)
        for r in summary["results"]:
            mark = "✓" if r["status"] == "ok" else "✗"
            logger.info("  %s %-25s %s", mark, r["name"], r.get("error", "")[:80])
        return summary

    def _scrape_one_source(self, src: SourceConfig) -> dict:
        """Fully self-contained: own Playwright, browser, context, session.

        Retries the whole source (login + download) up to
        MAX_RETRIES_PER_SOURCE times with exponential backoff. A failure or
        hang here is contained to this one source.
        """
        # Looker needs a different browser context (stealth args, custom UA,
        # cross-origin iframes) that the regular context can't provide.
        if src.strategy == "looker_performance":
            return self._run_looker_source(src)

        last_err = "unknown"
        for attempt in range(1, MAX_RETRIES_PER_SOURCE + 1):
            try:
                with tempfile.TemporaryDirectory() as tmpdir:
                    download_dir = Path(tmpdir)
                    with sync_playwright() as p:
                        # Stealth flags: ZOZO BO (≈2026-06-15〜) はヘッドレス自動
                        # ブラウザのデータ画面アクセスを「タイムアウト」で弾く。
                        # performance スクレイパーと同じ自動検知回避フラグを付与。
                        browser = p.chromium.launch(
                            headless=self.headless,
                            args=[
                                "--no-sandbox",
                                "--disable-blink-features=AutomationControlled",
                                "--disable-features=IsolateOrigins,site-per-process",
                                "--disable-web-security",
                            ])
                        try:
                            context = self._new_context(browser)
                            page = context.new_page()
                            self._login(page)
                            result = self._download_source(context, page, src, download_dir)
                        finally:
                            browser.close()
                if result["status"] == "ok":
                    if attempt > 1:
                        result["retried"] = attempt
                    self._log_run(src, result)
                    return result
                last_err = result.get("error", "download failed")
            except Exception as exc:
                last_err = str(exc)
                logger.warning("[%s] attempt %d/%d failed: %s",
                               src.name, attempt, MAX_RETRIES_PER_SOURCE, str(exc)[:160])

            if attempt < MAX_RETRIES_PER_SOURCE:
                backoff = RETRY_BACKOFF_BASE_SEC * (2 ** (attempt - 1))
                logger.info("[%s] retrying in %.0fs...", src.name, backoff)
                time.sleep(backoff)

        result = {
            "name": src.name, "label": src.label, "status": "failed",
            "error": f"failed after {MAX_RETRIES_PER_SOURCE} attempts: {last_err}"[:300],
            "started_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }
        self._log_run(src, result)
        return result

    def _new_context(self, browser) -> BrowserContext:
        return browser.new_context(
            accept_downloads=True,
            locale="ja-JP",
            viewport={"width": 1440, "height": 900},
            # 実ブラウザの UA を名乗る (自動操作検知でデータ画面が timeout する対策)
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"),
            http_credentials={"username": self.basic_user, "password": self.basic_pw},
        )

    # ── Authentication ────────────────────────────────────────────────────────

    def _login(self, page: Page) -> None:
        logger.info("Logging in...")
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)

        # Sometimes the page already shows the dashboard if cookies are valid;
        # only fill if login form is visible
        if page.locator('input[name="LoginName"]').count() > 0:
            page.fill('input[name="LoginName"]', self.login_id)
            page.fill('input[name="Password"]', self.password)
            with page.expect_navigation(wait_until="domcontentloaded", timeout=30_000):
                page.get_by_role("button", name="ログイン").first.click()

        if "main" not in page.url.lower() and "default" not in page.url.lower():
            raise RuntimeError(f"Login failed — landed on {page.url}")
        logger.info("Login OK: %s", page.url)

    def _ensure_logged_in(self, page: Page) -> None:
        """Re-login if session expired."""
        if is_session_expired(page):
            logger.warning("Session expired, re-logging in...")
            self._login(page)

    # ── Per-source download ───────────────────────────────────────────────────

    def _download_source(self, context: BrowserContext, page: Page,
                         src: SourceConfig, download_dir: Path) -> dict:
        result = {
            "name":       src.name,
            "label":      src.label,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "status":     "pending",
        }
        logger.info("─" * 60)
        logger.info("[%s] %s", src.name, src.label)

        try:
            # Navigate to the page
            full_url = f"{BASE_URL}{src.page_url}"
            logger.info("   GET %s", full_url)
            page.goto(full_url, wait_until="domcontentloaded", timeout=30_000)
            time.sleep(1.5)

            self._ensure_logged_in(page)

            # Check for 404
            if "404" in page.title():
                raise RuntimeError(f"Page not found: {full_url}")

            # Apply filters
            if src.apply_filters:
                try:
                    src.apply_filters(page, self.target_date)
                    time.sleep(1.0)
                except Exception as exc:
                    logger.warning("   filter apply failed (non-fatal): %s", exc)

            # Robust multi-strategy download (validates real CSV before accepting)
            local_path = self._robust_download(context, page, src, download_dir)

            size = local_path.stat().st_size
            gcs_path = f"uploads/{src.gcs_prefix}/{self.target_date}/{local_path.name}"
            self._upload_to_gcs(local_path, gcs_path)

            result.update({
                "status":     "ok",
                "filename":   local_path.name,
                "size_bytes": size,
                "gcs_path":   f"gs://{self.gcs_bucket}/{gcs_path}",
            })
            logger.info("   ✓ %s → gs://%s/%s (%s bytes)",
                        local_path.name, self.gcs_bucket, gcs_path, f"{size:,}")
        except Exception as exc:
            result.update({"status": "failed", "error": str(exc)[:300]})
            logger.error("   ✗ %s", exc)

        result["finished_at"] = datetime.now(timezone.utc).isoformat()
        return result

    # ── Download cascade ──────────────────────────────────────────────────────

    @staticmethod
    def _looks_like_csv(data: bytes) -> bool:
        if len(data) < 50:
            return False
        head = data[:300].lower()
        if b"<html" in head or b"<!doctype" in head or b"<head" in head:
            return False
        return True

    def _robust_download(self, context: BrowserContext, page: Page,
                         src: SourceConfig, download_dir: Path) -> Path:
        """Try every plausible download trigger until one yields real CSV.

        ZOZO BO exposes downloads inconsistently (direct endpoint, form
        submit, dropdown link, JS handler). Rather than hard-coding one
        brittle selector per page (the fragility that broke アシロボ), we try
        an ordered cascade and validate the bytes are CSV, not an HTML page.
        """
        errors: list[str] = []

        # Build the ordered list of attempts. Honour the configured primary
        # strategy first, then fall back to discovery.
        attempts: list[Callable[[], Path]] = []
        # Confirmed exact recipes go first — most reliable, no UI fragility.
        if src.strategy == "form_post" and src.post_template:
            attempts.append(lambda: self._dl_form_post(context, src, download_dir))
        if src.strategy == "sales_center":
            attempts.append(lambda: self._dl_sales_center(context, page, src, download_dir))
        if src.strategy == "goods_search":
            attempts.append(lambda: self._dl_goods_search(context, src, download_dir))
        # Submit the live data-page form (works for pages whose CSV depends on
        # server-rendered dynamic fields, e.g. StockAnalysis).
        attempts.append(lambda: self._dl_page_form_submit(page, src, download_dir))
        if src.download_url:
            attempts.append(lambda: self._dl_session_get(context, src, download_dir))
        # Harvest CSV hrefs from the DOM (works even when the link is hidden
        # in a dropdown menu) and fetch them with the authenticated session.
        attempts.append(lambda: self._dl_harvest_hrefs(context, page, src, download_dir))
        # ZOZO BO funnels most CSVs through a central async download center
        # (ManualDownLoad.asp): trigger generation, then collect the file there.
        attempts.append(lambda: self._dl_manual_center(context, page, src, download_dir))
        attempts.append(lambda: self._dl_click_discovered(page, src, download_dir))
        attempts.append(lambda: self._dl_click_selector(page, src.submit_button, src, download_dir))
        attempts.append(lambda: self._dl_click_selector(page, src.download_selector, src, download_dir))

        for attempt in attempts:
            try:
                path = attempt()
                data = path.read_bytes()
                if self._looks_like_csv(data):
                    return path
                errors.append(f"{getattr(attempt, '__name__', 'attempt')}: got HTML/empty")
            except PWTimeout as exc:
                errors.append(f"timeout: {str(exc)[:80]}")
            except Exception as exc:
                errors.append(str(exc)[:120])

        raise RuntimeError("no download strategy yielded CSV — " + " | ".join(errors)[:260])

    def _dl_page_form_submit(self, page: Page, src: SourceConfig,
                             download_dir: Path) -> Path:
        """Submit the data page's real list form (form1) with its live, server
        -rendered field state and capture the resulting CSV.

        Some ZOZO pages (StockAnalysis) only return CSV when the form is
        submitted with the exact dynamic fields the page rendered (csrf-like
        tokens, default radio states). A static replay returns the HTML form
        again, so we drive the actual page instead.
        """
        # Select all-shops if such a control exists (best effort).
        try:
            page.evaluate("""() => {
              for (const s of document.querySelectorAll("select[name='ShopID']")) {
                if ([...s.options].some(o => o.value === '-1')) s.value = '-1';
              }
            }""")
        except Exception:
            pass

        captured: list[bytes] = []
        cap_name = {"fn": src.filename_default}

        def on_resp(resp):
            try:
                ct = (resp.headers.get("content-type") or "").lower()
                cd = (resp.headers.get("content-disposition") or "").lower()
                if ("csv" in ct or "excel" in ct or "attachment" in cd
                        or "octet-stream" in ct):
                    body = resp.body()
                    if self._looks_like_csv(body):
                        captured.append(body)
                        if "filename=" in cd:
                            cap_name["fn"] = cd.split("filename=")[-1].strip('"; ').replace("/", "")
            except Exception:
                pass

        page.on("response", on_resp)
        try:
            btn = page.locator(
                "form[name='form1'] button[type='submit'], "
                "form[name='form1'] input[type='submit'], "
                "button[name='search'], button:has-text('ダウンロード'), "
                "input[type='submit'][value*='ダウンロード']")
            if btn.count() == 0:
                raise RuntimeError("no form1 submit button")
            # Prefer a real download event; fall back to captured response.
            try:
                with page.expect_download(timeout=90_000) as di:
                    btn.first.click(force=True, no_wait_after=True, timeout=15_000)
                return self._save_download(di.value, src, download_dir)
            except PWTimeout:
                pass
            deadline = time.time() + 90
            while time.time() < deadline and not captured:
                time.sleep(2)
            if captured:
                path = download_dir / cap_name["fn"]
                path.write_bytes(captured[0])
                return path
            raise RuntimeError("form1 submit produced no CSV")
        finally:
            try:
                page.remove_listener("response", on_resp)
            except Exception:
                pass

    def _dl_form_post(self, context: BrowserContext, src: SourceConfig,
                      download_dir: Path) -> Path:
        """Replay the exact CSV-generating POST with the authenticated session.

        Most robust path: no clicking, no visibility/dropdown issues — just
        the same form submission the browser makes, captured from the live
        site. {D} → URL-encoded target date (YYYY%2FMM%2FDD).
        """
        d_enc = self.target_date.replace("-", "%2F")  # 2026-05-14 → 2026%2F05%2F14
        body = src.post_template.replace("{D}", d_enc)
        resp = context.request.post(
            src.post_url, data=body, timeout=180_000,
            headers={"content-type": "application/x-www-form-urlencoded",
                     "referer": src.post_url})
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} POST {src.post_url}")
        cd = resp.headers.get("content-disposition", "")
        fn = src.filename_default
        if "filename=" in cd:
            fn = cd.split("filename=")[-1].strip('"; ').replace("/", "")
        path = download_dir / fn
        path.write_bytes(resp.body())
        return path

    # User's 7 ZOZO shops (from goods_deep.html: user_shops_id hidden field).
    # 登録商品 search rejects ShopID=0/-1/empty → must loop these explicitly.
    GOODS_SHOPS: list[tuple[str, str]] = [
        ("MONO-MART",    "1787"),
        ("EMMA CLOTHES", "2031"),
        ("Chaco closet", "2258"),
        ("ADRER",        "2395"),
        ("anown",        "2524"),
        ("Anchor Smith", "2525"),
        ("BONLECILL",    "2710"),
    ]

    def _dl_goods_search(self, context: BrowserContext, src: SourceConfig,
                         download_dir: Path) -> Path:
        """登録商品 SKU単位 — loop 7 shops, concatenate CSVs (header once).

        Per-shop recipe (validated 2026-05-20):
          POST GoodsSearch.asp  c=Search&Shelf=shop&MallID=1&ShopID={id}
              &SCategoryPID=0&SCategoryID=0&SelectTagBrandName=
              &SearchTagBrandID=&GoodsCode=&TypeCategoryID=0&TypeID=0
              &GoodsName=&GoodsData2=&CustomerTypeID=0&StockType=0&Stock=0
              &ExternalStockType=0&ExternalStock=0&ShowWebFlag=0&SellType=0
              &GoodsDetailID=&PriceFrom=&PriceTo=&SellStartDTFrom=&SellStartDTTo=
              &RegistDTFrom=&RegistDTTo=&OrderBy=1&Top=1&SearchDb=1&search=SEARCH
          GET  GoodsSearch.asp?c=ListDownLoadCS  →  Application/vnd.ms-excel-csv

        Combined size ~395 MB across 7 shops; output stays Shift-JIS (cp932)
        like the other ZOZO BO CSVs — downstream parser already handles it.
        """
        first_header: bytes | None = None
        parts: list[bytes] = []
        per_shop_sizes: list[str] = []

        for label, shop_id in self.GOODS_SHOPS:
            body = (
                f"c=Search&Shelf=shop&MallID=1&ShopID={shop_id}"
                f"&SCategoryPID=0&SCategoryID=0&SelectTagBrandName="
                f"&SearchTagBrandID=&GoodsCode=&TypeCategoryID=0&TypeID=0"
                f"&GoodsName=&GoodsData2=&CustomerTypeID=0&StockType=0&Stock=0"
                f"&ExternalStockType=0&ExternalStock=0&ShowWebFlag=0&SellType=0"
                f"&GoodsDetailID=&PriceFrom=&PriceTo=&SellStartDTFrom=&SellStartDTTo="
                f"&RegistDTFrom=&RegistDTTo=&OrderBy=1&Top=1&SearchDb=1&search=SEARCH"
            )
            sr = context.request.post(
                src.post_url, data=body, timeout=120_000,
                headers={"content-type": "application/x-www-form-urlencoded",
                         "referer": src.post_url + "?c=Init"})
            if sr.status != 200:
                raise RuntimeError(
                    f"goods_search POST shop={shop_id} HTTP {sr.status}")
            gr = context.request.get(
                src.post_url + "?c=ListDownLoadCS", timeout=300_000,
                headers={"referer": src.post_url})
            ct = (gr.headers.get("content-type") or "").lower()
            if "csv" not in ct and "excel" not in ct:
                raise RuntimeError(
                    f"goods_search shop={shop_id} unexpected ct={ct[:60]}")
            data = gr.body()
            per_shop_sizes.append(f"{label}={len(data):,}B")
            # Strip header on rows 2..N; keep the first shop's header.
            if first_header is None:
                first_header = data
                parts.append(data)
            else:
                # Drop the first line (CSV header) for subsequent shops.
                # ZOZO BO uses \r\n line endings.
                idx = data.find(b"\r\n")
                parts.append(data[idx + 2:] if idx >= 0 else data)

        merged = b"".join(parts)
        logger.info("   goods_search: merged %d shops → %d bytes (per-shop: %s)",
                    len(parts), len(merged), ", ".join(per_shop_sizes))
        path = download_dir / src.filename_default
        path.write_bytes(merged)
        return path

    # Same 7 ZOZO shops as goods_search. Looker filter is mandatory and
    # single-select → loop per shop, concatenate TSVs (header kept once).
    LOOKER_SHOPS: list[tuple[str, str]] = [
        ("MONO-MART",    "1787"),
        ("EMMA CLOTHES", "2031"),
        ("Chaco closet", "2258"),
        ("ADRER",        "2395"),
        ("anown",        "2524"),
        ("Anchor Smith", "2525"),
        ("BONLECILL",    "2710"),
    ]

    def _run_looker_source(self, src: SourceConfig) -> dict:
        """商品別実績(新) Looker dashboard → per-shop TSV download → GCS.

        The Looker iframe (toreportprd.cloud.looker.com) refuses to load
        without specific bot-detection workarounds. We use a dedicated
        browser/context for this source rather than the shared one.

        Flow per shop (validated 2026-05-20 on MONO-MART):
          1. LookerDashboards.asp → click 商品別実績(新) link
          2. Wait for the embedded dashboard iframe to populate (~30-60s)
          3. Click the "ショップ名" filter chip (span[role=button] with
             text "値は必須です" the first time)
          4. Type shop name into popover input
          5. Click the matching [role=option]
          6. Click 「更新」 to apply
          7. Wait for the tile to render with data
          8. Click "タイルの操作" (kebab)
          9. Click 「データをダウンロード」
         10. Click ダウンロード button, capture file
         11. Concatenate per-shop TSVs (keep header once)
        """
        from datetime import datetime as _dt
        result: dict = {
            "name": src.name, "label": src.label,
            "started_at": _dt.now(timezone.utc).isoformat(),
            "shops_ok": [], "shops_failed": [],
        }
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                download_dir = Path(tmpdir)
                merged: list[bytes] = []
                first_header_seen = False
                with sync_playwright() as p:
                    browser = p.chromium.launch(
                        headless=self.headless,
                        args=[
                            "--no-sandbox",
                            "--disable-blink-features=AutomationControlled",
                            "--disable-features=IsolateOrigins,site-per-process",
                            "--disable-web-security",
                        ])
                    try:
                        context = browser.new_context(
                            locale="ja-JP",
                            viewport={"width": 1920, "height": 1200},
                            accept_downloads=True,
                            user_agent=(
                                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                "AppleWebKit/537.36 (KHTML, like Gecko) "
                                "Chrome/131.0.0.0 Safari/537.36"),
                            http_credentials={"username": self.basic_user,
                                              "password": self.basic_pw})
                        context.add_init_script(
                            "Object.defineProperty(navigator,'webdriver',"
                            "{get:()=>undefined});window.chrome={runtime:{}};")
                        page = context.new_page()
                        self._login(page)

                        # Pick the per-shop loop OR a single "ALL" pass
                        # depending on whether the dashboard requires a shop
                        # filter or has a dedicated DL tile.
                        shop_iter = ([("ALL", "ALL")]
                                     if src.looker_skip_shop_filter
                                     else self.LOOKER_SHOPS)

                        for shop_name, _shop_id in shop_iter:
                            logger.info("   looker: shop=%s", shop_name)
                            try:
                                shop_file = self._dl_looker_one_shop(
                                    page, shop_name, src, download_dir)
                                data = shop_file.read_bytes()
                                if not first_header_seen:
                                    merged.append(data)
                                    first_header_seen = True
                                else:
                                    nl = data.find(b"\n")
                                    merged.append(data[nl + 1:] if nl >= 0 else data)
                                result["shops_ok"].append(
                                    {"shop": shop_name, "bytes": len(data)})
                            except Exception as e:
                                logger.warning("   looker shop=%s FAILED: %s",
                                               shop_name, str(e)[:120])
                                result["shops_failed"].append(
                                    {"shop": shop_name, "err": str(e)[:200]})
                                try:
                                    page.goto(BASE_URL + "LookerDashboards.asp",
                                              wait_until="networkidle",
                                              timeout=45_000)
                                except Exception:
                                    pass
                    finally:
                        browser.close()

                if not merged:
                    raise RuntimeError("all shops failed to download")

                merged_bytes = b"".join(merged)
                local_path = download_dir / src.filename_default
                local_path.write_bytes(merged_bytes)

                gcs_path = (f"uploads/{src.gcs_prefix}/{self.target_date}/"
                            f"{src.filename_default}")
                bkt = storage.Client().bucket(self.gcs_bucket)
                bkt.blob(gcs_path).upload_from_filename(
                    str(local_path), content_type="text/tab-separated-values")
                result.update({
                    "status": "ok",
                    "gcs_path": f"gs://{self.gcs_bucket}/{gcs_path}",
                    "bytes": len(merged_bytes),
                    "shops": len(result["shops_ok"]),
                })
                logger.info("   ✓ looker merged %d shops → gs://%s/%s "
                            "(%s bytes)",
                            len(result["shops_ok"]), self.gcs_bucket, gcs_path,
                            f"{len(merged_bytes):,}")
        except Exception as e:
            result["status"] = "failed"
            result["error"] = str(e)[:300]
            logger.error("   ✗ looker source failed: %s", str(e)[:200])
        result["finished_at"] = datetime.now(timezone.utc).isoformat()
        self._log_run(src, result)
        return result

    def _dl_looker_one_shop(self, page: "Page", shop_name: str,
                            src: SourceConfig, download_dir: Path) -> Path:
        """Single-shop download flow inside the Looker iframe.

        Modes:
          (a) Default: per-shop filter, then click the SINGLE tile kebab —
              used for 商品別実績(新) where the whole dashboard IS one table.
          (b) skip_shop_filter + tile_label: download a SPECIFIC named tile
              (e.g. '日別検索キーワードTOP20_DL用') from a multi-tile dashboard,
              ignoring the per-shop loop.
        """
        link_text = src.looker_link_text or "商品別実績(新)"
        # Open the dashboard
        page.goto(BASE_URL + "LookerDashboards.asp",
                  wait_until="networkidle", timeout=45_000)
        time.sleep(3)
        page.get_by_role("link", name=link_text).first.click(timeout=10_000)
        page.wait_for_load_state("networkidle", timeout=60_000)

        # Wait for the embedded-dashboard iframe to attach. Looker iframes
        # are flaky to load (~30% retry rate); allow up to 5 min and reload
        # the dashboard once if nothing shows up after 3 min.
        dash = None
        for attempt_i in range(2):
            for _ in range(36):  # up to 180s per attempt
                time.sleep(5)
                for f in page.frames:
                    if "embed/dashboards/" in (f.url or ""):
                        dash = f
                        break
                if dash:
                    break
            if dash:
                break
            # Reload the dashboard page once to retry iframe attachment
            logger.warning("   looker iframe missing after 180s, reloading once")
            try:
                page.reload(wait_until="networkidle", timeout=60_000)
                time.sleep(5)
            except Exception:
                pass
        if not dash:
            raise RuntimeError("Looker dashboard iframe never appeared")
        # Wait for content
        for _ in range(12):
            time.sleep(5)
            try:
                n = dash.evaluate(
                    "()=>document.body?document.body.innerText.length:0")
                if n and n > 200:
                    break
            except Exception:
                pass

        # 日付フィルタを「最後7日間」に（既定の前週だと最新日が取れない・顧客2026）。
        # 商品別実績(has_2day_lag)で適用。失敗時は既定のまま続行（非致命）。
        if src.has_2day_lag:
            ok = set_looker_date_last7(dash)
            logger.info("   looker date filter -> 最後7日間: %s", ok)

        # ── Tab navigation (rpid=9 App/PC-SP(ショップ親カテゴリ) etc.) ──
        # Looker tabs live in the EXTENSION iframe, not the dashboard iframe.
        # Clicking a tab in the extension causes Looker to swap the dashboard
        # iframe (URL changes from ::dashboard_N to ::dashboard_M). After the
        # click we re-find the dashboard frame and refresh `dash`.
        if src.looker_tab_label:
            ext = None
            for f in page.frames:
                if "extensions.cloud.looker.com/project-resource" in (f.url or ""):
                    ext = f
                    break
            if not ext:
                raise RuntimeError("extension iframe not found (no tabs visible)")
            # Capture the INITIAL dashboard URL *before* the click so we can
            # detect the swap. After Looker swaps the iframe, `dash` becomes
            # detached and its .url may return stale or empty values.
            try:
                initial_dash_url = dash.url
            except Exception:
                initial_dash_url = ""
            logger.info("   looker: pre-tab dash url=%s", initial_dash_url[:100])
            click_res = ext.evaluate(r"""(target) => {
              for (const b of document.querySelectorAll('button')) {
                const text = (b.innerText || '').replace(/\s+/g,' ').trim();
                if (text === target) {
                  b.scrollIntoView({block: 'center'});
                  b.click();
                  return true;
                }
              }
              return false;
            }""", src.looker_tab_label)
            if not click_res:
                raise RuntimeError(
                    f"tab '{src.looker_tab_label}' not found in extension")
            logger.info("   looker: clicked tab '%s', waiting for swap",
                        src.looker_tab_label)
            # Wait for the dashboard frame to swap. Strategy:
            #   1) Pick whichever embed/dashboards frame is present and has
            #      content (>200 chars) — the swap usually leaves only the
            #      new frame attached.
            #   2) Verify its URL differs from the pre-click URL.
            # If after 4 min no swap is detected, log all current frame URLs
            # for diagnosis and raise.
            # Wait up to 10 min for the new dashboard frame to attach +
            # render initial content. Looker behaviour is highly variable —
            # sometimes 5s, sometimes 7+ min. Poll every 3s and log every
            # iteration so we can see the swap as it happens. Also re-click
            # the tab once at the 3-min mark in case the first click was
            # lost (no event fired in the extension).
            new_dash = None
            re_clicked = False
            for itr in range(200):  # 200 × 3s = 600s = 10 min
                time.sleep(3)
                dash_frames = [f for f in page.frames
                               if "embed/dashboards/" in (f.url or "")]
                # Re-click once around the 3-min mark if no swap detected
                if itr == 60 and not new_dash and not re_clicked:
                    logger.info("   looker: no swap after 3min — re-clicking tab")
                    try:
                        ext.evaluate(r"""(target) => {
                          for (const b of document.querySelectorAll('button')) {
                            if ((b.innerText || '').replace(/\s+/g,' ').trim() === target) {
                              b.click(); return true;
                            }
                          }
                          return false;
                        }""", src.looker_tab_label)
                        re_clicked = True
                    except Exception as exc:
                        logger.warning("   looker: re-click failed: %s", exc)
                if dash_frames and itr % 10 == 0:
                    logger.info("   looker: t≈%ds dash_frames=%s",
                                (itr + 1) * 3,
                                [(f.url.split("::")[-1].split("?")[0],
                                  _safe_body_len(f))
                                 for f in dash_frames])
                for f in dash_frames:
                    if f.url == initial_dash_url:
                        continue
                    body_len = _safe_body_len(f)
                    if body_len > 100:
                        new_dash = f
                        break
                if new_dash:
                    break
            if not new_dash:
                # Diagnostic dump
                logger.error("   tab swap timeout — all frame URLs follow:")
                for f in page.frames:
                    try:
                        b = f.evaluate(
                            "() => document.body ? document.body.innerText.length : 0")
                    except Exception:
                        b = -1
                    logger.error("     body_len=%s url=%s", b, (f.url or "")[:150])
                raise RuntimeError(
                    f"dashboard did not swap after clicking tab "
                    f"'{src.looker_tab_label}'")
            dash = new_dash
            logger.info("   looker: swap complete → %s", dash.url[:120])
            # Allow tiles in the new tab to render
            time.sleep(15)

        # ── Shop filter (skip for dashboards where ショップ is optional) ──
        if not src.looker_skip_shop_filter:
            chip = dash.locator(
                'span[data-testid="filter-token"][role="button"]'
                ':has-text("値は必須です")')
            if chip.count() == 0:
                chip = dash.locator('span[data-testid="filter-token"][role="button"]')
            chip.first.click(timeout=10_000)
            time.sleep(2)

            inp = dash.locator("input[type='text']:visible").first
            inp.fill(shop_name, timeout=5_000)
            time.sleep(1.5)
            dash.locator(f'[role="option"]:has-text("{shop_name}")').first.click(
                timeout=5_000)
            time.sleep(1)

            for sel in ("button:has-text('更新')", "button:has-text('適用')"):
                try:
                    loc = dash.locator(sel)
                    if loc.count() > 0 and loc.first.is_visible():
                        loc.first.click(timeout=3_000)
                        break
                except Exception:
                    continue
            time.sleep(30)
        else:
            # No per-shop filter to set — just let the dashboard render
            time.sleep(20)

        # ── Multi-select all 7 shops + click dashboard-level「ダウンロード」 ──
        # Used for rpid=9 App/PC-SP(ショップ親カテゴリ) tabs where the DL link
        # lives in the dashboard action menu (top-right ⋮) rather than on a
        # tile kebab. Pre-req: tab swap done, dashboard rendered.
        if src.looker_use_dashboard_dl:
            logger.info("   looker: opening required filter (multi-select)")
            # Click the first chip whose text is「値は必須です」(the required
            # filter — could be ショップ名 OR ショップ親カテゴリ名 etc. depending
            # on the active tab). Skip date chips (have "前週" / "週" etc.).
            opened = dash.evaluate(r"""() => {
              const tokens = [...document.querySelectorAll('[data-testid="filter-token"]')];
              // Pass 1: explicit「値は必須です」 chip
              for (const t of tokens) {
                const txt = (t.innerText || '').replace(/\s+/g,' ').trim();
                if (txt === '値は必須です') {
                  t.scrollIntoView({block:'center'});
                  t.click();
                  return true;
                }
              }
              // Pass 2: any chip that's not the date one
              for (const t of tokens) {
                const txt = (t.innerText || '').replace(/\s+/g,' ').trim();
                if (txt.startsWith('前週') || txt.startsWith('週') ||
                    /日付/.test(txt)) continue;
                t.scrollIntoView({block:'center'});
                t.click();
                return true;
              }
              return false;
            }""")
            if not opened:
                raise RuntimeError("required filter chip not found")
            time.sleep(4)

            # Select all 7 shop options. role=option toggles the checkbox.
            selected_count = dash.evaluate(r"""() => {
              const opts = [...document.querySelectorAll('[role="option"]')];
              let count = 0;
              for (const o of opts) {
                const checked = o.getAttribute('aria-selected') === 'true' ||
                  o.querySelector('input[type="checkbox"]')?.checked || false;
                if (!checked) {
                  o.click();
                  count++;
                }
              }
              return count;
            }""")
            logger.info("   looker: selected %d shop option(s)", selected_count)
            time.sleep(2)

            # Click「完了」(or 適用) to apply
            applied = dash.evaluate(r"""() => {
              for (const b of document.querySelectorAll('button')) {
                if (b.offsetParent === null) continue;
                const t = (b.innerText || '').trim();
                if (t === '完了' || t === '適用' || t === '更新') {
                  b.click(); return t;
                }
              }
              return null;
            }""")
            logger.info("   looker: apply button clicked = %s", applied)
            # Allow the dashboard to start re-rendering after filter apply.
            time.sleep(30)
            # Re-locate the dashboard frame (Looker may have swapped it).
            for f in page.frames:
                if "embed/dashboards/" in (f.url or "") and "_6_ga4" in f.url:
                    if _safe_body_len(f) > 200:
                        dash = f
                        break
            # The「ダッシュボード アクション」kebab is actually a <button> whose
            # accessible name comes from an inner `.VisuallyHidden` div
            # (NOT from an aria-label attribute), AND it has
            # data-isvisible="false" until the user hovers over the dash-
            # board toolbar. Click via JS evaluate (force-bypasses the
            # visibility check) and immediately probe for the menu.
            logger.info("   looker: triggering ダッシュボード アクション menu")
            dl_clicked = False
            for attempt in range(8):  # up to ~80s
                # Click the button via JS — find it by inner-text search
                kebab_clicked = dash.evaluate(r"""() => {
                  for (const b of document.querySelectorAll('button')) {
                    if ((b.innerText || '').includes('ダッシュボード アクション')) {
                      b.scrollIntoView({block: 'center'});
                      // Force the visibility flag in case it's data-driven
                      b.setAttribute('data-isvisible', 'true');
                      b.click();
                      return true;
                    }
                  }
                  return false;
                }""")
                if not kebab_clicked:
                    logger.warning("   kebab not located on attempt %d", attempt + 1)
                    time.sleep(4)
                    continue
                # Poll for menu items
                for _ in range(20):  # up to 10s
                    time.sleep(0.5)
                    items = dash.evaluate(r"""() => {
                      return [...document.querySelectorAll(
                          '[role=menuitem],[role=menuitemradio],li[role]')]
                        .map(e => (e.innerText || '').replace(/\s+/g,' ').trim())
                        .filter(t => t).slice(0, 20);
                    }""")
                    if items:
                        logger.info("   looker: dashboard menu items: %s",
                                    items[:8])
                        # Use Playwright's locator+click to send real
                        # pointer events (React handlers may ignore .click())
                        try:
                            dl_menuitem = dash.locator(
                                '[role=menuitem]:has-text("ダウンロード"), '
                                'li[role]:has-text("ダウンロード")').first
                            dl_menuitem.click(timeout=10_000, force=True)
                            dl_clicked = True
                        except Exception as exc:
                            logger.warning(
                                "   locator click on ダウンロード failed: %s",
                                exc)
                            # Fallback: try keyboard shortcut
                            try:
                                page.keyboard.press("Alt+Shift+KeyD")
                                dl_clicked = True
                                logger.info(
                                    "   fell back to Alt+Shift+D shortcut")
                            except Exception:
                                pass
                        break
                if dl_clicked:
                    break
                logger.info("   attempt %d: menu empty, retry", attempt + 1)
                time.sleep(3)
            if not dl_clicked:
                raise RuntimeError(
                    "dashboard 'ダウンロード' menu item not found after "
                    "ダッシュボード アクション kebab triggered")

            # Wait for the dashboard-DL modal to fully render
            time.sleep(8)

            # Modal default format is PDF — change to CSV so we get a
            # parseable text export. Client confirmed flow (2026-06-09):
            #   フォーマット選択 → 高度なデータオプション → すべての結果
            # The expand-tables checkbox (高度なデータオプション/含める行数)
            # ensures the export includes ALL rows, not just the visible page.
            try:
                dash.evaluate(r"""() => {
                  const inp = document.querySelector('input[name="formatOption"]');
                  if (inp) { inp.click(); inp.focus(); }
                }""")
                time.sleep(2)
                sel_fmt = dash.evaluate(r"""() => {
                  for (const o of document.querySelectorAll('[role=option]')) {
                    const t = (o.innerText || '').trim();
                    if (t === 'CSV') { o.click(); return 'CSV'; }
                  }
                  for (const o of document.querySelectorAll('[role=option]')) {
                    const t = (o.innerText || '').trim();
                    if (t === 'TSV' || t === 'テキスト') { o.click(); return t; }
                  }
                  return null;
                }""")
                logger.info("   looker: format selected = %s", sel_fmt)
                time.sleep(2)
                # Check expand-tables for「すべての結果」(all rows)
                exp_result = dash.evaluate(r"""() => {
                  const cb = document.querySelector('input[name="expandTablesCheck"]');
                  if (cb && !cb.checked) {
                    cb.click();
                    cb.dispatchEvent(new Event('change', {bubbles: true}));
                    return 'checked';
                  }
                  return cb ? 'already-checked' : 'no-checkbox';
                }""")
                logger.info("   looker: expandTables = %s", exp_result)
                time.sleep(1)
            except Exception as exc:
                logger.warning("   format/options failed: %s", exc)

            # Click the dialog's ダウンロード button. Looker streams the
            # generated file as a real download event when format != PDF.
            with page.expect_download(timeout=300_000) as info:
                btn = dash.locator(
                    '[role=dialog] button:text-is("ダウンロード"), '
                    '[role=alertdialog] button:text-is("ダウンロード")')
                if btn.count() == 0:
                    raise RuntimeError("dialog ダウンロード button not found")
                btn.first.scroll_into_view_if_needed(timeout=5_000)
                time.sleep(0.5)
                btn.first.click(timeout=15_000, force=True)
                logger.info(
                    "   looker: clicked final ダウンロード, awaiting download")
            dl = info.value
            safe = shop_name.replace(" ", "_").replace("/", "_")
            out_path = download_dir / f"{safe}_{dl.suggested_filename}"
            dl.save_as(str(out_path))
            # Dashboard-level DL returns a ZIP archive with one CSV per
            # tile (e.g., "dashboard-app(新)(ショップ親カテゴリ)/アクセス実績_app_dl用.csv").
            # Extract the target tile's CSV (looker_tile_label matches the
            # CSV filename case-insensitively after stripping spaces).
            import zipfile
            if zipfile.is_zipfile(out_path):
                # Normalize both sides: spaces → '', `/` → `_`, lowercase.
                # Looker replaces `/` with `_` in ZIP filenames so the tile
                # `アクセス実績_PC/SP_DL用` becomes `アクセス実績_pc_sp_dl用.csv`.
                def _norm(s: str) -> str:
                    return s.replace(" ", "").replace("/", "_").lower()
                wanted = (_norm(src.looker_tile_label)
                          if src.looker_tile_label else "")
                with zipfile.ZipFile(out_path) as z:
                    target_data = None
                    target_name = None
                    members = z.namelist()
                    # Pass 1: exact tile_label match
                    for name in members:
                        base = name.split("/")[-1]
                        if wanted and wanted in _norm(base):
                            with z.open(name) as f:
                                target_data = f.read()
                            target_name = base
                            break
                    # Pass 2 (fallback): pick the LARGEST CSV — the "DL用"
                    # tile is the wide one with bulk data.
                    if not target_data:
                        # Pick the largest .csv member
                        best = None
                        for info in z.infolist():
                            if info.filename.lower().endswith(".csv"):
                                if not best or info.file_size > best.file_size:
                                    best = info
                        if best:
                            with z.open(best.filename) as f:
                                target_data = f.read()
                            target_name = best.filename.split("/")[-1]
                            logger.info(
                                "   looker: tile_label '%s' not found — "
                                "fell back to largest CSV '%s' (%d bytes)",
                                src.looker_tile_label, target_name,
                                best.file_size)
                    if target_data:
                        csv_path = download_dir / f"{safe}_{target_name}"
                        csv_path.write_bytes(target_data)
                        logger.info(
                            "   looker: extracted %s from ZIP (%d bytes)",
                            target_name, len(target_data))
                        return csv_path
                    logger.warning(
                        "   looker: no CSV found in ZIP — files: %s",
                        [n.split("/")[-1] for n in members][:10])
            return out_path

        # ── Scroll target tile into view first, then click its kebab ──
        if src.looker_tile_label:
            kebab_sel = (f"button[aria-label*='タイルの操作']"
                         f"[aria-label*='{src.looker_tile_label}']")
            kebab = dash.locator(kebab_sel)
            if kebab.count() == 0:
                raise RuntimeError(
                    f"tile '{src.looker_tile_label}' not found in dashboard")
        else:
            kebab = dash.locator("button[aria-label*='タイルの操作']")
            if kebab.count() == 0:
                raise RuntimeError("kebab (タイルの操作) not found")
        # Looker tile-action buttons are hidden by default (data-isvisible="false")
        # and only render their popup menu when triggered after hover. Scroll +
        # hover + click is the reliable sequence.
        try:
            kebab.first.scroll_into_view_if_needed(timeout=5_000)
            time.sleep(1)
            # Hover the parent tile so the kebab becomes interactive
            kebab.first.hover(timeout=5_000)
            time.sleep(1)
        except Exception:
            pass
        kebab.first.click(timeout=10_000, force=True)
        time.sleep(4)
        # Debug aid: dump current popup menu items
        try:
            menu_items = dash.evaluate(r"""()=>{
              const norm=s=>(s==null?'':String(s)).replace(/\s+/g,' ').trim();
              return [...document.querySelectorAll('[role=menuitem],[role=menuitemradio],li[role],a[role]')]
                .map(e=>norm(e.innerText||''))
                .filter(t=>t).slice(0,20);
            }""")
            logger.info("   looker popup items: %s", menu_items)
        except Exception:
            pass

        # Click データをダウンロード
        dl_item = dash.locator("text='データをダウンロード'").first
        if dl_item.count() == 0:
            raise RuntimeError("『データをダウンロード』menu item not found")
        dl_item.click(timeout=5_000)
        time.sleep(4)

        # Modal: expand 高度なデータオプション if collapsed, then check
        # すべての結果 (client requirement).
        for adv_sel in ("text='高度なデータ オプション'",
                        "text='高度なデータオプション'",
                        "button:has-text('高度なデータ')"):
            try:
                adv = dash.locator(adv_sel).first
                if adv.count() > 0 and adv.is_visible():
                    adv.click(timeout=3_000)
                    time.sleep(1)
                    break
            except Exception:
                continue
        # Now click すべての結果
        for sel in ("text='すべての結果'",
                    "label:has-text('すべての結果')",
                    "input[type='radio'][value*='all'i]"):
            try:
                ar = dash.locator(sel).first
                if ar.count() > 0 and ar.is_visible():
                    ar.click(timeout=3_000)
                    time.sleep(1)
                    break
            except Exception:
                continue

        # Format choice — for dashboards where the export modal opens with
        # no format pre-selected, the download button stays disabled until
        # the user clicks one. 商品別実績(新) had it pre-set; 検索キーワード経由
        # / アクセス実績(新) do not. Try clicking the "TSV" / "CSV" / "テキスト"
        # option, then fall back to the first visible format radio.
        for fmt_sel in (
            "label:has-text('TSV')",
            "label:has-text('テキスト')",
            "label:has-text('CSV')",
            "input[type='radio'][value='txt']",
            "input[type='radio'][value='csv']",
        ):
            try:
                fm = dash.locator(fmt_sel).first
                if fm.count() > 0 and fm.is_visible():
                    fm.click(timeout=3_000)
                    time.sleep(1)
                    break
            except Exception:
                continue

        # Click ダウンロード button + capture. Prefer the modal's specific
        # download button ID (qr-export-modal-download) — much more reliable
        # than text-based matching when multiple ダウンロード buttons exist.
        # Wait for the button to become enabled (Looker disables it until a
        # format is chosen).
        for _ in range(15):  # up to 30s
            try:
                enabled = dash.evaluate(r"""() => {
                  const b = document.getElementById('qr-export-modal-download');
                  if (!b) return null;
                  return !b.disabled && !b.classList.contains('disabled');
                }""")
                if enabled:
                    break
            except Exception:
                pass
            time.sleep(2)

        with page.expect_download(timeout=240_000) as info:
            # Click via JS to bypass any visibility/overlay weirdness;
            # fall back to a normal click if the ID isn't present.
            try:
                dash.evaluate(r"""() => {
                  const b = document.getElementById('qr-export-modal-download');
                  if (b) b.click();
                }""")
            except Exception:
                dl_btn = dash.locator("button:has-text('ダウンロード')")
                dl_btn.last.click(timeout=10_000, force=True)
        dl = info.value
        # Tag with shop name so per-shop files are distinguishable
        safe = shop_name.replace(" ", "_").replace("/", "_")
        out_path = download_dir / f"{safe}_{dl.suggested_filename}"
        dl.save_as(str(out_path))
        return out_path

    def _looker_complete_download(self, page: "Page", dash, src: SourceConfig,
                                   shop_name: str, download_dir: Path) -> Path:
        """Common modal handler — runs after either:
          (a) tile kebab → データをダウンロード, OR
          (b) dashboard kebab (ダッシュボード アクション) → ダウンロード.
        Expands 高度なデータオプション, picks すべての結果, picks a format
        (TSV/CSV), then captures the download.
        """
        # Expand 高度なデータオプション
        for adv_sel in ("text='高度なデータ オプション'",
                        "text='高度なデータオプション'",
                        "button:has-text('高度なデータ')"):
            try:
                adv = dash.locator(adv_sel).first
                if adv.count() > 0 and adv.is_visible():
                    adv.click(timeout=3_000)
                    time.sleep(1)
                    break
            except Exception:
                continue
        # Check すべての結果
        for sel in ("text='すべての結果'",
                    "label:has-text('すべての結果')",
                    "input[type='radio'][value*='all'i]"):
            try:
                ar = dash.locator(sel).first
                if ar.count() > 0 and ar.is_visible():
                    ar.click(timeout=3_000)
                    time.sleep(1)
                    break
            except Exception:
                continue
        # Pick format
        for fmt_sel in (
            "label:has-text('TSV')",
            "label:has-text('テキスト')",
            "label:has-text('CSV')",
            "input[type='radio'][value='txt']",
            "input[type='radio'][value='csv']",
        ):
            try:
                fm = dash.locator(fmt_sel).first
                if fm.count() > 0 and fm.is_visible():
                    fm.click(timeout=3_000)
                    time.sleep(1)
                    break
            except Exception:
                continue
        # Wait for the modal download button to become enabled
        for _ in range(15):  # up to 30s
            try:
                enabled = dash.evaluate(r"""() => {
                  const b = document.getElementById('qr-export-modal-download');
                  if (!b) return null;
                  return !b.disabled && !b.classList.contains('disabled');
                }""")
                if enabled:
                    break
            except Exception:
                pass
            time.sleep(2)
        # Diagnostic: dump modal buttons before clicking
        try:
            modal_btns = dash.evaluate(r"""() => {
              return [...document.querySelectorAll('button')]
                .filter(b => b.offsetParent !== null)
                .map(b => {
                  const t = (b.innerText || '').replace(/\s+/g, ' ').trim();
                  return {text: t, id: b.id || '', disabled: b.disabled};
                })
                .filter(b => b.text || b.id)
                .slice(0, 30);
            }""")
            logger.info("   modal buttons: %s", modal_btns)
        except Exception:
            pass

        # Click + capture (up to 10 min — dashboard-level downloads with
        # full-result option can take several minutes to generate).
        with page.expect_download(timeout=600_000) as info:
            clicked = False
            try:
                clicked = dash.evaluate(r"""() => {
                  const b = document.getElementById('qr-export-modal-download');
                  if (b && !b.disabled) { b.click(); return true; }
                  // Fallback: find any visible button labeled ダウンロード
                  // (not 'キャンセル' or 'ダウンロードを送信' etc.)
                  for (const btn of document.querySelectorAll('button')) {
                    if (btn.offsetParent === null) continue;
                    if (btn.disabled) continue;
                    const t = (btn.innerText || '').replace(/\s+/g,' ').trim();
                    if (t === 'ダウンロード') {
                      btn.click(); return true;
                    }
                  }
                  return false;
                }""")
            except Exception as exc:
                logger.warning("   final dl click via JS failed: %s", exc)
            if not clicked:
                dl_btn = dash.locator("button:has-text('ダウンロード')")
                dl_btn.last.click(timeout=10_000, force=True)
            logger.info("   waiting for download event (up to 10 min)...")
        dl = info.value
        safe = shop_name.replace(" ", "_").replace("/", "_")
        out_path = download_dir / f"{safe}_{dl.suggested_filename}"
        dl.save_as(str(out_path))
        return out_path

    def _dl_sales_center(self, context: BrowserContext, page: Page,
                         src: SourceConfig, download_dir: Path) -> Path:
        """ZOZO central sales download center (Sales_download.asp).

        The page renders a DownloadForm_<file>.csv carrying a fresh
        csrf_token and the current FileName. Scrape both, then POST them.
        FileName contains Japanese → must be Shift-JIS (cp932) URL-encoded.
        """
        from urllib.parse import quote
        page.goto("https://to.zozo.jp/to/Sales_download.asp",
                  wait_until="domcontentloaded", timeout=30_000)
        time.sleep(1.5)
        # Bug fix (2026-05-28): the page lists ALL pending downloads (sales
        # summaries like "2026年04月集計.csv" AND セール設定 "salegoods.csv").
        # The previous implementation picked the FIRST form which often
        # downloaded the wrong (summary) file. Filter for FileName containing
        # 'salegoods' (or whatever default filename was configured).
        wanted = (src.filename_default or "salegoods").split(".")[0]
        info = page.evaluate(r"""(wanted) => {
          let fallback = null;
          for (const f of document.forms) {
            const c = f.querySelector("input[name='c']");
            if (!(c && /downl/i.test(c.value||''))) continue;
            const g = n => { const e=f.querySelector(`[name='${n}']`);
                             return e ? e.value : ''; };
            const fn = g('FileName');
            const rec = {csrf:g('csrf_token'), fn:fn,
                         shop:g('ShopID')||'0', scat:g('SCategoryPID')||'0'};
            if (fn && fn.toLowerCase().includes(wanted.toLowerCase())) {
              return rec;   // exact target match
            }
            if (!fallback) fallback = rec;
          }
          return fallback;
        }""", wanted)
        if not info or not info.get("fn"):
            raise RuntimeError("sales center: DownloadForm not found")
        if wanted.lower() not in (info.get("fn") or "").lower():
            logger.warning("   sales_center: target '%s' not found in form list, "
                           "falling back to first form '%s'",
                           wanted, info.get("fn"))
        body = (f"c=DownLoad&csrf_token={quote(info['csrf'])}"
                f"&FileName={quote(info['fn'], encoding='cp932')}"
                f"&ShopID={info['shop']}&SCategoryPID={info['scat']}")
        resp = context.request.post(
            src.post_url, data=body, timeout=120_000,
            headers={"content-type": "application/x-www-form-urlencoded",
                     "referer": src.post_url})
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} sales center POST")
        path = download_dir / (info["fn"] or src.filename_default)
        path.write_bytes(resp.body())
        return path

    def _dl_session_get(self, context: BrowserContext, src: SourceConfig,
                        download_dir: Path) -> Path:
        """Fetch the direct endpoint with the authenticated session cookies."""
        resp = context.request.get(src.download_url, timeout=120_000)
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} fetching {src.download_url}")
        cd = resp.headers.get("content-disposition", "")
        fn = src.filename_default
        if "filename=" in cd:
            fn = cd.split("filename=")[-1].strip('"; ')
        path = download_dir / fn
        path.write_bytes(resp.body())
        return path

    def _dl_harvest_hrefs(self, context: BrowserContext, page: Page,
                          src: SourceConfig, download_dir: Path) -> Path:
        """Collect every <a href> (and form action) that looks like a CSV
        endpoint — including ones hidden inside dropdown menus — then fetch
        each with the authenticated session until one returns real CSV.

        This is the most robust path: it does not depend on an element being
        visible or clickable, only on the link existing in the DOM.
        """
        from urllib.parse import urljoin

        hrefs: list[str] = []
        try:
            raw = page.eval_on_selector_all(
                "a", "els => els.map(e => e.getAttribute('href'))") or []
            hrefs.extend(h for h in raw if h)
        except Exception:
            pass
        try:
            actions = page.eval_on_selector_all(
                "form", "els => els.map(e => e.getAttribute('action'))") or []
            hrefs.extend(a for a in actions if a)
        except Exception:
            pass

        # Rank: explicit *_csv.asp first, then anything csv/download-ish
        def score(h: str) -> int:
            hl = h.lower()
            if "_csv.asp" in hl or "csv.asp" in hl:
                return 0
            if "csv" in hl:
                return 1
            if "download" in hl or "export" in hl or "_dl" in hl:
                return 2
            return 9

        cand = sorted(
            {urljoin(page.url, h) for h in hrefs
             if any(p.lower() in h.lower() for p in self._DL_HREF_PATTERNS)},
            key=score)

        if not cand:
            raise RuntimeError("no CSV-like href in DOM")

        last = "none"
        for url in cand[:12]:
            try:
                resp = context.request.get(url, timeout=120_000)
                if resp.status != 200:
                    last = f"HTTP {resp.status} {url[:60]}"
                    continue
                body = resp.body()
                if not self._looks_like_csv(body):
                    last = f"HTML from {url[:60]}"
                    continue
                cd = resp.headers.get("content-disposition", "")
                fn = src.filename_default
                if "filename=" in cd:
                    fn = cd.split("filename=")[-1].strip('"; ')
                path = download_dir / fn
                path.write_bytes(body)
                logger.info("   harvested CSV from %s", url)
                return path
            except Exception as exc:
                last = str(exc)[:80]
                continue
        raise RuntimeError(f"no harvested href yielded CSV ({last})")

    MANUAL_CENTER_URL = "https://to.zozo.jp/to/ManualDownLoad.asp"

    def _dl_manual_center(self, context: BrowserContext, page: Page,
                          src: SourceConfig, download_dir: Path) -> Path:
        """Handle ZOZO's centralised async CSV flow.

        1. On the current data page, fire the CSV-generation trigger (a link
           that posts the request and lands on ManualDownLoad.asp).
        2. Open ManualDownLoad.asp (the download queue / history).
        3. Poll it: when the freshly-generated file's link appears, fetch it
           with the authenticated session.
        """
        from urllib.parse import urljoin

        # 1) Try to fire a CSV-generation trigger on the data page.
        for txt in ("CSVダウンロード", "ＣＳＶダウンロード", "CSV出力", "ダウンロード", "CSV"):
            try:
                loc = page.locator(
                    f"a:has-text('{txt}'), button:has-text('{txt}'), "
                    f"input[type=submit][value*='{txt}'], input[type=button][value*='{txt}']")
                if loc.count() > 0:
                    loc.first.click(force=True, no_wait_after=True, timeout=8_000)
                    time.sleep(2.0)
                    break
            except Exception:
                continue

        # 2+3) Poll the download centre for the generated file.
        deadline = time.time() + 90
        last = "no file link found"
        while time.time() < deadline:
            try:
                page.goto(self.MANUAL_CENTER_URL,
                          wait_until="domcontentloaded", timeout=30_000)
                time.sleep(1.0)
                raw = page.eval_on_selector_all(
                    "a", "els => els.map(e => e.getAttribute('href'))") or []
                links = sorted(
                    {urljoin(page.url, h) for h in raw if h and any(
                        p.lower() in h.lower()
                        for p in ("download", "dl", "csv", "file"))},
                    key=lambda h: 0 if "csv" in h.lower() else 1)
                for url in links[:15]:
                    try:
                        resp = context.request.get(url, timeout=120_000)
                        if resp.status == 200 and self._looks_like_csv(resp.body()):
                            cd = resp.headers.get("content-disposition", "")
                            fn = src.filename_default
                            if "filename=" in cd:
                                fn = cd.split("filename=")[-1].strip('"; ')
                            path = download_dir / fn
                            path.write_bytes(resp.body())
                            logger.info("   got %s from download center", fn)
                            return path
                    except Exception as exc:
                        last = str(exc)[:60]
                        continue
            except Exception as exc:
                last = str(exc)[:60]
            time.sleep(6)
        raise RuntimeError(f"download center: {last}")

    def _dl_click_selector(self, page: Page, selector: str, src: SourceConfig,
                           download_dir: Path) -> Path:
        loc = page.locator(selector)
        if loc.count() == 0:
            raise RuntimeError(f"selector not found: {selector}")
        with page.expect_download(timeout=120_000) as dl_info:
            loc.first.click(force=True, no_wait_after=True, timeout=15_000)
        return self._save_download(dl_info.value, src, download_dir)

    # Text/href patterns that mark a CSV download trigger on ZOZO BO pages.
    _DL_TEXT_PATTERNS = ["ダウンロード", "ＣＳＶ", "CSV", "csv出力", "CSV出力",
                         "出力", "エクスポート", "DL", "ダウンロ"]
    _DL_HREF_PATTERNS = ["_csv.asp", "csv.asp", "download", "Download",
                         "Csv", "CSV", "_dl", "export"]

    def _dl_click_discovered(self, page: Page, src: SourceConfig,
                             download_dir: Path) -> Path:
        """Scan the page for any element that looks like a CSV trigger and
        click each candidate until a download fires."""
        candidates = []
        for txt in self._DL_TEXT_PATTERNS:
            candidates.append(f"a:has-text('{txt}')")
            candidates.append(f"button:has-text('{txt}')")
            candidates.append(f"input[type=submit][value*='{txt}']")
            candidates.append(f"input[type=button][value*='{txt}']")
        for hp in self._DL_HREF_PATTERNS:
            candidates.append(f"a[href*='{hp}']")

        last_err = "no candidate matched"
        for sel in candidates:
            try:
                loc = page.locator(sel)
                if loc.count() == 0:
                    continue
                with page.expect_download(timeout=45_000) as dl_info:
                    loc.first.click(force=True, no_wait_after=True, timeout=10_000)
                return self._save_download(dl_info.value, src, download_dir)
            except Exception as exc:
                last_err = f"{sel}: {str(exc)[:60]}"
                continue
        raise RuntimeError(f"discovery found no working trigger ({last_err})")

    def _save_download(self, download, src: SourceConfig, download_dir: Path) -> Path:
        fn = download.suggested_filename or src.filename_default
        path = download_dir / fn
        download.save_as(path)
        return path

    # ── Upload ────────────────────────────────────────────────────────────────

    def _upload_to_gcs(self, local: Path, gcs_path: str) -> None:
        bucket = self.gcs_client.bucket(self.gcs_bucket)
        blob = bucket.blob(gcs_path)
        blob.upload_from_filename(str(local))

    # ── Monitoring ────────────────────────────────────────────────────────────

    def _log_run(self, src: SourceConfig, result: dict) -> None:
        """Insert one row into monitoring.scraping_runs."""
        try:
            from google.cloud import bigquery
            project = os.getenv("GCP_PROJECT_ID", "mono-back-office-system")
            client = bigquery.Client(project=project)
            table = f"{project}.monitoring.scraping_runs"
            row = {
                "run_id":       self.run_id,
                "run_date":     self.target_date,
                "source_name":  src.name,
                "source_label": src.label,
                "status":       result["status"],
                "filename":     result.get("filename"),
                "size_bytes":   result.get("size_bytes"),
                "gcs_path":     result.get("gcs_path"),
                "error_message":result.get("error"),
                "started_at":   result["started_at"],
                "finished_at":  result.get("finished_at"),
            }
            errors = client.insert_rows_json(table, [row])
            if errors:
                logger.warning("BQ insert errors: %s", errors)
        except Exception as exc:
            logger.warning("Failed to log run to BigQuery: %s", exc)


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def main() -> int:
    basic_user = get_secret("ZOZO_BASIC_USER")
    basic_pw   = get_secret("ZOZO_BASIC_PASSWORD")
    login_id   = get_secret("ZOZO_LOGIN_ID")
    password   = get_secret("ZOZO_LOGIN_PASSWORD")
    if not all([basic_user, basic_pw, login_id, password]):
        logger.error("Missing credentials. Need 4 env vars/secrets:")
        logger.error("  ZOZO_BASIC_USER, ZOZO_BASIC_PASSWORD, ZOZO_LOGIN_ID, ZOZO_LOGIN_PASSWORD")
        return 2

    only_env = os.getenv("ONLY", "").strip()
    only = [s.strip() for s in only_env.split(",") if s.strip()] if only_env else None

    scraper = ZOZOScraper(
        basic_user=basic_user, basic_pw=basic_pw,
        login_id=login_id, password=password,
        headless=os.getenv("HEADLESS", "1") == "1",
    )
    summary = scraper.run(only=only)
    failed = sum(1 for r in summary["results"] if r["status"] != "ok")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
