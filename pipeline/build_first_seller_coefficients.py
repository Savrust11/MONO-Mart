"""ファーストセラー由来の52週季節係数を構築（顧客#14）。

GCSの first_seller CSV を全件 → analytics_layer.first_seller_weekly にロードし、
product_master と品番で結合して child_item_type を補完、gender×商品タイプ子×ISO週で
販売数を集計 → seasonal_coefficients を再構築する。

Usage:  python build_first_seller_coefficients.py [TARGET_TABLE] [MIN_WEEKS]
  TARGET_TABLE  出力先（既定 seasonal_coefficients）。検証時は別名にして本番を汚さない。
  MIN_WEEKS     係数化に必要な最小週数（既定 40）。検証時は小さく。
"""
import sys, csv, io, re
from google.cloud import storage, bigquery

PROJECT = "mono-back-office-system"
A = f"{PROJECT}.analytics_layer"
BKT = "mono-back-office-system-raw-data"
TARGET = sys.argv[1] if len(sys.argv) > 1 else "seasonal_coefficients"
MIN_WEEKS = int(sys.argv[2]) if len(sys.argv) > 2 else 40

sc = storage.Client(project=PROJECT)
bq = bigquery.Client(project=PROJECT)


def num(s):
    s = re.sub(r"[¥,円\s]", "", str(s or ""))
    try:
        return int(float(s))
    except ValueError:
        return 0


# 1) GCSの first_seller CSV を全件パース
rows = []
for b in sc.list_blobs(BKT, prefix="uploads/zozo/first_seller/"):
    if not b.name.endswith(".csv"):
        continue
    txt = b.download_as_bytes().decode("utf-8", "replace")
    for d in csv.DictReader(io.StringIO(txt)):
        d = {k.replace("﻿", ""): v for k, v in d.items()}
        rows.append({
            "iso_year": num(d.get("iso_year")),
            "iso_week": num(d.get("iso_week")),
            "gender": (d.get("gender") or "").strip(),
            "product_code": (d.get("ブランド品番") or "").strip(),
            "units": num(d.get("販売数")),
        })
print(f"parsed {len(rows)} first_seller rows from GCS")

# 2) BigQuery にロード（WRITE_TRUNCATE）
tbl = f"{A}.first_seller_weekly"
bq.load_table_from_json(rows, tbl, job_config=bigquery.LoadJobConfig(
    write_disposition="WRITE_TRUNCATE",
    schema=[bigquery.SchemaField("iso_year", "INT64"), bigquery.SchemaField("iso_week", "INT64"),
            bigquery.SchemaField("gender", "STRING"), bigquery.SchemaField("product_code", "STRING"),
            bigquery.SchemaField("units", "INT64")],
)).result()
weeks = list(bq.query(f"SELECT COUNT(DISTINCT iso_week) w FROM `{tbl}`"))[0]["w"]
print(f"loaded -> {tbl}  (distinct ISO weeks = {weeks})")

# 3) gender×商品タイプ子×ISO週で集計 → 季節係数（平均週=1.0）
bq.query(f"""
CREATE OR REPLACE TABLE `{A}.{TARGET}` AS
WITH pm AS (
  SELECT UPPER(TRIM(product_code)) pc, ANY_VALUE(child_item_type) ct
  FROM `{A}.product_master`
  WHERE child_item_type IS NOT NULL AND child_item_type!='' GROUP BY pc),
fs AS (
  -- 年をまたぐ同一ISO週(例 W25が2025/2026)は平均して二重計上を防ぐ
  SELECT gender, child_item_type, week_number, AVG(yr_units) units
  FROM (
    SELECT f.gender, pm.ct AS child_item_type, f.iso_week AS week_number, f.iso_year, SUM(f.units) yr_units
    FROM `{tbl}` f JOIN pm ON UPPER(TRIM(f.product_code))=pm.pc
    WHERE f.gender IN ('MEN','WOMEN') GROUP BY 1,2,3,4)
  GROUP BY 1,2,3),
cat AS (
  SELECT gender, child_item_type, AVG(units) avg_u
  FROM fs GROUP BY 1,2 HAVING COUNT(*) >= {MIN_WEEKS} AND SUM(units) >= 100)
SELECT f.gender, f.child_item_type, f.week_number,
       ROUND(SAFE_DIVIDE(f.units, c.avg_u),3) AS coefficient,
       f.units AS week_qty, CURRENT_TIMESTAMP() AS updated_at
FROM fs f JOIN cat c USING(gender, child_item_type)
ORDER BY gender, child_item_type, week_number
""").result()
r = list(bq.query(f"SELECT COUNT(*) n, COUNT(DISTINCT CONCAT(gender,child_item_type)) cats FROM `{A}.{TARGET}`"))[0]
print(f"built {A}.{TARGET}: {r['n']} rows / {r['cats']} categories (MIN_WEEKS={MIN_WEEKS})")
