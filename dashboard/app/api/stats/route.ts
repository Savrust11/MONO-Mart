import { NextResponse } from 'next/server';
import { BigQuery } from '@google-cloud/bigquery';

export const dynamic = 'force-dynamic';

const PROJECT  = process.env.GCP_PROJECT_ID || 'mono-back-office-system';
const ANALYTICS = process.env.BQ_DATASET_ANALYTICS || 'analytics_layer';
const MART     = process.env.BQ_DATASET_MART || 'mart_layer';
const LOCATION = process.env.BQ_LOCATION || 'asia-northeast1';
const MOCK_URL = process.env.MOCK_API_URL;

export async function GET() {
  if (MOCK_URL) {
    const resp = await fetch(`${MOCK_URL}/api/products`);
    const { data } = await resp.json();
    const rows = Array.isArray(data) ? data : [];
    const products = new Set(rows.map((r: any) => r.product_code));
    return NextResponse.json({
      total_products:  products.size,
      total_skus:      rows.length,
      total_inventory: rows.reduce((s: number, r: any) => s + (r.inventory ?? 0), 0),
      critical_count:  rows.filter((r: any) => r.order_urgency === 'CRITICAL').length,
      warning_count:   rows.filter((r: any) => r.order_urgency === 'WARNING').length,
    });
  }

  try {
    const bq = new BigQuery({ projectId: PROJECT, location: LOCATION });

    const sql = `
      SELECT
        (SELECT COUNT(DISTINCT product_code) FROM \`${PROJECT}.${ANALYTICS}.product_master\` WHERE product_code IS NOT NULL) AS total_products,
        (SELECT COUNT(*)  FROM \`${PROJECT}.${ANALYTICS}.product_master\`)                                  AS total_skus,
        (SELECT IFNULL(SUM(stock_quantity), 0) FROM \`${PROJECT}.${ANALYTICS}.inventory_snapshot\`)         AS total_inventory,
        (SELECT COUNT(*)  FROM \`${PROJECT}.${MART}.order_analysis\` WHERE order_urgency = 'CRITICAL')      AS critical_count,
        (SELECT COUNT(*)  FROM \`${PROJECT}.${MART}.order_analysis\` WHERE order_urgency = 'WARNING')       AS warning_count
    `;

    const [job] = await bq.createQueryJob({ query: sql, location: LOCATION });
    const [rows] = await job.getQueryResults();
    const r = rows[0] || {};

    return NextResponse.json({
      total_products:  Number(r.total_products  ?? 0),
      total_skus:      Number(r.total_skus      ?? 0),
      total_inventory: Number(r.total_inventory ?? 0),
      critical_count:  Number(r.critical_count  ?? 0),
      warning_count:   Number(r.warning_count   ?? 0),
    });
  } catch (err: any) {
    return NextResponse.json({ error: err.message || String(err) }, { status: 500 });
  }
}
