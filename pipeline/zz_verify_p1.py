from google.cloud import bigquery
c = bigquery.Client(project="mono-back-office-system")

print("=== 検証1：全オプションの列が入っているか (6/18) ===")
r=list(c.query("""SELECT COUNT(*) n,
  COUNTIF(favorites IS NOT NULL) fav, COUNTIF(barcode IS NOT NULL) bc, COUNTIF(arrival_date IS NOT NULL) arr
  FROM `analytics_layer.stock_analysis` WHERE snapshot_date='2026-06-18'""").result())[0]
print(f"  行数{r.n:,}  お気に入り{r.fav:,}  バーコード{r.bc:,}  最終入荷日{r.arr:,}")

print("\n=== 検証2：お気に入り数が日ごとに変わるか (前日分の証拠) ===")
print("  同じSKUの お気に入り数 を 6/16 / 6/17 / 6/18 で比較:")
q="""
WITH d AS (
  SELECT sku_code, snapshot_date, favorites
  FROM `analytics_layer.stock_analysis`
  WHERE snapshot_date IN ('2026-06-16','2026-06-17','2026-06-18') AND favorites > 0
)
SELECT sku_code,
  MAX(IF(snapshot_date='2026-06-16',favorites,NULL)) d16,
  MAX(IF(snapshot_date='2026-06-17',favorites,NULL)) d17,
  MAX(IF(snapshot_date='2026-06-18',favorites,NULL)) d18
FROM d GROUP BY sku_code
HAVING d16 IS NOT NULL AND d17 IS NOT NULL AND d18 IS NOT NULL
ORDER BY d18 DESC LIMIT 8
"""
for r in c.query(q).result():
    print(f"  {r.sku_code}: 6/16={r.d16}  6/17={r.d17}  6/18={r.d18}")

print("\n=== 検証3：お気に入り数の規模感 (前日分なら小さめ) ===")
r=list(c.query("""SELECT MIN(favorites) mn, MAX(favorites) mx, AVG(favorites) av
  FROM `analytics_layer.stock_analysis` WHERE snapshot_date='2026-06-18' AND favorites>0""").result())[0]
print(f"  非0のお気に入り数: 最小{r.mn} 最大{r.mx} 平均{r.av:.1f}")
