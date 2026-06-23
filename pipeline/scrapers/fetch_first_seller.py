"""
ZOZO BO ファーストセラー (No.16) — 週次取得。

クライアント仕様 (2026-05-29 確定):
  ・期間: ISO 8601 週 (月曜〜日曜)。毎週月曜03:00 JSTに前週分を取得。
  ・ショップ: ZOZOTOWN全店 (ShopID=0)
  ・親カテゴリ: 指定なし (SCategoryPID=0)
  ・商品タイプ × タイプ: 全てを1つずつループ (将来拡張)
  ・性別: MEN (CustomerTypeID=1), WOMEN (CustomerTypeID=2) それぞれ
  ・販売タイプ: 指定なし (OrderType=0)
  ・価格タイプ: 指定なし (PriceType=0)
  ・並び: 売上順 (SellOrderBy=1)
  ・モール: 指定なし (MallCheck=0)

ZOZO BO ファーストセラーは DL不可なため、画面表示の TOP50 ランキング
テーブルを HTML スクレイピングし CSV に整形してGCSへ保存する方式。

URL: https://to.zozo.jp/to/siteinfo.asp?c=Seller&clear=on
Form: form1 POST siteinfo.asp (c=Seller)

ENV:
  ZOZO_LOGIN_ID / ZOZO_LOGIN_PASSWORD / ZOZO_BASIC_USER / ZOZO_BASIC_PASSWORD
  GCS_RAW_BUCKET   (default: mono-back-office-system-raw-data)
  TARGET_DATE      (default: today JST; ISO週 = TARGET_DATE を含む週の前週)
"""
from __future__ import annotations
import csv, io, os, sys, time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from google.cloud import storage
from playwright.sync_api import sync_playwright

JST = timezone(timedelta(hours=9))
BASE = "https://to.zozo.jp/to/"
LOGIN_URL = BASE
PAGE_URL = BASE + "siteinfo.asp?c=Seller&clear=on"

# Gender axis to loop. CustomerTypeID: 0=指定なし, 1=MEN, 2=WOMEN, 3=KIDS
GENDERS = [
    ("MEN",   "1"),
    ("WOMEN", "2"),
]

# --- 全パターン (商品タイプ × タイプ) ループ設定 (client 2026: すべてのパターン) ----------
# 既定 OFF。FIRST_SELLER_FULL=1 で有効化（性別×商品タイプ×タイプ ≈ 1,700 検索/回）。
# タイプは商品タイプに連動（カスケード）するため、商品タイプ選択後にタイプ一覧を都度読む。
# 検証用: FIRST_SELLER_LIMIT=N で先頭 N(商品タイプ×タイプ) 組み合わせのみ実行。
FULL  = os.getenv("FIRST_SELLER_FULL", "0") == "1"
LIMIT = int(os.getenv("FIRST_SELLER_LIMIT", "0") or "0")   # >0 は検証用に件数制限
PACE  = float(os.getenv("FIRST_SELLER_PACE", "1.5"))       # 各検索間の待機秒(礼儀)

# 商品タイプ select を「内容」で識別するための代表ラベル（タイプ一覧と被らない単語）
_PT_MARKERS = ["トップス", "パンツ", "スカート", "シューズ", "バッグ", "帽子", "アクセサリー"]


def _read_selects(page) -> dict:
    """フォーム上の全 <select> を {name: [(value,label),...]} で返す。"""
    return page.evaluate(r"""() => {
      const o = {};
      for (const s of document.querySelectorAll('select')) {
        const n = s.getAttribute('name'); if (!n) continue;
        o[n] = [...s.options].map(op => [op.value, (op.textContent || '').trim()]);
      }
      return o;
    }""")


def _find_pt_select(selects: dict):
    """商品タイプ select の name を内容から特定する。"""
    for name, opts in selects.items():
        labels = [t for _v, t in opts]
        if sum(1 for m in _PT_MARKERS if m in labels) >= 3:
            return name
    return None


def _set_select(page, name: str, value: str) -> None:
    page.evaluate("""([n, v]) => {
      const s = document.querySelector('select[name="' + n + '"]');
      if (s) { s.value = v; s.dispatchEvent(new Event('change', {bubbles:true})); }
    }""", [name, value])


def _clean_rows(rows: list[list[str]]):
    """空列を除去し (header_row, data_rows) を返す。data_rows は header と一致する重複行を除外。"""
    kept = [i for i in range(len(rows[0])) if rows[0][i].strip() != ""]
    rows = [[r[i] if i < len(r) else "" for i in kept] for r in rows]
    header_row = rows[0]
    data_rows = [r for r in rows[1:] if r != header_row]
    return header_row, data_rows


def iso_previous_week(today: date) -> tuple[date, date]:
    """Return (Monday, Sunday) of the ISO week PRIOR to `today`.

    ISO 8601: week starts Monday. If today is Sunday 2026/06/14, returns
    (2026/06/01, 2026/06/07).
    """
    monday_this_week = today - timedelta(days=today.isoweekday() - 1)
    sunday_prev_week = monday_this_week - timedelta(days=1)
    monday_prev_week = sunday_prev_week - timedelta(days=6)
    return monday_prev_week, sunday_prev_week


