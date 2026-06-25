/**
 * BigQuery client for server-side API routes.
 * Credentials come from the service account attached to Cloud Run.
 */
import { BigQuery } from '@google-cloud/bigquery';

const PROJECT_ID = process.env.GCP_PROJECT_ID!;
const DATASET_MART = process.env.BQ_DATASET_MART ?? 'mart_layer';

// Singleton — reuse across requests in the same Cloud Run instance
let _bq: BigQuery | null = null;

function getBQClient(): BigQuery {
  if (!_bq) {
    _bq = new BigQuery({ projectId: PROJECT_ID });
  }
  return _bq;
}

// 顧客#15: 発注推奨データ画面が「今日」で空になるのを防ぐため、マートの最新日を返す。
export async function fetchLatestAnalysisDate(): Promise<string | null> {
  const bq = getBQClient();
  const [rows] = await bq.query({
    query: `SELECT CAST(MAX(analysis_date) AS STRING) AS d FROM \`${PROJECT_ID}.${DATASET_MART}.order_analysis\``,
    location: 'asia-northeast1',
  });
  return (rows as { d: string | null }[])[0]?.d ?? null;
}

export interface OrderAnalysisRow {
  analysis_date: string;
  product_code: string;
  product_name: string;
  color_code: string;
  color_name: string;
  size: string;
  sku_code: string;
  maker_color_code: string;
  shelf_type: string;
  inventory: number;
  incoming_stock: number;
  reserved_quantity: number;
  reservations_pending: number;
  free_inventory: number;
  sales_cumulative: number;
  favorites_total: number;
  sales_7d: number;
  sales_30d: number;
  sales_2w: number;
  sales_ytd: number;
  daily_velocity_7d: number;
  daily_velocity_30d: number;
  stock_days_7d: number | null;
  monthly_gap: number;
  trend_coefficient: number | null;
  cost_price: number;
  retail_price: number;
  gross_margin_pct: number | null;
  recommended_order_qty: number;
  order_urgency: 'CRITICAL' | 'WARNING' | 'OK' | 'OVERSTOCK';
  days_to_stockout: number | null;
  daily_sales_30d: Array<{ sale_date: string; qty: number }>;
  monthly_sales: Array<{ month: string; qty: number }>;
  computed_at: string;
}

export async function fetchOrderAnalysis(params: {
  date: string;
  product_code?: string;
  urgency?: string;
  limit?: number;
  offset?: number;
}): Promise<{ rows: OrderAnalysisRow[]; total: number }> {
  const bq = getBQClient();

  const conditions = ['analysis_date = @date'];
  const queryParams: Record<string, unknown> = { date: params.date };

  if (params.product_code) {
    conditions.push('product_code = @product_code');
    queryParams.product_code = params.product_code;
  }
  if (params.urgency) {
    conditions.push('order_urgency = @urgency');
    queryParams.urgency = params.urgency;
  }

  const where = conditions.join(' AND ');
  const limit = params.limit ?? 500;
  const offset = params.offset ?? 0;

  const countQuery = `
    SELECT COUNT(*) AS total
    FROM \`${PROJECT_ID}.${DATASET_MART}.order_analysis\`
    WHERE ${where}
  `;

  const dataQuery = `
    SELECT *
    FROM \`${PROJECT_ID}.${DATASET_MART}.order_analysis\`
    WHERE ${where}
    ORDER BY
      CASE order_urgency
        WHEN 'CRITICAL'  THEN 1
        WHEN 'WARNING'   THEN 2
        WHEN 'OK'        THEN 3
        WHEN 'OVERSTOCK' THEN 4
        ELSE 5
      END,
      days_to_stockout ASC NULLS LAST,
      product_code,
      color_code,
      size
    LIMIT @limit OFFSET @offset
  `;

  const queryOpts = {
    params: { ...queryParams, limit, offset },
    location: 'asia-northeast1',
  };

  const [[countResult], [rows]] = await Promise.all([
    bq.query({ query: countQuery, params: queryParams, location: queryOpts.location }),
    bq.query({ query: dataQuery, ...queryOpts }),
  ]);

  return {
    rows: rows as OrderAnalysisRow[],
    total: Number(countResult[0]?.total ?? 0),
  };
}

export async function fetchAlerts(date: string) {
  const bq = getBQClient();
  const [rows] = await bq.query({
    query: `
      SELECT *
      FROM \`${PROJECT_ID}.${DATASET_MART}.reorder_alerts\`
      WHERE analysis_date = @date
      ORDER BY
        CASE order_urgency WHEN 'CRITICAL' THEN 0 ELSE 1 END,
        days_to_stockout ASC NULLS LAST
      LIMIT 200
    `,
    params: { date },
    location: 'asia-northeast1',
  });
  return rows;
}

export async function fetchAvailableDates(): Promise<string[]> {
  const bq = getBQClient();
  const [rows] = await bq.query({
    query: `
      SELECT DISTINCT FORMAT_DATE('%Y-%m-%d', analysis_date) AS d
      FROM \`${PROJECT_ID}.${DATASET_MART}.order_analysis\`
      ORDER BY d DESC
      LIMIT 90
    `,
    location: 'asia-northeast1',
  });
  return (rows as Array<{ d: string }>).map((r) => r.d);
}
