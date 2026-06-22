"""簡易データ確認画面 (Phase 1 検証用)

毎日の日次バッチ後に実行され、現状のデータ取得状況・行数・品質チェックを
1つのHTMLファイルにまとめて GCS にアップロードする。クライアントは1つの
URLをブックマークすれば、いつでもパイプラインの稼働状況とデータ品質を
確認できる。

出力: gs://mono-back-office-system-exports/verify/index.html  (公開URL)
"""
from __future__ import annotations
import html
from datetime import datetime, timedelta, timezone
from pathlib import Path

from google.cloud import bigquery, storage

JST = timezone(timedelta(hours=9))
PROJECT = "mono-back-office-system"
EXPORTS_BUCKET = "mono-back-office-system-exports"
REPORT_PATH = "verify/index.html"

SKU_TEST_LIST = ["UBbg448", "AAsh1234", "sc737", "FOop671", "sc1426",
                 "sh1704", "CLEsc1116", "CUSpt981", "CLEpt1428", "CLEsc1183"]


def q(client, sql, params=None):
    cfg = bigquery.QueryJobConfig(query_parameters=params or [])
    return list(client.query(sql, job_config=cfg).result())


def main():
    bq = bigquery.Client(project=PROJECT)
    now = datetime.now(JST)

    # ─── 1. データソース別 最新取得日 + 行数 ──────────────────────────────
    freshness = q(bq, """
    SELECT '受注/発送 (sales_daily)' AS src, MAX(sale_date) AS d,
           COUNT(*) AS n_total,
           COUNTIF(sale_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)) AS n_30d
    FROM `analytics_layer.sales_daily` WHERE sale_date >= '2025-01-01'
    UNION ALL SELECT '倉庫在庫 (inventory)', MAX(snapshot_date),
           COUNT(*), COUNTIF(snapshot_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY))
    FROM `analytics_layer.inventory_snapshot` WHERE snapshot_date >= '2025-01-01'
    UNION ALL SELECT '在庫分析 (stock_analysis)', MAX(snapshot_date),
           COUNT(*), COUNTIF(snapshot_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY))
    FROM `analytics_layer.stock_analysis` WHERE snapshot_date >= '2025-01-01'
    UNION ALL SELECT '予約管理一覧 (reservations)', MAX(reservation_date),
           COUNT(*), COUNTIF(reservation_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY))
    FROM `analytics_layer.reservations` WHERE reservation_date >= '2025-01-01'
    UNION ALL SELECT '入荷残 (incoming_stock)', MAX(source_date),
           COUNT(*), COUNTIF(source_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY))
    FROM `analytics_layer.incoming_stock` WHERE source_date >= '2025-01-01'
    UNION ALL SELECT 'MMS原価 (cost_master)', MAX(valid_from),
           COUNT(*), COUNTIF(valid_from >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY))
    FROM `analytics_layer.cost_master`
    UNION ALL SELECT '商品マスタ (product_master)', CURRENT_DATE(),
           COUNT(*), COUNT(*)
    FROM `analytics_layer.product_master`
    UNION ALL SELECT 'セール設定 (sale_settings)', MAX(snapshot_date),
           COUNT(*), COUNTIF(snapshot_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY))
    FROM `analytics_layer.sale_settings` WHERE snapshot_date >= '2025-01-01'
    UNION ALL SELECT '発注管理表マート (mart_order_analysis)', MAX(analysis_date),
           COUNT(*), COUNTIF(analysis_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY))
    FROM `mart_layer.order_analysis` WHERE analysis_date >= '2025-01-01'
    UNION ALL SELECT 'ZOZOAD実績 (zozoad_daily)', MAX(record_date),
           COUNT(*), COUNTIF(record_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY))
    FROM `analytics_layer.zozoad_daily` WHERE record_date >= '2025-01-01'
    UNION ALL SELECT 'クーポン除外 (coupon_exclusion)', MAX(exclusion_date),
           COUNT(*), COUNTIF(exclusion_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY))
    FROM `analytics_layer.coupon_exclusion` WHERE exclusion_date >= '2025-01-01'
    UNION ALL SELECT '検索キーワード経由 (search_keyword_daily)', MAX(record_date),
           COUNT(*), COUNTIF(record_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY))
    FROM `analytics_layer.search_keyword_daily` WHERE record_date >= '2025-01-01'
    UNION ALL SELECT 'アクセス実績 (access_log_daily)', MAX(record_date),
           COUNT(*), COUNTIF(record_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY))
    FROM `analytics_layer.access_log_daily` WHERE record_date >= '2025-01-01'
    UNION ALL SELECT '商品レビュー (product_reviews)', MAX(review_date),
           COUNT(*), COUNTIF(review_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY))
    FROM `analytics_layer.product_reviews` WHERE review_date >= '2025-01-01'
    UNION ALL SELECT 'sitateru商品マスタ (sitateru_item_master)', MAX(snapshot_date),
           COUNT(*), COUNTIF(snapshot_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY))
    FROM `analytics_layer.sitateru_item_master` WHERE snapshot_date >= '2025-01-01'
    ORDER BY src
    """)

    # ─── 2. 最新Martの公式整合性 ──────────────────────────────────────────
    integrity = q(bq, """
    WITH latest AS (SELECT MAX(analysis_date) AS d FROM `mart_layer.order_analysis`)
    SELECT
      (SELECT d FROM latest) AS d,
      COUNT(*) AS total_skus,
      COUNTIF(free_inventory = inventory + incoming_stock - reservations_pending) AS formula_ok,
      COUNTIF(free_inventory < 0) AS negative_free,
      COUNTIF(cost_price IS NOT NULL) AS has_cost,
      ROUND(AVG(gross_margin_pct), 1) AS avg_margin
    FROM `mart_layer.order_analysis`, latest
    WHERE analysis_date = (SELECT d FROM latest)
    """)[0]

    # ─── 3. 緊急度別 SKU数 ────────────────────────────────────────────────
    urgency = q(bq, """
    WITH latest AS (SELECT MAX(analysis_date) AS d FROM `mart_layer.order_analysis`)
    SELECT order_urgency, COUNT(*) AS n
    FROM `mart_layer.order_analysis`, latest
    WHERE analysis_date = (SELECT d FROM latest)
    GROUP BY order_urgency
    ORDER BY CASE order_urgency
      WHEN 'CRITICAL' THEN 1 WHEN 'WARNING' THEN 2
      WHEN 'OK' THEN 3 WHEN 'OVERSTOCK' THEN 4 ELSE 5 END
    """)

    # ─── 4. テスト10品番のサマリ ──────────────────────────────────────────
    test_skus = q(bq, """
    WITH latest AS (SELECT MAX(analysis_date) AS d FROM `mart_layer.order_analysis`),
    pm AS (
      SELECT product_code, sku_code, ANY_VALUE(shop_name) AS shop_name
      FROM `analytics_layer.product_master` GROUP BY product_code, sku_code
    )
    SELECT
      o.product_code, ANY_VALUE(o.product_name) AS product_name,
      ANY_VALUE(pm.shop_name) AS shop,
      COUNT(*) AS sku_count,
      SUM(o.inventory) AS inv, SUM(o.incoming_stock) AS inc,
      SUM(o.reservations_pending) AS res, SUM(o.free_inventory) AS free_inv,
      SUM(o.sales_30d) AS sales_30d,
      SUM(o.recommended_order_qty) AS rec,
      ROUND(AVG(o.gross_margin_pct), 1) AS margin
    FROM `mart_layer.order_analysis` o, latest
    LEFT JOIN pm ON pm.product_code = o.product_code AND pm.sku_code = o.sku_code
    WHERE o.analysis_date = (SELECT d FROM latest)
      AND o.product_code IN UNNEST(@skus)
    GROUP BY o.product_code
    ORDER BY o.product_code
    """, params=[bigquery.ArrayQueryParameter("skus", "STRING", SKU_TEST_LIST)])

    # ─── 5. ファーストセラー最新取得情報 ──────────────────────────────────
    fs_blob_info = None
    try:
        sc = storage.Client(project=PROJECT)
        bkt = sc.bucket("mono-back-office-system-raw-data")
        blobs = sorted(sc.list_blobs(bkt, prefix="uploads/zozo/first_seller/"),
                       key=lambda b: b.updated, reverse=True)
        if blobs:
            fs_blob_info = {"name": blobs[0].name,
                            "updated": blobs[0].updated.astimezone(JST),
                            "size": blobs[0].size}
    except Exception:
        pass

    # ─── HTML レンダリング ───────────────────────────────────────────────
    def fmt_num(n):
        return f"{n:,}" if n is not None else "-"
    def fmt_date(d):
        return d.isoformat() if d else "-"

    css = """
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Meiryo, sans-serif;
           margin: 0; padding: 24px; background: #f7f8fa; color: #1f2937; }
    h1 { color: #111827; font-size: 24px; margin: 0 0 4px; }
    .meta { color: #6b7280; font-size: 13px; margin-bottom: 24px; }
    .card { background: white; border-radius: 8px; padding: 20px;
            margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
    .card h2 { font-size: 16px; margin: 0 0 12px; color: #111827; border-bottom: 2px solid #e5e7eb; padding-bottom: 8px; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th { text-align: left; padding: 8px 10px; background: #f3f4f6; color: #4b5563; font-weight: 600; }
    td { padding: 8px 10px; border-top: 1px solid #f3f4f6; }
    td.num { text-align: right; font-variant-numeric: tabular-nums; }
    .ok { color: #059669; font-weight: 600; }
    .warn { color: #d97706; font-weight: 600; }
    .ng { color: #dc2626; font-weight: 600; }
    .badge { display: inline-block; padding: 2px 8px; border-radius: 4px;
             font-size: 11px; font-weight: 600; }
    .badge-CRITICAL { background: #fee2e2; color: #dc2626; }
    .badge-WARNING  { background: #fef3c7; color: #d97706; }
    .badge-OK       { background: #d1fae5; color: #059669; }
    .badge-OVERSTOCK { background: #dbeafe; color: #2563eb; }
    .footer { color: #6b7280; font-size: 12px; text-align: center; margin-top: 24px; }
    """

    def freshness_status_class(d, src):
        if not d:
            return "ng"
        today = datetime.now(JST).date()
        age = (today - d).days
        # Looker ダッシュボード系 (rpid=9/11): 日付フィルタ既定が「前週」のため、
        # 最新 record_date は常に「先週日曜」≈ 2-8日前で正常 (8日超は要警戒)
        if "検索キーワード経由" in src or "アクセス実績" in src:
            return "ok" if age <= 8 else ("warn" if age <= 14 else "ng")
        # ZOZOAD: ZOZO BO が広告実績を ~2-3 日遅延で公開するため、T-3 まで正常
        if "ZOZOAD" in src:
            return "ok" if age <= 4 else ("warn" if age <= 7 else "ng")
        # 商品レビュー: 日次差分 (該当日 0 件もよくある) — 厳しすぎる閾値は不適
        if "商品レビュー" in src or "product_reviews" in src:
            return "ok" if age <= 7 else ("warn" if age <= 30 else "ng")
        # クーポン除外: クーポン施策日のみ更新 (未実施日は据え置き)
        if "クーポン除外" in src:
            return "ok" if age <= 7 else ("warn" if age <= 14 else "ng")
        # マスタ系: 商品マスタは毎日更新、MMS/セールも日次
        if "商品マスタ" in src or "MMS" in src or "セール" in src:
            return "ok" if age <= 2 else ("warn" if age <= 7 else "ng")
        # sitateru: 不定期 (運用上、週次以上の頻度はない想定)
        if "sitateru" in src:
            return "ok" if age <= 14 else ("warn" if age <= 30 else "ng")
        # その他 (日次必須): 受注/在庫/予約/分析マート
        return "ok" if age <= 2 else ("warn" if age <= 5 else "ng")

    parts = []
    parts.append(f"<!DOCTYPE html><html lang='ja'><head><meta charset='utf-8'>"
                 f"<title>MONO BACK OFFICE - データ確認画面</title>"
                 f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
                 f"<style>{css}</style></head><body>")
    parts.append(f"<h1>📊 MONO BACK OFFICE — 簡易データ確認画面</h1>")
    parts.append(f"<div class='meta'>レポート生成: {now.strftime('%Y-%m-%d %H:%M:%S JST')}"
                 f" / プロジェクト: <code>{PROJECT}</code></div>")

    # 発注管理表 Excel ダウンロードリンク (latest stable URL)
    excel_url = ("https://storage.googleapis.com/mono-back-office-system-exports"
                 "/order_management/latest/%E7%99%BA%E6%B3%A8%E7%AE%A1%E7%90%86%E8%A1%A8.xlsx")
    parts.append(
        f"<div class='card' style='border-left:4px solid #2563eb;'>"
        f"<h2 style='margin:0 0 8px;'>📥 発注管理表 (最新版)</h2>"
        f"<p style='margin:0 0 12px;color:#475467;font-size:13px;'>"
        f"毎朝 07:00 JST に最新データで再生成されます。経営者サマリ + 23 列 SKU 詳細 + 緊急度別集計の 3 シート構成。"
        f"</p>"
        f"<a href='{excel_url}' "
        f"style='display:inline-block;padding:10px 18px;background:#2563eb;color:white;"
        f"border-radius:6px;text-decoration:none;font-weight:600;font-size:14px;'>"
        f"📊 発注管理表.xlsx をダウンロード</a>"
        f"</div>"
    )

    # Card 1: データ取得状況
    parts.append("<div class='card'><h2>1. データソース別 取得状況</h2><table>")
    parts.append("<tr><th>データソース</th><th>最新取得日</th><th class='num'>全期間 行数</th><th class='num'>直近30日 行数</th><th>状態</th></tr>")
    for r in freshness:
        st = freshness_status_class(r.d, r.src)
        st_label = {"ok": "✅ 正常", "warn": "⚠ 注意", "ng": "❌ 古い"}.get(st, "-")
        parts.append(f"<tr><td>{html.escape(r.src)}</td>"
                     f"<td>{fmt_date(r.d)}</td>"
                     f"<td class='num'>{fmt_num(r.n_total)}</td>"
                     f"<td class='num'>{fmt_num(r.n_30d)}</td>"
                     f"<td class='{st}'>{st_label}</td></tr>")
    parts.append("</table></div>")

    # Card 2: 発注判断マートの品質
    parts.append("<div class='card'><h2>2. 発注判断マートの品質チェック</h2>")
    formula_pct = (integrity.formula_ok / integrity.total_skus * 100
                   if integrity.total_skus else 0)
    cost_pct = (integrity.has_cost / integrity.total_skus * 100
                if integrity.total_skus else 0)
    parts.append(f"<div style='display:grid; grid-template-columns: repeat(4, 1fr); gap: 12px;'>")
    parts.append(f"<div><div class='meta'>対象日</div><div style='font-size:18px; font-weight:600'>{fmt_date(integrity.d)}</div></div>")
    parts.append(f"<div><div class='meta'>SKU数</div><div style='font-size:18px; font-weight:600'>{fmt_num(integrity.total_skus)}</div></div>")
    formula_cls = "ok" if formula_pct == 100 else "warn"
    parts.append(f"<div><div class='meta'>公式整合性</div><div style='font-size:18px; font-weight:600' class='{formula_cls}'>{formula_pct:.2f}%</div></div>")
    parts.append(f"<div><div class='meta'>原価カバー率</div><div style='font-size:18px; font-weight:600'>{cost_pct:.1f}%</div></div>")
    parts.append(f"</div><p class='meta' style='margin-top:12px'>"
                 f"※ 公式整合性 = フリー在庫が「在庫+入荷残−予約未処理」と一致するSKUの割合<br>"
                 f"※ フリー在庫マイナス = {integrity.negative_free} SKU (欠品リスクシグナル)<br>"
                 f"※ 平均粗利率 = {integrity.avg_margin}%</p></div>")

    # Card 3: 緊急度別
    parts.append("<div class='card'><h2>3. 緊急度別 SKU数 (発注判断)</h2><table>")
    parts.append("<tr><th>緊急度</th><th class='num'>SKU数</th></tr>")
    for r in urgency:
        cls = f"badge-{r.order_urgency}" if r.order_urgency else ""
        parts.append(f"<tr><td><span class='badge {cls}'>{r.order_urgency or '(未分類)'}</span></td>"
                     f"<td class='num'>{fmt_num(r.n)}</td></tr>")
    parts.append("</table></div>")

    # Card 4: テスト10品番
    parts.append("<div class='card'><h2>4. テスト10品番の数値検証</h2><table>")
    parts.append("<tr><th>品番</th><th>ショップ</th><th class='num'>SKU</th>"
                 "<th class='num'>在庫</th><th class='num'>入荷残</th>"
                 "<th class='num'>予約未処理</th><th class='num'>フリー在庫</th>"
                 "<th class='num'>30日販売</th><th class='num'>推奨発注</th>"
                 "<th class='num'>粗利率</th></tr>")
    for r in test_skus:
        margin_str = f"{r.margin}%" if r.margin else "-"
        parts.append(f"<tr><td><code>{html.escape(r.product_code)}</code></td>"
                     f"<td>{html.escape(r.shop or '-')}</td>"
                     f"<td class='num'>{fmt_num(r.sku_count)}</td>"
                     f"<td class='num'>{fmt_num(r.inv)}</td>"
                     f"<td class='num'>{fmt_num(r.inc)}</td>"
                     f"<td class='num'>{fmt_num(r.res)}</td>"
                     f"<td class='num'>{fmt_num(r.free_inv)}</td>"
                     f"<td class='num'>{fmt_num(r.sales_30d)}</td>"
                     f"<td class='num'>{fmt_num(r.rec)}</td>"
                     f"<td class='num'>{margin_str}</td></tr>")
    parts.append("</table></div>")

    # Card 5: ファーストセラー
    parts.append("<div class='card'><h2>5. ファーストセラー (週次取得) 状況</h2>")
    if fs_blob_info:
        parts.append(f"<p>最新取得ファイル: <code>{html.escape(fs_blob_info['name'])}</code><br>"
                     f"取得日時: {fs_blob_info['updated'].strftime('%Y-%m-%d %H:%M JST')}<br>"
                     f"ファイルサイズ: {fmt_num(fs_blob_info['size'])} bytes</p>")
    else:
        parts.append("<p class='warn'>まだファーストセラーは取得されていません (毎週月曜 03:00 JST に取得)</p>")
    parts.append("</div>")

    parts.append(f"<div class='footer'>MONO BACK OFFICE Phase 1 — Generated automatically by run_daily.ps1</div>")
    parts.append("</body></html>")

    html_str = "\n".join(parts)

    # ─── GCS にアップロード (Public Read) ─────────────────────────────────
    sc = storage.Client(project=PROJECT)
    bkt = sc.bucket(EXPORTS_BUCKET)
    blob = bkt.blob(REPORT_PATH)
    blob.upload_from_string(html_str, content_type="text/html; charset=utf-8")
    try:
        blob.make_public()
    except Exception as e:
        print(f"public access not enabled: {e}")
    public_url = blob.public_url
    print(f"✓ Report uploaded: {public_url}")
    print(f"  ({len(html_str):,} bytes)")
    return 0


if __name__ == "__main__":
    main()
