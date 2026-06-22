import { NextRequest, NextResponse } from 'next/server';
import { fetchAlerts } from '@/lib/bigquery';
import { todayJST } from '@/lib/utils';

export const dynamic = 'force-dynamic';

const MOCK_URL = process.env.MOCK_API_URL;

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const date = searchParams.get('date') || todayJST();

  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
    return NextResponse.json({ error: 'Invalid date format.' }, { status: 400 });
  }

  if (MOCK_URL) {
    const resp = await fetch(`${MOCK_URL}/api/alerts`);
    const data = await resp.json();
    return NextResponse.json(data);
  }

  try {
    const alerts = await fetchAlerts(date);
    const critical = alerts.filter((a: any) => a.order_urgency === 'CRITICAL').length;
    const warning  = alerts.filter((a: any) => a.order_urgency === 'WARNING').length;

    return NextResponse.json({
      data: alerts,
      summary: { critical, warning, total: alerts.length },
      date,
      generated_at: new Date().toISOString(),
    });
  } catch (err) {
    console.error('[api/alerts] Error:', err);
    return NextResponse.json({ error: 'Failed to fetch alerts.' }, { status: 500 });
  }
}
