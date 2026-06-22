"""Capture CSV recipes for 倉庫在庫:入荷日毎 and クーポン除外(イベントカレンダー)."""
import json, os, sys, time
from pathlib import Path
from datetime import date, timedelta
from playwright.sync_api import sync_playwright

LOGIN_URL = "https://to.zozo.jp/to/"
BASE = "https://to.zozo.jp/to/"
OUT = Path(__file__).parent / "html"
T = os.getenv("TARGET_DATE") or (date.today() - timedelta(days=1)).isoformat()

# candidate landing pages to inspect
PAGES = {
    "zaiko_arrival_a": "zaiko_csv2.asp?c=Zaiko",          # known SKU毎 page - inspect for 入荷日毎 option
    "zaiko_arrival_b": "zaiko_csv.asp?c=Zaiko",
    "event_calendar":  "EventCalendar.asp",
    "event_calendar2": "EventCalendar.asp?c=Init",
    "coupon_exclude":  "EventCalendar.asp?c=CouponExclude",
}


def login(page):
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
    if page.locator('input[name="LoginName"]').count() > 0:
        page.fill('input[name="LoginName"]', os.environ["ZOZO_LOGIN_ID"])
        page.fill('input[name="Password"]', os.environ["ZOZO_LOGIN_PASSWORD"])
        with page.expect_navigation(wait_until="domcontentloaded", timeout=30_000):
            page.get_by_role("button", name="ログイン").first.click()


def main():
    rep = {}
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(locale="ja-JP", viewport={"width":1440,"height":1000},
            accept_downloads=True,
            http_credentials={"username":os.environ["ZOZO_BASIC_USER"],
                              "password":os.environ["ZOZO_BASIC_PASSWORD"]})
        page = ctx.new_page()
        hits=[]
        def on_resp(r):
            try:
                ct=(r.headers.get("content-type") or "").lower()
                cd=(r.headers.get("content-disposition") or "").lower()
                if ("csv" in ct or "excel" in ct or "attachment" in cd
                        or "octet-stream" in ct or r.url.lower().endswith(".csv")):
                    hits.append({"url":r.url,"status":r.status,"method":r.request.method,
                                 "post":(r.request.post_data or "")[:1500],"ct":ct,"cd":cd[:60]})
            except Exception: pass
        page.on("response", on_resp)
        login(page); print("logged in", page.url)
        for key,url in PAGES.items():
            n0=len(hits)
            try:
                page.goto(BASE+url, wait_until="domcontentloaded", timeout=30_000)
                time.sleep(2)
                fin=page.url; title=page.title()
                err=("Message" in fin or "Error" in fin or "404" in title)
                # dump forms + zaiko/arrival/coupon related links
                info=page.evaluate(r"""()=>{
                  const forms=[...document.forms].map(f=>({name:f.name,action:f.getAttribute('action'),
                    method:(f.getAttribute('method')||'GET').toUpperCase(),
                    fields:[...f.querySelectorAll('input,select,button')].slice(0,30).map(i=>({
                      n:i.name,t:i.type,v:(i.value||'').slice(0,30),txt:(i.innerText||'').trim().slice(0,20)}))}));
                  const links=[...document.querySelectorAll('a')].map(a=>({
                    t:(a.innerText||'').trim().slice(0,24),h:a.getAttribute('href')||'',
                    oc:(a.getAttribute('onclick')||'').slice(0,90)}))
                    .filter(x=>/入荷|arrival|csv|ダウンロ|出力|クーポン|coupon|除外|event/i.test(x.t+x.h+x.oc));
                  return {forms,links};
                }""")
                # try clicking csv/download triggers
                for t in ("入荷日毎","CSVダウンロード","ＣＳＶ","CSV","ダウンロード","出力","クーポン除外","除外品番"):
                    for sel in (f"a:has-text('{t}')",f"button:has-text('{t}')",
                                f"input[value*='{t}']"):
                        try:
                            loc=page.locator(sel)
                            if loc.count()==0: continue
                            loc.first.click(force=True,no_wait_after=True,timeout=4000)
                            time.sleep(3)
                            if len(hits)>n0: break
                        except Exception: continue
                    if len(hits)>n0: break
                rep[key]={"url":url,"final":fin[-55:],"title":title[:30],"err":err,
                          "forms":info["forms"],"links":info["links"][:12],
                          "new_hits":hits[n0:]}
            except Exception as e:
                rep[key]={"url":url,"fatal":str(e)[:150]}
            print(key,"err=",rep[key].get("err"),"hits=",len(rep[key].get("new_hits",[])))
        ctx.close(); b.close()
    (OUT/"probe_two.json").write_text(json.dumps(rep,ensure_ascii=False,indent=2),encoding="utf-8")
    print("saved html/probe_two.json")
    return 0


if __name__=="__main__":
    sys.exit(main())