def iso_week_number(d: date) -> tuple[int, int]:
    """Return (iso_year, iso_week) for date d. e.g. 2026/06/01 → (2026, 23)."""
    cal = d.isocalendar()
    return cal.year, cal.week


def login(page) -> None:
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
    if page.locator('input[name="LoginName"]').count() > 0:
        page.fill('input[name="LoginName"]', os.environ["ZOZO_LOGIN_ID"])
        page.fill('input[name="Password"]', os.environ["ZOZO_LOGIN_PASSWORD"])
        with page.expect_navigation(wait_until="domcontentloaded", timeout=30_000):
            page.get_by_role("button", name="ログイン").first.click()


def search_and_scrape(page, mon: date, sun: date, gender_label: str,
                      gender_id: str, pt_name: str = "", pt_value: str = "",
                      type_name: str = "", type_value: str = "") -> list[list[str]]:
    """Run the search with given filters and scrape the result table.

    Returns: list of rows including header (first row).
    """
    page.goto(PAGE_URL, wait_until="domcontentloaded", timeout=45_000)
    time.sleep(5)

    # Fill date range (datepicker inputs accept YYYY/MM/DD)
    from_str = mon.strftime("%Y/%m/%d")
    to_str = sun.strftime("%Y/%m/%d")
    page.fill('input[name="SellTermDTFrom"]', from_str)
    page.fill('input[name="SellTermDTTo"]', to_str)

    # Select gender (radio)
    page.evaluate(f"""() => {{
      const r = document.querySelector(
        'input[name="CustomerTypeID"][value="{gender_id}"]');
      if (r) {{ r.checked = true; r.dispatchEvent(new Event('change', {{bubbles:true}})); }}
    }}""")

    # Order: 売上 (already default = 1) — make explicit
    page.evaluate("""() => {
      const r = document.querySelector('input[name="SellOrderBy"][value="1"]');
      if (r) { r.checked = true; }
    }""")

    # ShopID: 全店 = "0" (no specific shop)
    page.evaluate("""() => {
      const s = document.querySelector('select[name="ShopID"]');
      if (s) { s.value = ''; s.dispatchEvent(new Event('change',{bubbles:true})); }
    }""")

    # 商品タイプ → (カスケード) → タイプ を設定（FULL モードのみ）
    if pt_name and pt_value:
        _set_select(page, pt_name, pt_value)
        time.sleep(3)  # タイプ一覧の再読込(カスケード)待ち
        if type_name and type_value:
            _set_select(page, type_name, type_value)
            time.sleep(0.5)

    time.sleep(1)
    # Click 検索 (the page's own submit button, not header search).
    # Header has its own submit button without a name attribute; the page
    # form1 button is button[name="search"][value="SEARCH"].
    btn = page.locator('button[name="search"][value="SEARCH"]')
    if btn.count() == 0:
        raise RuntimeError("検索ボタンが見つかりません")
    btn.first.click(timeout=10_000)
    # networkidle on ZOZO BO can hang due to background analytics; use
    # domcontentloaded + manual wait instead.
    page.wait_for_load_state("domcontentloaded", timeout=60_000)
    time.sleep(8)

    # Scrape the ranking table
    rows = page.evaluate(r"""() => {
      const norm = s => (s==null?'':String(s)).replace(/\s+/g,' ').trim();
      // Find the main result table — usually the largest <table>
      const tables = [...document.querySelectorAll('table')];
      let best = null, bestRows = 0;
      for (const t of tables) {
        const n = t.querySelectorAll('tr').length;
        if (n > bestRows) { best = t; bestRows = n; }
      }
      if (!best) return [];
      return [...best.querySelectorAll('tr')].map(tr =>
        [...tr.querySelectorAll('th,td')].map(c => norm(c.innerText || ''))
      );
    }""")
    return rows


