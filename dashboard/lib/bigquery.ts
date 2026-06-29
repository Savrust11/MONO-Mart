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
  // 顧客要望2026: ZOZOBO同様の絞り込み用（product_master から補完）
  shop_name: string | null;
  parent_category: string | null;
  gender: string | null;
}

export async function fetchOrderAnalysis(params: {
  date: string;
  product_code?: string;
  urgency?: string;
  shop?: string;
  parent_category?: string;
  gender?: string;
  limit?: number;
  offset?: number;
}): Promise<{ rows: OrderAnalysisRow[]; total: number;
              filters: { shops: string[]; categories: string[]; genders: string[] } }> {
  const bq = getBQClient();
  const LOC = 'asia-northeast1';

  // 顧客要望2026: ZOZOBO同様に ショップ／親カテゴリ／商品主性別 で絞り込み。
  //   mart に該当列が無いため product_master（品番単位に重複排除）をJOINして補完・絞り込む。
  const PM = `pm AS (
    SELECT UPPER(TRIM(product_code)) pc, ANY_VALUE(shop_name) shop_name,
           ANY_VALUE(parent_item_type) parent_category, ANY_VALUE(gender) gender
    FROM \`${PROJECT_ID}.analytics_layer.product_master\` GROUP BY pc)`;
  const MART = `\`${PROJECT_ID}.${DATASET_MART}.order_analysis\``;

  const conditions = ['o.analysis_date = @date'];
  const queryParams: Record<string, unknown> = { date: params.date };
  if (params.product_code) { conditions.push('o.product_code = @product_code'); queryParams.product_code = params.product_code; }
  if (params.urgency)      { conditions.push('o.order_urgency = @urgency');      queryParams.urgency = params.urgency; }
  if (params.shop)            { conditions.push('pm.shop_name = @shop');            queryParams.shop = params.shop; }
  if (params.parent_category) { conditions.push('pm.parent_category = @parent_category'); queryParams.parent_category = params.parent_category; }
  if (params.gender)          { conditions.push('pm.gender = @gender');             queryParams.gender = params.gender; }

  const where = conditions.join(' AND ');
  const limit = params.limit ?? 500;
  const offset = params.offset ?? 0;
  const joined = `${MART} o LEFT JOIN pm ON pm.pc = UPPER(TRIM(o.product_code))`;

  const countQuery = `WITH ${PM} SELECT COUNT(*) AS total FROM ${joined} WHERE ${where}`;
  const dataQuery = `WITH ${PM}
    SELECT o.*, pm.shop_name, pm.parent_category, pm.gender
    FROM ${joined}
    WHERE ${where}
    ORDER BY
      CASE o.order_urgency WHEN 'CRITICAL' THEN 1 WHEN 'WARNING' THEN 2 WHEN 'OK' THEN 3 WHEN 'OVERSTOCK' THEN 4 ELSE 5 END,
      o.days_to_stockout ASC NULLS LAST, o.product_code, o.color_code, o.size
    LIMIT @limit OFFSET @offset`;
  // 絞り込みドロップダウンの選択肢（当日の対象に存在する値のみ・絞り込み条件は無視）。
  const optQuery = `WITH ${PM}
    SELECT DISTINCT pm.shop_name shop, pm.parent_category cat, pm.gender gender
    FROM ${joined} WHERE o.analysis_date = @date`;

  const [[countResult], [rows], [optRows]] = await Promise.all([
    bq.query({ query: countQuery, params: queryParams, location: LOC }),
    bq.query({ query: dataQuery, params: { ...queryParams, limit, offset }, location: LOC }),
    bq.query({ query: optQuery, params: { date: params.date }, location: LOC }),
  ]);

  const uniq = (vals: unknown[]) => [...new Set(vals.filter((v): v is string => !!v))].sort((a, b) => a.localeCompare(b, 'ja'));
  return {
    rows: rows as OrderAnalysisRow[],
    total: Number(countResult[0]?.total ?? 0),
    filters: {
      shops: uniq((optRows as Record<string, unknown>[]).map((r) => r.shop)),
      categories: uniq((optRows as Record<string, unknown>[]).map((r) => r.cat)),
      genders: uniq((optRows as Record<string, unknown>[]).map((r) => r.gender)),
    },
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
