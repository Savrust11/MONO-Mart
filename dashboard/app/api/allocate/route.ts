/**
 * POST /api/allocate
 *
 * 繰り返し発注 — SKU balance allocation
 *
 * Given a product_code and total_order_qty, distributes the quantity across
 * all SKUs (color × size) using the MONO BACK OFFICE allocation formula:
 *
 *   weight_i = sales_30d_i × stock_day_coefficient_i
 *   alloc_i  = total_order_qty × (weight_i / Σ weight)
 *
 * 在庫日数調整係数:
 *   stock_days == 0    → × 1.5  (stockout)
 *   0 < days ≤ 30     → × 1.0  (normal)
 *   30 < days ≤ 60    → × 0.9  (mild excess)
 *   days > 60          → × 0.7  (overstock)
 *
 * Body: { product_code: string; date: string; total_order_qty: number }
 */
import { NextRequest, NextResponse } from 'next/server';
import { BigQuery } from '@google-cloud/bigquery';
import { todayJST } from '@/lib/utils';

export const dynamic = 'force-dynamic';

const PROJECT_ID   = process.env.GCP_PROJECT_ID!;
const DATASET_MART = process.env.BQ_DATASET_MART ?? 'mart_layer';
const LOCATION     = process.env.BQ_LOCATION     ?? 'asia-northeast1';

let _bq: BigQuery | null = null;
function bq() {
  if (!_bq) _bq = new BigQuery({ projectId: PROJECT_ID });
  return _bq;
}

// ── Allocation coefficient lookup ─────────────────────────────────────────────

function stockDayCoeff(stockDays: number | null): number {
  if (stockDays == null) return 1.0;
  if (stockDays <= 0)   return 1.5;  // stockout
  if (stockDays <= 30)  return 1.0;  // normal
  if (stockDays <= 60)  return 0.9;  // mild excess
  return 0.7;                         // overstock
}

// ── Types ─────────────────────────────────────────────────────────────────────

interface SkuRow {
  sku_code:        string;
  color_code:      string;
  color_name:      string;
  size:            string;
  sales_30d:       number;
  stock_days_7d:   number | null;
  free_inventory:  number;
  recommended_order_qty: number;
  order_urgency:   string;
}

interface AllocationItem {
  sku_code:        string;
  color_code:      string;
  color_name:      string;
  size:            string;
  sales_30d:       number;
  stock_days_7d:   number | null;
  order_urgency:   string;
  free_inventory:  number;
  recommended_qty: number;
  sales_share_pct: number;  // percentage of 30d sales
  adj_coefficient: number;
  weight_share_pct: number; // percentage of weighted allocation
  allocated_qty:   number;  // final integer allocation
}

// ── Handler ───────────────────────────────────────────────────────────────────

const MOCK_URL = process.env.MOCK_API_URL;

export async function POST(req: NextRequest) {
  let body: Record<string, unknown>;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: 'Invalid JSON body.' }, { status: 400 });
  }

  const product_code    = String(body.product_code ?? '').trim();
  const date            = String(body.date         ?? todayJST()).trim();
  const total_order_qty = Number(body.total_order_qty ?? 0);

  if (!product_code) {
    return NextResponse.json({ error: 'product_code is required.' }, { status: 400 });
  }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
    return NextResponse.json({ error: 'Invalid date format.' }, { status: 400 });
  }
  if (isNaN(total_order_qty) || total_order_qty < 0) {
    return NextResponse.json({ error: 'total_order_qty must be ≥ 0.' }, { status: 400 });
  }

  if (MOCK_URL) {
    const resp = await fetch(`${MOCK_URL}/api/allocate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ product_code, total_order_qty }),
    });
    const data = await resp.json();
    return NextResponse.json(data, { status: resp.status });
  }

  try {
    const [rows] = await bq().query({
      query: `
        SELECT
          sku_code, color_code, color_name, size,
          sales_30d, stock_days_7d, free_inventory,
          recommended_order_qty, order_urgency
        FROM \`${PROJECT_ID}.${DATASET_MART}.order_analysis\`
        WHERE analysis_date = @date
          AND product_code  = @product_code
        ORDER BY color_code, size
      `,
      params: { date, product_code },
      location: LOCATION,
    });

    if (!rows.length) {
      return NextResponse.json(
        { error: `No SKUs found for product_code=${product_code} on date=${date}` },
        { status: 404 }
      );
    }

    const result = computeAllocation(
      product_code,
      total_order_qty,
      rows as SkuRow[]
    );

    return NextResponse.json(result);

  } catch (err) {
    console.error('[api/allocate] Error:', err);
    return NextResponse.json({ error: 'Allocation failed.' }, { status: 500 });
  }
}

// ── Core allocation logic ─────────────────────────────────────────────────────

function computeAllocation(
  product_code:    string,
  total_order_qty: number,
  skus:            SkuRow[]
) {
  const total_sales_30d = skus.reduce((s, r) => s + Math.max(r.sales_30d || 0, 0), 0);

  // Step 1: Compute weights
  const weights = skus.map(sku => {
    const sales = Math.max(sku.sales_30d || 0, 0);
    const coeff = stockDayCoeff(sku.stock_days_7d);
    return sales * coeff;
  });
  const totalWeight = weights.reduce((s, w) => s + w, 0);

  // Step 2: Raw allocation (may be fractional)
  const rawAllocs = weights.map(w =>
    totalWeight > 0
      ? total_order_qty * (w / totalWeight)
      : total_order_qty / skus.length
  );

  // Step 3: Floor + distribute residual by largest remainder
  const floored   = rawAllocs.map(Math.floor);
  const residual  = total_order_qty - floored.reduce((s, v) => s + v, 0);
  const remainders = rawAllocs.map((r, i) => ({ i, frac: r - Math.floor(r) }))
    .sort((a, b) => b.frac - a.frac);
  for (let j = 0; j < residual; j++) {
    floored[remainders[j].i] += 1;
  }

  // Step 4: Build output
  const items: AllocationItem[] = skus.map((sku, i) => {
    const sales    = Math.max(sku.sales_30d || 0, 0);
    const coeff    = stockDayCoeff(sku.stock_days_7d);
    const share    = totalWeight > 0 ? weights[i] / totalWeight : 1 / skus.length;
    const salesPct = total_sales_30d > 0 ? (sales / total_sales_30d) * 100 : 0;

    return {
      sku_code:         sku.sku_code,
      color_code:       sku.color_code,
      color_name:       sku.color_name,
      size:             sku.size,
      sales_30d:        sales,
      stock_days_7d:    sku.stock_days_7d,
      order_urgency:    sku.order_urgency,
      free_inventory:   sku.free_inventory,
      recommended_qty:  sku.recommended_order_qty,
      sales_share_pct:  Math.round(salesPct * 10) / 10,
      adj_coefficient:  coeff,
      weight_share_pct: Math.round(share * 1000) / 10,
      allocated_qty:    floored[i],
    };
  });

  return {
    product_code,
    date:              new Date().toISOString().slice(0, 10),
    total_order_qty,
    total_sales_30d,
    allocated_total:   floored.reduce((s, v) => s + v, 0),
    skus:              items,
  };
}
