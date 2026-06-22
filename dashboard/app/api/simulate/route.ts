/**
 * POST /api/simulate
 *
 * Runs a multi-scenario order simulation for a given SKU.
 * Returns three scenarios (conservative / balanced / aggressive) with
 * projected 12-week inventory curves and financial impact estimates.
 *
 * Body: { sku_code: string; date: string; order_qty?: number }
 *
 * Reads live data from mart_layer.order_analysis + analytics_layer.inventory_forecast.
 */
import { NextRequest, NextResponse } from 'next/server';
import { BigQuery } from '@google-cloud/bigquery';
import { todayJST } from '@/lib/utils';

export const dynamic = 'force-dynamic';

const PROJECT_ID       = process.env.GCP_PROJECT_ID!;
const DATASET_MART     = process.env.BQ_DATASET_MART     ?? 'mart_layer';
const DATASET_ANALYTICS = process.env.BQ_DATASET_ANALYTICS ?? 'analytics_layer';
const LOCATION         = process.env.BQ_LOCATION         ?? 'asia-northeast1';

let _bq: BigQuery | null = null;
function bq() {
  if (!_bq) _bq = new BigQuery({ projectId: PROJECT_ID });
  return _bq;
}

// ── Types ─────────────────────────────────────────────────────────────────────

export interface WeeklyProjection {
  week: number;
  stock_without_order: number;
  stock_conservative: number;
  stock_balanced: number;
  stock_aggressive: number;
}

export interface Scenario {
  label:           string;
  order_qty:       number;
  target_days:     number;
  projected_weeks: number | null;  // weeks of coverage, null = infinite within horizon
  stockout_week:   number | null;
  total_cost:      number;
  total_revenue:   number;
  gross_profit:    number;
  margin_pct:      number | null;
  description:     string;
}

export interface SimulationResult {
  sku_code:          string;
  product_code:      string;
  product_name:      string;
  color_name:        string;
  size:              string;
  date:              string;
  // Current snapshot
  current: {
    free_inventory:     number;
    daily_velocity_30d: number;
    trend_coefficient:  number;
    stock_days_7d:      number | null;
    order_urgency:      string;
    cost_price:         number;
    retail_price:       number;
    gross_margin_pct:   number | null;
    recommended_order_qty: number;
  };
  // Scenarios
  scenarios: {
    conservative: Scenario;
    balanced:     Scenario;
    aggressive:   Scenario;
  };
  // 12-week curve (one data point per week)
  weekly_projections: WeeklyProjection[];
}

// ── Main handler ──────────────────────────────────────────────────────────────

const MOCK_URL = process.env.MOCK_API_URL;

export async function POST(req: NextRequest) {
  let body: Record<string, unknown>;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: 'Invalid JSON body.' }, { status: 400 });
  }

  const sku_code  = String(body.sku_code  ?? '').trim();
  const date      = String(body.date      ?? todayJST()).trim();
  const order_qty = body.order_qty != null ? Number(body.order_qty) : null;

  if (!sku_code) {
    return NextResponse.json({ error: 'sku_code is required.' }, { status: 400 });
  }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
    return NextResponse.json({ error: 'Invalid date format. Use YYYY-MM-DD.' }, { status: 400 });
  }
  if (order_qty !== null && (isNaN(order_qty) || order_qty < 0)) {
    return NextResponse.json({ error: 'order_qty must be a non-negative number.' }, { status: 400 });
  }

  if (MOCK_URL) {
    const resp = await fetch(`${MOCK_URL}/api/simulate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sku_code, order_qty }),
    });
    const data = await resp.json();
    return NextResponse.json(data, { status: resp.status });
  }

  try {
    const [skuRows, forecastRows] = await Promise.all([
      fetchSkuMetrics(sku_code, date),
      fetchForecast(sku_code, date),
    ]);

    if (!skuRows.length) {
      return NextResponse.json(
        { error: `No data found for sku_code=${sku_code} on date=${date}` },
        { status: 404 }
      );
    }

    const sku      = skuRows[0] as SkuRow;
    const forecast = forecastRows[0] as ForecastRow | undefined;

    const result = buildSimulation(sku, forecast, order_qty);
    return NextResponse.json(result);

  } catch (err) {
    console.error('[api/simulate] Error:', err);
    return NextResponse.json({ error: 'Simulation failed.' }, { status: 500 });
  }
}

// ── Queries ───────────────────────────────────────────────────────────────────

interface SkuRow {
  sku_code: string;
  product_code: string;
  product_name: string;
  color_name: string;
  size: string;
  free_inventory: number;
  daily_velocity_30d: number;
  daily_velocity_7d: number;
  trend_coefficient: number | null;
  stock_days_7d: number | null;
  order_urgency: string;
  cost_price: number;
  retail_price: number;
  gross_margin_pct: number | null;
  recommended_order_qty: number;
}

interface ForecastRow {
  projected_week_1: number;
  projected_week_2: number;
  projected_week_3: number;
  projected_week_4: number;
  projected_week_5: number;
  projected_week_6: number;
  projected_week_7: number;
  projected_week_8: number;
  projected_week_9: number;
  projected_week_10: number;
  projected_week_11: number;
  projected_week_12: number;
  estimated_stockout_week: number | null;
}

async function fetchSkuMetrics(sku_code: string, date: string) {
  const [rows] = await bq().query({
    query: `
      SELECT
        sku_code, product_code, product_name, color_name, size,
        free_inventory, daily_velocity_30d, daily_velocity_7d,
        trend_coefficient, stock_days_7d, order_urgency,
        cost_price, retail_price, gross_margin_pct, recommended_order_qty
      FROM \`${PROJECT_ID}.${DATASET_MART}.order_analysis\`
      WHERE analysis_date = @date AND sku_code = @sku_code
      LIMIT 1
    `,
    params: { date, sku_code },
    location: LOCATION,
  });
  return rows;
}

