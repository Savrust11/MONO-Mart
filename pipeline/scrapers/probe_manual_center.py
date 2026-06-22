"""Deep-probe ManualDownLoad.asp — the batch/queued download center.

Dump every row/link/form so we can see whether 予約管理一覧 (ReserveList)
and 登録商品 (goods) CSVs are retrievable there, and how.
"""
import json, os, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

LOGIN_URL = "https://to.zozo.jp/to/"
BASE = "https://to.zozo.jp/to/"
OUT = Path(__file__).parent / "html"


def login(page):
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
    if page.locator('input[name="LoginName"]').count() > 0:
        page.fill('input[name="LoginName"]', os.environ["ZOZO_LOGIN_ID"])
        page.fill('input[name="Password"]', os.environ["ZOZO_LOGIN_PASSWORD"])
        with page.expect_navigation(wait_until="domcontentloaded", timeout=30_000):
            page.get_by_role("button", name="ログイン").first.click()


def main():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(locale="ja-JP", viewport={"width":1440,"height":1100},
            accept_downloads=True,
            http_credentials={"username":os.environ["ZOZO_BASIC_USER"],
                              "password":os.environ["ZOZO_BASIC_PASSWORD"]})
        page = ctx.new_page()
        login(page)

        report = {}
        for key, url in [("root", "ManualDownLoad.asp"),
                         ("init", "ManualDownLoad.asp?c=Init"),
                         ("type3502", "ManualDownLoad.asp?c=Init&ShowManualType=3502")]:
            try:
                page.goto(BASE + url, wait_until="domcontentloaded", timeout=30_000)
                time.sleep(2)
                (OUT / f"manualcenter_{key}.html").write_text(page.content(), encoding="utf-8")
                # capture the visible table text + all links + all forms + selects
                data = page.evaluate(r"""() => {
                  const links=[...document.querySelectorAll('a')].map(a=>({
                    t:(a.innerText||'').trim().slice(0,40),
                    href:a.getAttribute('href')||'',
                    oc:(a.getAttribute('onclick')||'').slice(0,140)})).filter(x=>x.t||x.href);
                  const sels=[...document.querySelectorAll('select')].map(s=>({
                    name:s.name, opts:[...s.options].slice(0,20).map(o=>({v:o.value,t:o.text.trim().slice(0,30)}))}));
                  const forms=[...document.forms].map(f=>({
                    name:f.name, action:f.getAttribute('action'),
                    method:(f.getAttribute('method')||'GET').toUpperCase(),
                    fields:[...f.querySelectorAll('input,select')].map(i=>({n:i.name,t:i.type,v:(i.value||'').slice(0,40)}))}));
                  const rows=[...document.querySelectorAll('table tr')].slice(0,40)
                    .map(tr=>tr.innerText.replace(/\s+/g,' ').trim().slice(0,160)).filter(x=>x);
                  return {links, sels, forms, rows, title:document.title};
                }""")
                report[key] = {"url": page.url, **data}
            except Exception as e:
                report[key] = {"error": str(e)[:160]}

        (OUT / "manualcenter_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

        for k, v in report.items():
            print("="*70)
            print(k, v.get("url",""), v.get("title",""))
            for s in v.get("sels", []):
                print("  SELECT", s["name"], "->", [o["t"] for o in s["opts"]][:14])
            for f in v.get("forms", []):
                if f["fields"]:
                    print("  FORM", f["method"], f["action"],
                          [(x["n"],x["t"]) for x in f["fields"] if x["n"]][:10])
            dl = [l for l in v.get("links", [])
                  if any(p in (l["t"]+l["href"]+l["oc"]).lower()
                         for p in ("csv","reservelist","予約","登録商品","goods","download","dl","ダウンロ"))]
            for l in dl[:20]:
                print("   L", repr(l["t"][:30]), "href=", l["href"][:55], "oc=", l["oc"][:80])
            for r in v.get("rows", [])[:12]:
                print("   ROW:", r[:140])
        ctx.close(); b.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
