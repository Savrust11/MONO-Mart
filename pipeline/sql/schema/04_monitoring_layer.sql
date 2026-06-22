-- =============================================================================
-- MONITORING LAYER: Pipeline execution audit + data quality tracking
-- =============================================================================

-- Pipeline run audit log (written by monitoring.py)
CREATE TABLE IF NOT EXISTS `monitoring.pipeline_runs` (
  run_id          STRING    NOT NULL OPTIONS(description="UUID for the pipeline run"),
  run_date        DATE      NOT NULL OPTIONS(description="Business date being processed"),
  step            STRING    NOT NULL OPTIONS(description="Pipeline step name"),
  status          STRING    NOT NULL OPTIONS(description="running | success | failed"),
  rows_processed  INT64              OPTIONS(description="Number of records processed"),
  duration_ms     INT64              OPTIONS(description="Step duration in milliseconds"),
  started_at      TIMESTAMP NOT NULL OPTIONS(description="UTC step start time"),
  finished_at     TIMESTAMP          OPTIONS(description="UTC step end time"),
  error_message   STRING             OPTIONS(description="Error details if failed")
)
PARTITION BY DATE(started_at)
CLUSTER BY run_date, step
OPTIONS(
  require_partition_filter = false,
  description = "Per-step execution log for every pipeline run"
);

-- Data quality check results (written by validators/data_validator.py)
CREATE TABLE IF NOT EXISTS `monitoring.data_quality_checks` (
  run_date         DATE      NOT NULL OPTIONS(description="Business date being validated"),
  dataset          STRING    NOT NULL OPTIONS(description="Source dataset name (e.g. zozo_sales)"),
  row_count        INT64     NOT NULL OPTIONS(description="Number of records validated"),
  total_checks     INT64     NOT NULL OPTIONS(description="Total number of checks run"),
  passed_checks    INT64     NOT NULL OPTIONS(description="Number of checks that passed"),
  failed_checks    INT64     NOT NULL OPTIONS(description="Number of checks that failed"),
  passed           BOOL      NOT NULL OPTIONS(description="True if all checks passed"),
  validated_at     TIMESTAMP NOT NULL OPTIONS(description="UTC time of validation"),
  failures_json    STRING             OPTIONS(description="JSON array of failed check details"),
  all_checks_json  STRING             OPTIONS(description="JSON array of all check results")
)
PARTITION BY run_date
CLUSTER BY dataset
OPTIONS(
  require_partition_filter = false,
  description = "Data quality check results per extraction step per day"
);

-- ZOZO scraping run audit log — one row per source per run
CREATE TABLE IF NOT EXISTS `monitoring.scraping_runs` (
  run_id        STRING    NOT NULL OPTIONS(description="UUID of this scraper run"),
  run_date      DATE      NOT NULL OPTIONS(description="Target business date"),
  source_name   STRING    NOT NULL OPTIONS(description="orders / shipped / ... / sale_settings"),
  source_label  STRING             OPTIONS(description="Human-friendly label"),
  status        STRING             OPTIONS(description="ok / failed / skipped"),
  filename      STRING             OPTIONS(description="Downloaded filename"),
  size_bytes    INT64              OPTIONS(description="Downloaded file size"),
  gcs_path      STRING             OPTIONS(description="gs:// upload destination"),
  error_message STRING             OPTIONS(description="Truncated error if failed"),
  started_at    TIMESTAMP NOT NULL,
  finished_at   TIMESTAMP
)
PARTITION BY run_date
CLUSTER BY source_name, status
OPTIONS(description="Per-source ZOZO scraping run log. Powers dashboard 'data ingestion status' page.");

-- Table row count snapshots (for data freshness monitoring)
CREATE TABLE IF NOT EXISTS `monitoring.table_row_counts` (
  snapshot_date   DATE      NOT NULL OPTIONS(description="Date of snapshot"),
  dataset_name    STRING    NOT NULL OPTIONS(description="BigQuery dataset name"),
  table_name      STRING    NOT NULL OPTIONS(description="BigQuery table name"),
  partition_date  DATE               OPTIONS(description="Partition date if applicable"),
  row_count       INT64     NOT NULL OPTIONS(description="Number of rows in partition"),
  recorded_at     TIMESTAMP NOT NULL OPTIONS(description="UTC time of count")
)
PARTITION BY snapshot_date
OPTIONS(
  require_partition_filter = false,
  description = "Daily row count snapshots for all key tables"
);
