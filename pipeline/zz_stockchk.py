from google.cloud import bigquery
c = bigquery.Client(project="mono-back-office-system")
# 最新スナップショットで、全オプション由来の列が埋まっているか
r=list(c.query("""
SELECT snapshot_date,
  COUNT(*) n,
  COUNTIF(favorites IS NOT NULL) fav_notnull, COUNTIF(favorites>0) fav_pos,
  COUNTIF(arrival_date IS NOT NULL AND arrival_date!='') arr,
  COUNTIF(barcode IS NOT NULL AND barcode!='') bc
FROM `analytics_layer.stock_analysis`
WHERE snapshot_date=(SELECT MAX(snapshot_date) FROM `analytics_layer.stock_analysis`)
GROUP BY snapshot_date""").result())[0]
print(f"最新在庫分析 snapshot={r.snapshot_date}  行数={r.n:,}")
print(f"  お気に入り(非NULL)={r.fav_notnull:,}  お気に入り>0={r.fav_pos:,}")
print(f"  最終入荷日あり={r.arr:,}  バーコードあり={r.bc:,}")

# 直近の取得日が前日まで来ているか（日次が回っているか）
print("\n=== 在庫分析の直近スナップショット日 ===")
for row in c.query("""SELECT snapshot_date, COUNT(*) n FROM `analytics_layer.stock_analysis`
  GROUP BY snapshot_date ORDER BY snapshot_date DESC LIMIT 6""").result():
    print(f"  {row.snapshot_date}: {row.n:,}行")
