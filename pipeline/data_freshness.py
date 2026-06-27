"""データ鮮度ダッシュボード: 各データ源が「何日まで来ているか」「何日遅れか」を一覧化。
Xサーバ(ZOZO IPロック)の取得停止箇所を可視化するための監視ツール。毎回再実行可。
"""
from datetime import date
from google.cloud import bigquery

PROJECT = "mono-back-office-system"
A = f"{PROJECT}.analytics_layer"
bq = bigquery.Client(project=PROJECT)

# (表示名, テーブル, 日付列, 追加条件, 想定ラグ日数=これを超えたら警告)
SOURCES = [
    ("受注 (orders)",              "sales_daily",          "sale_date",        "source_file='orders'",      2),
    ("商品別実績/UU (performance)", "sales_daily",          "sale_date",        "source_file='performance'", 3),
    ("出荷 (shipped)",             "sales_daily",          "sale_date",        "source_file='shipped'",     3),
    ("在庫スナップショット",        "inventory_snapshot",   "snapshot_date",    None,                        2),
    ("在庫分析 (お気に等)",         "stock_analysis",       "snapshot_date",    None,                        2),
    ("入荷残",                     "incoming_stock",       "source_date",      None,                        3),
    ("予約管理",                   "reservations",         "reservation_date", None,                        3),
    ("MMS発注書一覧",              "mms_orders",           "snapshot_date",    None,                        7),
    ("MMS評価額 (原価)",           "cost_master",          "updated_date",     None,                        7),
    ("PF手数料表",                 "pf_fee_master",        "snapshot_date",    None,                        7),
    ("sitateru",                  "sitateru_item_master", "snapshot_date",    None,                        7),
    ("アクセスログ",               "access_log_daily",     "record_date",      None,                        3),
]


def run():
    today = list(bq.query("SELECT CURRENT_DATE() d"))[0]["d"]
    rows = []
    for name, tbl, col, cond, lag in SOURCES:
        where = f"WHERE {cond}" if cond else ""
        try:
            r = list(bq.query(
                f"SELECT CAST(DATE(MAX({col})) AS STRING) d, COUNT(*) n FROM `{A}.{tbl}` {where}"
            ))[0]
            latest = r["d"]
            n = r["n"]
            behind = (today - date.fromisoformat(latest)).days if latest else None
        except Exception as e:
            latest, n, behind = f"ERR:{str(e)[:30]}", 0, None
        rows.append((name, latest, behind, n, lag))

    # 遅れの大きい順
    rows.sort(key=lambda x: (x[2] is None, -(x[2] or 0)))
    print(f"=== データ鮮度ダッシュボード（基準日 {today}）===\n")
    print(f"{'データ源':<26} {'最新日':<12} {'遅れ':>6}  {'件数':>10}  判定")
    print("-" * 72)
    for name, latest, behind, n, lag in rows:
        if behind is None:
            mark = "❓"
        elif behind <= lag:
            mark = "✅ 正常"
        elif behind <= lag + 4:
            mark = "⚠️ 遅延"
        else:
            mark = "🛑 停止の疑い"
        bstr = f"{behind}日" if behind is not None else "—"
        print(f"{name:<26} {str(latest):<12} {bstr:>6}  {n:>10,}  {mark}")
    print("\n（遅れ＝基準日−最新日。想定ラグを超えると⚠️、大幅超過で🛑＝取得停止の疑い）")


if __name__ == "__main__":
    run()
