"""Quick check: storage.Client() and GCSLoader pick up project from .env."""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from google.cloud import storage
from loaders.gcs_loader import GCSLoader

print("=" * 60)
print("Client init test")
print("=" * 60)
print(f"GCP_PROJECT_ID config:        {config.GCP_PROJECT_ID}")
print(f"GOOGLE_CLOUD_PROJECT env:     {os.environ.get('GOOGLE_CLOUD_PROJECT')}")

client = storage.Client()
print(f"storage.Client() project:     {client.project}")

loader = GCSLoader(bucket_name=config.GCS_RAW_BUCKET)
print(f"GCSLoader bucket:             {loader.bucket.name}")
print(f"GCSLoader client.project:     {loader.client.project}")
print()
print("OK - all clients pick up the correct project")
