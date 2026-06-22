from google.cloud import bigquery
c = bigquery.Client(project="mono-back-office-system")

print("=== product_master: カラー違いの行（コード系フィールド）===")
for r in c.query("""
SELECT sku_code, color_name, size, item_code, goods_detail_id, barcode
FROM `analytics_layer.product_master`
WHERE UPPER(TRIM(product_code))='SC1032'
ORDER BY color_name, size LIMIT 12""").result():
    print(f"  色={str(r.color_name)[:10]:<10} size={str(r.size):<5} item_code={r.item_code} goods_detail_id={r.goods_detail_id} barcode={r.barcode}")

print("\n=== mart order_analysis: color_code / maker_color_code があるか ===")
try:
    for r in c.query("""
    SELECT DISTINCT color_name, color_code, maker_color_code
    FROM `mart_layer.order_analysis`
    WHERE UPPER(TRIM(product_code))='SC1032' AND analysis_date=(SELECT MAX(analysis_date) FROM `mart_layer.order_analysis`)
    ORDER BY color_name LIMIT 12""").result():
        print(f"  色={str(r.color_name)[:12]:<12} color_code={r.color_code}  maker_color_code={r.maker_color_code}")
except Exception as e: print("  失敗", str(e)[:80])

print("\n=== sales_daily: item_code 等（受注CSV側のコード）===")
for r in c.query("""
SELECT DISTINCT color_name, item_code
FROM `analytics_layer.sales_daily`
WHERE product_code='sc1032' AND source_file='orders' AND item_code IS NOT NULL
ORDER BY color_name LIMIT 12""").result():
    print(f"  色={str(r.color_name)[:12]:<12} item_code={r.item_code}")
