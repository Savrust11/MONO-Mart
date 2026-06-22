/**
 * GET /api/status
 * Returns pipeline run history, data quality results, and table row counts
 * from BigQuery monitoring tables.
 */
import { NextRequest, NextResponse } from 'next/server';
import { BigQuery } from '@google-cloud/bigquery';
import { todayJST } from '@/lib/utils';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

const PROJECT_ID       = process.env.GCP_PROJECT_ID!;
const DATASET_MONITORING = process.env.BQ_DATASET_MONITORING ?? 'monitoring';
const DATASET_RAW        = process.env.BQ_DATASET_RAW        ?? 'raw_layer';
const DATASET_ANALYTICS  = process.env.BQ_DATASET_ANALYTICS  ?? 'analytics_layer';
const DATASET_MART       = process.env.BQ_DATASET_MART       ?? 'mart_layer';
const LOCATION           = process.env.BQ_LOCATION           ?? 'asia-northeast1';

let _bq: BigQuery | null = null;
function bq() {
  if (!_bq) _bq = new BigQuery({ projectId: PROJECT_ID });
  return _bq;
}

const MOCK_URL = process.env.MOCK_API_URL;

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const date = searchParams.get('date') || todayJST();

  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
    return NextResponse.json({ error: 'Invalid date format.' }, { status: 400 });
  }

  if (MOCK_URL) {
    const resp = await fetch(`${MOCK_URL}/api/status?date=${date}`);
    const data = await resp.json();
    return NextResponse.json(data);
  }

  try {
    const [runsResult, qualityResult, countResult] = await Promise.all([
      fetchPipelineRuns(),
      fetchQualityChecks(date),
      fetchTableCounts(date),
    ]);

    const runs = runsResult as PipelineRun[];
    const latest = runs[0] ?? null;
    const failures = runs.filter(r => r.status === 'failed').length;

    return NextResponse.json({
      pipeline_runs:   groupRunsByDate(runs),
      quality_reports: qualityResult,
      table_counts:    countResult,
      summary: {
        last_run_date:    latest?.run_date ?? null,
        last_run_status:  latest?.status   ?? null,
        runs_last_7d:     runs.map(r => r.run_date).filter((v, i, a) => a.indexOf(v) === i).length,
        failures_last_7d: failures,
        generated_at:     new Date().toISOString(),
      },
    });
  } catch (err) {
    console.error('[api/status] Error:', err);
    return NextResponse.json({ error: 'Failed to fetch pipeline status.' }, { status: 500 });
  }
}

// ── Queries ───────────────────────────────────────────────────────────────────

interface PipelineRun {
  run_id: string;
  run_date: string;
  step: string;
  status: string;
  rows_processed: number | null;
  duration_ms: number | null;
  started_at: string;
  finished_at: string | null;
  error_message: string | null;
}

async function fetchPipelineRuns() {
  const [rows] = await bq().query({
    query: `
      SELECT
        run_id,
        FORMAT_DATE('%Y-%m-%d', run_date) AS run_date,
        step,
        status,
        rows_processed,
        duration_ms,
        FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', started_at)  AS started_at,
        FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', finished_at) AS finished_at,
        error_message
      FROM \`${PROJECT_ID}.${DATASET_MONITORING}.pipeline_runs\`
      WHERE run_date >= DATE_SUB(CURRENT_DATE('Asia/Tokyo'), INTERVAL 7 DAY)
        AND status != 'running'
      ORDER BY started_at DESC
      LIMIT 500
    `,
    location: LOCATION,
  });
  return rows;
}

async function fetchQualityChecks(date: string) {
  const [rows] = await bq().query({
    query: `
      SELECT
        FORMAT_DATE('%Y-%m-%d', run_date) AS run_date,
        dataset,
        row_count,
        total_checks,
        passed_checks,
        failed_checks,
        passed,
        FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', validated_at) AS validated_at,
        failures_json,
        all_checks_json
      FROM \`${PROJECT_ID}.${DATASET_MONITORING}.data_quality_checks\`
      WHERE run_date = @date
      ORDER BY dataset
    `,
    params: { date },
    location: LOCATION,
  });
  return rows;
}

async function fetchTableCounts(date: string) {
  // Query row counts for each key table partition
  const queries = [
    { dataset: DATASET_RAW,       table: 'zozo_sales_raw',          partition_col: 'source_date' },
    { dataset: DATASET_RAW,       table: 'zozo_inventory_raw',       partition_col: 'snapshot_date' },
    { dataset: DATASET_RAW,       table: 'sheets_reservations_raw',  partition_col: 'reservation_date' },
    { dataset: DATASET_ANALYTICS, table: 'sales_daily',              partition_col: 'sale_date' },
    { dataset: DATASET_ANALYTICS, table: 'inventory_snapshot',       partition_col: 'snapshot_date' },
    { dataset: DATASET_ANALYTICS, table: 'reservations',             partition_col: 'reservation_date' },
    { dataset: DATASET_ANALYTICS, table: 'cost_master',              partition_col: null },
    { dataset: DATASET_MART,      table: 'order_analysis',           partition_col: 'analysis_date' },
    { dataset: DATASET_MART,      table: 'reorder_alerts',           partition_col: 'analysis_date' },
  ];

  const results = await Promise.allSettled(
    queries.map(async ({ dataset, table, partition_col }) => {
      const where = partition_col ? `WHERE ${partition_col} = @date` : '';
      const [rows] = await bq().query({
        query: `SELECT COUNT(*) AS cnt FROM \`${PROJECT_ID}.${dataset}.${table}\` ${where}`,
        params: partition_col ? { date } : {},
        location: LOCATION,
      });
      return {
        dataset,
        table,
        row_count: Number((rows as Array<{ cnt: number }>)[0]?.cnt ?? 0),
        last_updated: date,
      };
    })
  );

  return results
    .filter((r): r is PromiseFulfilledResult<{ dataset: string; table: string; row_count: number; last_updated: string }> =>
      r.status === 'fulfilled'
    )
    .map(r => r.value);
}

// ── Group step rows into run objects ──────────────────────────────────────────

function groupRunsByDate(stepRows: PipelineRun[]) {
  const runMap = new Map<string, {
    run_id: string; run_date: string; status: string;
    total_ms: number; started_at: string; steps: PipelineRun[];
  }>();

  for (const row of stepRows) {
    if (!runMap.has(row.run_id)) {
      runMap.set(row.run_id, {
        run_id:     row.run_id,
        run_date:   row.run_date,
        status:     'success',
        total_ms:   0,
        started_at: row.started_at,
        steps:      [],
      });
    }
    const run = runMap.get(row.run_id)!;
    run.steps.push(row);
    run.total_ms += row.duration_ms ?? 0;
    if (row.status === 'failed') run.status = 'failed';
  }

  return Array.from(runMap.values()).sort(
    (a, b) => b.started_at.localeCompare(a.started_at)
  );
}