def main():
    target_date_str = os.getenv("TARGET_DATE")
    if target_date_str:
        target_date = date.fromisoformat(target_date_str)
    else:
        target_date = datetime.now(JST).date()

    mon, sun = iso_previous_week(target_date)
    iso_year, iso_week = iso_week_number(mon)
    bucket_name = os.getenv("GCS_RAW_BUCKET",
                            "mono-back-office-system-raw-data")

    print(f"target_date  : {target_date}")
    print(f"ISO week     : {iso_year}-W{iso_week:02d}")
    print(f"period       : {mon} (月) 〜 {sun} (日)")

    with sync_playwright() as p:
        b = p.chromium.launch(headless=os.getenv("HEADLESS", "1") == "1")
        ctx = b.new_context(
            locale="ja-JP", viewport={"width": 1600, "height": 1100},
            accept_downloads=True,
            http_credentials={"username": os.environ["ZOZO_BASIC_USER"],
                              "password": os.environ["ZOZO_BASIC_PASSWORD"]})
        pg = ctx.new_page()
        login(pg)
        print(f"logged in: {pg.url}")

        all_results = []
        header_added = False

        def emit(rows, meta_vals, meta_cols) -> int:
            nonlocal header_added
            if not rows:
                return 0
            header_row, data_rows = _clean_rows(rows)
            if not header_added:
                all_results.append(meta_cols + header_row)
                header_added = True
            for r in data_rows:
                all_results.append(meta_vals + r)
            return len(data_rows)

        if FULL:
            # ===== 全パターン: 性別 × 商品タイプ × タイプ =====================
            META_COLS = ["iso_year", "iso_week", "period_from", "period_to",
                         "gender", "product_type", "type"]
            pg.goto(PAGE_URL, wait_until="domcontentloaded", timeout=45_000)
            time.sleep(5)
            selects = _read_selects(pg)
            pt_name = _find_pt_select(selects)
            if not pt_name:
                print("✗ 商品タイプ select を特定できませんでした"); ctx.close(); b.close(); return 1
            pt_opts = [(v, t) for v, t in selects[pt_name] if v not in ("", "0")]
            # タイプ select の name を特定: 商品タイプを1つ選び、変化した select を探す
            before = _read_selects(pg)
            _set_select(pg, pt_name, pt_opts[0][0]); time.sleep(3)
            type_name = next((n for n, o in _read_selects(pg).items()
                              if n != pt_name and o != before.get(n) and len(o) > 1), None)
            print(f"商品タイプ field={pt_name} ({len(pt_opts)}件) / タイプ field={type_name}"
                  + (f" / LIMIT={LIMIT}" if LIMIT else ""))
            if not type_name:
                print("✗ タイプ select を特定できませんでした"); ctx.close(); b.close(); return 1

            done = 0
            stop = False
            for gender_label, gender_id in GENDERS:
                if stop:
                    break
                for pt_value, pt_label in pt_opts:
                    try:
                        pg.goto(PAGE_URL, wait_until="domcontentloaded", timeout=45_000)
                        time.sleep(3)
                        _set_select(pg, pt_name, pt_value); time.sleep(3)
                        type_opts = [(v, t) for v, t in _read_selects(pg).get(type_name, [])
                                     if v not in ("", "0")]
                    except Exception as e:
                        print(f"  ✗ タイプ取得失敗 {gender_label}/{pt_label}: {str(e)[:120]}")
                        continue
                    print(f"\n--- {gender_label} / {pt_label}: タイプ {len(type_opts)}件 ---")
                    for type_value, type_label in type_opts:
                        try:
                            rows = search_and_scrape(
                                pg, mon, sun, gender_label, gender_id,
                                pt_name, pt_value, type_name, type_value)
                            n = emit(rows, [str(iso_year), str(iso_week), mon.isoformat(),
                                            sun.isoformat(), gender_label, pt_label, type_label],
                                     META_COLS)
                            done += 1
                            print(f"    [{done}] {gender_label}/{pt_label}/{type_label}: {n} rows")
                        except Exception as e:
                            print(f"    ✗ {gender_label}/{pt_label}/{type_label}: {str(e)[:120]}")
                        time.sleep(PACE)
                        if LIMIT and done >= LIMIT:
                            stop = True; break
                    if stop:
                        break
            print(f"\n総組み合わせ実行: {done}")
        else:
            # ===== 既定: 性別のみ（従来動作）===============================
            META_COLS = ["iso_year", "iso_week", "period_from", "period_to", "gender"]
            for gender_label, gender_id in GENDERS:
                print(f"\n--- 検索: 性別={gender_label} 期間={mon}〜{sun} ---")
                try:
                    rows = search_and_scrape(pg, mon, sun, gender_label, gender_id)
                    n = emit(rows, [str(iso_year), str(iso_week), mon.isoformat(),
                                    sun.isoformat(), gender_label], META_COLS)
                    print(f"  ✓ {gender_label}: {n} ranking rows scraped")
                except Exception as e:
                    print(f"  ✗ {gender_label} FAILED: {str(e)[:200]}")

        ctx.close(); b.close()

    if not all_results:
        print("no data scraped")
        return 1

    # Write CSV
    buf = io.StringIO()
    csv.writer(buf).writerows(all_results)
    data = buf.getvalue().encode("utf-8-sig")

    # 検証モード(LIMIT>0): 本番GCSを上書きしないよう、ローカル保存のみ。
    if LIMIT:
        local = "first_seller_LIMIT_test.csv"
        with open(local, "wb") as f:
            f.write(data)
        print(f"\n✓ [LIMIT={LIMIT}/検証] local save: {local} "
              f"({len(all_results)-1} rows) — 本番GCSには未アップロード")
        return 0

    gcs_path = (f"uploads/zozo/first_seller/{target_date.isoformat()}/"
                f"first_seller_W{iso_week:02d}.csv")
    storage.Client().bucket(bucket_name).blob(gcs_path).upload_from_string(
        data, content_type="text/csv")
    mode = "FULL(性別×商品タイプ×タイプ)" if FULL else "性別のみ"
    print(f"\n✓ saved: gs://{bucket_name}/{gcs_path} "
          f"({len(all_results)-1} rows, mode={mode}, {len(data):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
