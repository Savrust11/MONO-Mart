"""
ファーストセラー (siteinfo.asp?c=Seller) フォームのフィールド・選択肢を1回だけ調査する
ヘルパー。「すべてのパターン（商品タイプ × タイプ）ループ」実装の前提情報を取得する。

なぜ必要か:
  商品タイプ/タイプ の選択肢は静的HTMLに無く（リポジトリの captured form は『指定なし』のみ）、
  ライブの BO フォーム上で動的にロードされる。正しくループを組むには、実フォームの
  ・該当フィールド名（商品タイプ / タイプ がどの select か）
  ・選択肢（value / ラベル）
  ・カスケード挙動（商品タイプを選ぶと タイプ がどう変わるか）
  を一度だけ取得する必要がある。

実行（BOにアクセスできる Windows 等の環境で1回だけ）:
  python pipeline/scrapers/_discover_seller_form.py  > seller_form_dump.txt

ENV は fetch_first_seller.py と同じ:
  ZOZO_LOGIN_ID / ZOZO_LOGIN_PASSWORD / ZOZO_BASIC_USER / ZOZO_BASIC_PASSWORD
"""
from __future__ import annotations
import os
from playwright.sync_api import sync_playwright
from fetch_first_seller import PAGE_URL, login  # 同ディレクトリのスクレイパを再利用


def dump_form(page) -> dict:
    """現在のページの全 <select>（name+選択肢）と radio グループを返す。"""
    return page.evaluate(r"""() => {
      const out = {selects: [], radios: {}};
      for (const s of document.querySelectorAll('select')) {
        out.selects.push({
          name: s.getAttribute('name') || '(no-name)',
          options: [...s.options].map(o => [o.value, (o.textContent || '').trim()]),
        });
      }
      for (const r of document.querySelectorAll('input[type=radio]')) {
        const n = r.getAttribute('name'); if (!n) continue;
        (out.radios[n] = out.radios[n] || []).push([r.value, r.checked]);
      }
      return out;
    }""")


def main() -> None:
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(http_credentials={
            "username": os.environ["ZOZO_BASIC_USER"],
            "password": os.environ["ZOZO_BASIC_PASSWORD"],
        })
        pg = ctx.new_page()
        login(pg)
        pg.goto(PAGE_URL, wait_until="domcontentloaded", timeout=45_000)
        pg.wait_for_timeout(1500)

        base = dump_form(pg)
        print("=" * 60)
        print("Seller フォーム — 全 SELECT")
        print("=" * 60)
        for s in base["selects"]:
            print(f"\nSELECT name={s['name']}  ({len(s['options'])} options)")
            for v, t in s["options"][:60]:
                print(f"    value={v!r:>10}  : {t}")
        print("\nRADIO groups:")
        for n, vals in base["radios"].items():
            print(f"  {n}: {vals}")

        # カスケード調査: 商品タイプ候補 select の最初の実値を選び、タイプ がどう変わるか観察
        candidates = ["SCategoryPID", "SCategoryID", "ItemTypeID", "GoodsTypeID", "CategoryID"]
        for fld in candidates:
            opts = next((s["options"] for s in base["selects"] if s["name"] == fld), None)
            if not opts:
                continue
            nonzero = [v for v, _t in opts if v not in ("", "0")]
            if not nonzero:
                print(f"\n[cascade] {fld}: 実値の選択肢なし（動的ロードの可能性）")
                continue
            pick = nonzero[0]
            print("\n" + "=" * 60)
            print(f"カスケード: {fld} = {pick} を選択 → 他 SELECT の変化")
            print("=" * 60)
            try:
                pg.select_option(f'select[name="{fld}"]', pick)
                pg.wait_for_timeout(2000)
                after = dump_form(pg)
                for s in after["selects"]:
                    if s["name"] in (fld, "ShopID"):
                        continue
                    print(f"  SELECT {s['name']}: {len(s['options'])} -> {s['options'][:20]}")
            except Exception as e:
                print(f"  cascade probe error: {e}")
            break

        ctx.close()
        b.close()


if __name__ == "__main__":
    main()
