"""Brute-probe likely CSV command endpoints for reservations / product_master /
zozoad by GET and POST with the authenticated session, checking for CSV bytes."""
import os, sys
from datetime import date, timedelta
from playwright.sync_api import sync_playwright

LOGIN_URL = "https://to.zozo.jp/to/"
BASE = "https://to.zozo.jp/to/"
T = os.getenv("TARGET_DATE") or (date.today() - timedelta(days=1)).isoformat()
DENC = T.replace("-", "%2F")
DL = "%83_%83E%83%93%83%8D%81%5B%83h"

CANDIDATES = [
    # reservations (予約管理一覧 / 予約納期管理)
    "Reserve.asp?c=Csv", "Reserve.asp?c=CsvDownload", "Reserve.asp?c=Download",
    "Reserve.asp?c=ReserveListCsv", "Reserve.asp?c=ListCsv",
    "Reserve.asp?c=ReserveCsv", "Reserve_csv.asp?c=Reserve",
    "reserve_csv.asp?c=Reserve", "ReserveList_csv.asp",
    # product_master (登録商品 / 商品検索)
    "GoodsSearch.asp?c=Csv", "GoodsSearch.asp?c=CsvDownload",
    "GoodsSearch.asp?c=Download", "goods_csv.asp?c=Goods",
    "Goods_csv.asp?c=Goods", "GoodsSearch.asp?c=GoodsCsv",
    "GoodsCsv.asp?c=Init", "goods_cs.asp",
    # zozoad
    "Advertisement.asp?c=Csv", "Advertisement.asp?c=Download",
    "Advertisement.asp?c=Detail", "Advertisement.asp?c=Report",
    "advertisement_csv.asp?c=Advertisement", "Ad_csv.asp",
]
# also try POST c=Download style on Reserve/GoodsSearch
POSTS = [
    ("Reserve.asp", f"c=Download&ShopID=-1&SCategoryPID=0&SCategoryID=0&TermFrom={DENC}&TermTo={DENC}&DL_BUTTON={DL}"),
    ("Reserve.asp", f"c=CsvDownload&ShopID=-1&DL_BUTTON={DL}"),
    ("GoodsSearch.asp", f"c=Download&ShopID=-1&DL_BUTTON={DL}"),
    ("GoodsSearch.asp", f"c=Csv&ShopID=-1&DL_BUTTON={DL}"),
]


def login(page):
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
    if page.locator('input[name="LoginName"]').count() > 0:
        page.fill('input[name="LoginName"]', os.environ["ZOZO_LOGIN_ID"])
        page.fill('input[name="Password"]', os.environ["ZOZO_LOGIN_PASSWORD"])
        with page.expect_navigation(wait_until="domcontentloaded", timeout=30_000):
            page.get_by_role("button", name="ログイン").first.click()


def is_csv(b: bytes) -> bool:
    h = b[:120].lower()
    return len(b) > 200 and b"<html" not in h and b"<!doctype" not in h


def main():
    with sync_playwright() as p:
        br = p.chromium.launch(headless=True)
        ctx = br.new_context(locale="ja-JP",
            http_credentials={"username": os.environ["ZOZO_BASIC_USER"],
                              "password": os.environ["ZOZO_BASIC_PASSWORD"]})
        page = ctx.new_page()
        login(page)
        print("logged in")
        for u in CANDIDATES:
            try:
                r = ctx.request.get(BASE + u, timeout=40_000)
                b = r.body()
                tag = "CSV!!" if (r.status == 200 and is_csv(b)) else "no"
                if tag == "CSV!!" or r.status not in (200, 302, 404):
                    print(f"  GET {u:55s} {r.status} {len(b):>9,} {tag} "
                          f"ct={r.headers.get('content-type','')[:25]}")
            except Exception as e:
                print(f"  GET {u} ERR {str(e)[:50]}")
        for url, body in POSTS:
            try:
                r = ctx.request.post(BASE + url, data=body, headers={
                    "content-type": "application/x-www-form-urlencoded"},
                    timeout=60_000)
                b = r.body()
                tag = "CSV!!" if (r.status == 200 and is_csv(b)) else "no"
                print(f"  POST {url} [{body[:30]}] {r.status} {len(b):,} {tag} "
                      f"ct={r.headers.get('content-type','')[:25]}")
            except Exception as e:
                print(f"  POST {url} ERR {str(e)[:50]}")
        ctx.close(); br.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
