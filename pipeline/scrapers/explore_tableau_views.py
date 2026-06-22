"""Click the 予約管理 Recents card on Tableau Home, capture the view URL,
and dump toolbar/download controls across all frames. Read-only."""
import json, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

SESS = Path(__file__).parent / "sessions"
STATE = SESS / "tableau_state.json"
HOME = "https://prod-apnortheast-a.online.tableau.com/#/site/sitaterunext/home"


def dump_controls(scope, label):
    try:
        return scope.evaluate(r"""() => {
          const norm = s => (s==null?'':String(s)).replace(/\s+/g,' ').trim();
          return [...document.querySelectorAll('button,[role=button],a,[data-tb-test-id],span')]
            .map(e=>({tag:e.tagName,
              tid:e.getAttribute&&e.getAttribute('data-tb-test-id')||null,
              al:norm(e.getAttribute&&e.getAttribute('aria-label')),
              tt:norm(e.getAttribute&&e.getAttribute('title')),
              tx:norm(e.innerText).slice(0,24), vis:!!e.offsetParent}))
            .filter(x=>(x.tid||x.al||x.tt||x.tx) &&
              /download|ダウンロ|エクスポート|export|crosstab|クロス集計|データ|toolbar/i
              .test((x.tid||'')+(x.al||'')+(x.tt||'')+(x.tx||'')));
        }""")
    except Exception as e:
        return [{"frame_err": str(e)[:80], "label": label}]


def main():
    rep = {}
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(storage_state=str(STATE), locale="ja-JP",
                            viewport={"width": 1600, "height": 1000},
                            accept_downloads=True)
        pg = ctx.new_page()
        try:
            pg.goto(HOME, wait_until="domcontentloaded", timeout=60_000)
            time.sleep(14)
            # Click the first element whose text is exactly/contains 予約管理
            clicked = False
            for sel in ["text=予約管理", "[aria-label*='予約管理']",
                        "[title*='予約管理']"]:
                try:
                    loc = pg.locator(sel)
                    if loc.count() > 0:
                        loc.first.click(timeout=8_000)
                        clicked = True
                        break
                except Exception:
                    continue
            rep["clicked"] = clicked
            time.sleep(16)  # viz renders
            rep["view_url"] = pg.url
            pg.screenshot(path=str(SESS / "tbv_view.png"), full_page=True)
            rep["frames"] = [f.url for f in pg.frames]
            rep["main_controls"] = dump_controls(pg, "main")
            rep["frame_controls"] = {}
            for fr in pg.frames:
                if fr == pg.main_frame:
                    continue
                rep["frame_controls"][fr.url[:80]] = dump_controls(fr, fr.url[:50])
        except Exception as e:
            rep["error"] = str(e)[:200]
        finally:
            ctx.close(); b.close()
    (SESS / "tbv_report.json").write_text(
        json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print("clicked:", rep.get("clicked"))
    print("view_url:", rep.get("view_url"))
    print("frames:", rep.get("frames"))
    print("main_controls:")
    for c in rep.get("main_controls", [])[:15]:
        print("  ", c)
    for furl, ctrls in rep.get("frame_controls", {}).items():
        print("frame", furl)
        for c in ctrls[:15]:
            print("  ", c)
    print("error:", rep.get("error"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