async function fetchForecast(sku_code: string, date: string) {
  const [rows] = await bq().query({
    query: `
      SELECT
        projected_week_1,  projected_week_2,  projected_week_3,
        projected_week_4,  projected_week_5,  projected_week_6,
        projected_week_7,  projected_week_8,  projected_week_9,
        projected_week_10, projected_week_11, projected_week_12,
        estimated_stockout_week
      FROM \`${PROJECT_ID}.${DATASET_ANALYTICS}.inventory_forecast\`
      WHERE forecast_date = @date AND sku_code = @sku_code
      LIMIT 1
    `,
    params: { date, sku_code },
    location: LOCATION,
  });
  return rows;
}

// ── Simulation logic ──────────────────────────────────────────────────────────

function buildSimulation(
  sku:       SkuRow,
  forecast:  ForecastRow | undefined,
  userQty:   number | null
): SimulationResult {
  const trend    = Math.min(2.0, Math.max(0.5, sku.trend_coefficient ?? 1.0));
  const velocity = sku.daily_velocity_30d * trend;  // adjusted daily demand
  const freePre  = sku.free_inventory;
  const rec      = sku.recommended_order_qty;

  // Three order quantities:
  //   conservative = 50% of recommended (minimum safety top-up)
  //   balanced     = recommended (default 8-week coverage)
  //   aggressive   = 150% of recommended (growth-forward, 12-week coverage)
  const qtyConservative = userQty != null ? Math.round(userQty * 0.6) : Math.max(0, Math.round(rec * 0.5));
  const qtyBalanced     = userQty != null ? userQty                   : rec;
  const qtyAggressive   = userQty != null ? Math.round(userQty * 1.5) : Math.round(rec * 1.5);

  const makeScenario = (
    label: string,
    qty: number,
    description: string
  ): Scenario => {
    const startStock   = freePre + qty;
    // Weeks until depletion at adjusted daily velocity
    const projWeeks    = velocity > 0 ? startStock / (velocity * 7) : Infinity;
    const stockoutWeek = projWeeks < 12 && velocity > 0
      ? Math.ceil(projWeeks) : null;

    const cost         = qty * sku.cost_price;
    const unitsSold    = velocity > 0
      ? Math.min(startStock, velocity * 7 * 12)   // max 12 weeks
      : 0;
    const revenue      = unitsSold * sku.retail_price;
    const grossProfit  = revenue - cost - (freePre * sku.cost_price);  // net of existing inventory cost
    const margin       = revenue > 0 ? grossProfit / revenue : null;

    return {
      label,
      order_qty:       qty,
      target_days:     velocity > 0 ? Math.round(startStock / velocity) : 0,
      projected_weeks: stockoutWeek == null ? null : stockoutWeek,
      stockout_week:   stockoutWeek,
      total_cost:      Math.round(cost),
      total_revenue:   Math.round(revenue),
      gross_profit:    Math.round(grossProfit),
      margin_pct:      margin,
      description,
    };
  };

  const scenarios = {
    conservative: makeScenario(
      '安全発注',
      qtyConservative,
      '最小限の補充。キャッシュフロー優先。在庫リスクは残る。'
    ),
    balanced: makeScenario(
      '推奨発注',
      qtyBalanced,
      '8週間カバレッジを目標。トレンド係数を考慮した標準発注量。'
    ),
    aggressive: makeScenario(
      '積極発注',
      qtyAggressive,
      '12週間カバレッジ。需要加速・欠品リスクゼロを優先。在庫コスト増。'
    ),
  };

  // 12-week projections for chart
  const baseProjections: number[] = forecast
    ? [
        forecast.projected_week_1,  forecast.projected_week_2,
        forecast.projected_week_3,  forecast.projected_week_4,
        forecast.projected_week_5,  forecast.projected_week_6,
        forecast.projected_week_7,  forecast.projected_week_8,
        forecast.projected_week_9,  forecast.projected_week_10,
        forecast.projected_week_11, forecast.projected_week_12,
      ]
    : buildLinearProjection(freePre, velocity, 12);

  const weeklyProjections: WeeklyProjection[] = baseProjections.map((baseStock, i) => ({
    week: i + 1,
    stock_without_order: baseStock,
    stock_conservative:  baseStock + qtyConservative,
    stock_balanced:      baseStock + qtyBalanced,
    stock_aggressive:    baseStock + qtyAggressive,
  }));

  return {
    sku_code:     sku.sku_code,
    product_code: sku.product_code,
    product_name: sku.product_name,
    color_name:   sku.color_name,
    size:         sku.size,
    date:         new Date().toISOString().slice(0, 10),
    current: {
      free_inventory:        freePre,
      daily_velocity_30d:    sku.daily_velocity_30d,
      trend_coefficient:     trend,
      stock_days_7d:         sku.stock_days_7d,
      order_urgency:         sku.order_urgency,
      cost_price:            sku.cost_price,
      retail_price:          sku.retail_price,
      gross_margin_pct:      sku.gross_margin_pct,
      recommended_order_qty: rec,
    },
    scenarios,
    weekly_projections: weeklyProjections,
  };
}

/** Fallback: linear depletion when forecast table has no data yet */
function buildLinearProjection(
  startStock: number,
  dailyVelocity: number,
  weeks: number
): number[] {
  const result: number[] = [];
  for (let w = 1; w <= weeks; w++) {
    result.push(Math.round(startStock - dailyVelocity * 7 * w));
  }
  return result;
}
