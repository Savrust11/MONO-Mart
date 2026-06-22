import { NextRequest, NextResponse } from 'next/server';
import { BigQuery } from '@google-cloud/bigquery';

export const dynamic = 'force-dynamic';

const PROJECT  = process.env.GCP_PROJECT_ID || 'mono-back-office-system';
const LOCATION = process.env.BQ_LOCATION || 'asia-northeast1';

const SOURCE_CATALOG = [
  { name: 'orders',         label: '受注 (No.1)' },
  { name: 'shipped',        label: '発送 (No.2)' },
  { name: 'reservations',   label: '予約管理一覧 (No.3)' },
  { name: 'inventory_sku',  label: '倉庫在庫 SKU毎 (No.4)' },
  { name: 'stock_analysis', label: '在庫分析 (No.6)' },
  { name: 'zozoad',         label: 'ZOZOAD (No.7)' },
  { name: 'performance',    label: '商品別実績(新) (No.8)' },
  { name: 'product_master', label: '登録商品 (No.9)' },
  { name: 'sale_settings',  label: 'セール設定 (No.17)' },
];

const MOCK_URL = process.env.MOCK_API_URL;

export async function GET(req: NextRequest) {
  if (MOCK_URL) {
    const status = SOURCE_CATALOG.map(s => ({
      name:     s.name,
      label:    s.label,
      status:   'ok',
      filename: `${s.name}_2026-06-15.csv`,
      size:     null,
      gcs_path: null,
      error:    null,
      run_date: '2026-06-15',
      started:  '2026-06-15T17:05:00Z',
      finished: '2026-06-15T17:08:00Z',
    }));
    return NextResponse.json({
      sources:      status,
      summary:      { total: status.length, ok: status.length, failed: 0, no_data: 0 },
      window:       '7 days',
      generated_at: new Date().toISOString(),
    });
  }

  try {
    const days = Number(req.nextUrl.searchParams.get('days') || '7');
    const bq = new BigQuery({ projectId: PROJECT, location: LOCATION });

    // Latest run per source within the window
    const sql = `
      WITH ranked AS (
        SELECT
          source_name,
          source_label,
          run_date,
          status,
          filename,
          size_bytes,
          gcs_path,
          error_message,
          started_at,
          finished_at,
          ROW_NUMBER() OVER (PARTITION BY source_name ORDER BY started_at DESC) AS rn
        FROM \`${PROJECT}.monitoring.scraping_runs\`
        WHERE run_date >= DATE_SUB(CURRENT_DATE("Asia/Tokyo"), INTERVAL @days DAY)
      )
      SELECT * FROM ranked WHERE rn = 1
    `;

    const [job] = await bq.createQueryJob({
      query: sql,
      location: LOCATION,
      params: { days },
    });
    const [rows] = await job.getQueryResults();

    // Merge with catalog so missing sources show as "no data"
    const byName: Record<string, any> = {};
    rows.forEach((r: any) => { byName[r.source_name] = r; });

    const status = SOURCE_CATALOG.map(s => {
      const row = byName[s.name];
      return {
        name:     s.name,
        label:    s.label,
        status:   row?.status        ?? 'no_data',
        filename: row?.filename      ?? null,
        size:     row?.size_bytes    ?? null,
        gcs_path: row?.gcs_path      ?? null,
        error:    row?.error_message ?? null,
        run_date: row?.run_date?.value ?? null,
        started:  row?.started_at?.value ?? null,
        finished: row?.finished_at?.value ?? null,
      };
    });

    // Aggregate stats
    const ok      = status.filter(s => s.status === 'ok').length;
    const failed  = status.filter(s => s.status === 'failed').length;
    const noData  = status.filter(s => s.status === 'no_data').length;

    return NextResponse.json({
      sources:  status,
      summary:  { total: status.length, ok, failed, no_data: noData },
      window:   `${days} days`,
      generated_at: new Date().toISOString(),
    });
  } catch (err: any) {
    return NextResponse.json({ error: err.message || String(err) }, { status: 500 });
  }
}
