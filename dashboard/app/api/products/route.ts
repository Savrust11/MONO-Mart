import { NextRequest, NextResponse } from 'next/server';
import { fetchOrderAnalysis } from '@/lib/bigquery';
import { todayJST } from '@/lib/utils';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

const MOCK_URL = process.env.MOCK_API_URL;

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);

  const date         = searchParams.get('date')         || todayJST();
  const product_code = searchParams.get('product_code') || undefined;
  const urgency      = searchParams.get('urgency')      || undefined;
  const limit        = Math.min(Number(searchParams.get('limit')  || 500), 1000);
  const offset       = Number(searchParams.get('offset') || 0);

  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
    return NextResponse.json({ error: 'Invalid date format. Use YYYY-MM-DD.' }, { status: 400 });
  }
  if (urgency && !['CRITICAL', 'WARNING', 'OK', 'OVERSTOCK'].includes(urgency)) {
    return NextResponse.json({ error: 'Invalid urgency value.' }, { status: 400 });
  }

  if (MOCK_URL) {
    const qs = new URLSearchParams();
    if (urgency)      qs.set('urgency',      urgency);
    if (product_code) qs.set('product_code', product_code);
    const resp = await fetch(`${MOCK_URL}/api/products?${qs}`);
    const data = await resp.json();
    return NextResponse.json(data);
  }

  try {
    const result = await fetchOrderAnalysis({ date, product_code, urgency, limit, offset });
    return NextResponse.json({
      data:  result.rows,
      total: result.total,
      date,
      limit,
      offset,
      generated_at: new Date().toISOString(),
    });
  } catch (err) {
    console.error('[api/products] Error:', err);
    return NextResponse.json(
      { error: 'Failed to fetch product data from BigQuery.' },
      { status: 500 }
    );
  }
}
