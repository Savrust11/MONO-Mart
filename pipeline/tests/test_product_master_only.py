"""Quick test: parse + load goods_cs.csv only."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from extractors.zozo_csv_extractor import ZOZOCsvExtractor
from loaders.bigquery_loader import BigQueryLoader
from google.cloud import storage

print('Downloading goods_cs.csv from GCS...')
client = storage.Client(project='mono-back-office-system')
bucket = client.bucket('mono-back-office-system-raw-data')
blob = bucket.blob('uploads/zozo/product_master/2026-05-05/goods_cs.csv')
data = blob.download_as_bytes()
print(f'Downloaded {len(data):,} bytes')

print('Parsing...')
z = ZOZOCsvExtractor()
rows = z.parse_product_master(data)
print(f'Parsed {len(rows):,} rows')

# Inspect barcode types
barcode_types = set(type(r.get('barcode')).__name__ for r in rows[:1000])
print(f'Barcode types in first 1000 rows: {barcode_types}')

# Find any non-string or weird barcodes
weird = [r['barcode'] for r in rows[:5000] if r.get('barcode') and ('/' in str(r.get('barcode')) or '"' in str(r.get('barcode')))]
print(f'Sample weird barcodes (first 3): {weird[:3]}')

print('Loading to BQ...')
bq = BigQueryLoader()
bq.upsert_product_master(rows)
print('Done!')
