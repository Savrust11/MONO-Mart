import { NextRequest, NextResponse } from 'next/server';
import { fetchPlan2, plan2ToMatrix } from '@/lib/order-plan2';
import { matrixToCsv } from '@/lib/sheets-out';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

// 発注管理表「案2」: 品番 × 指定期間 の時系列ピボット（11指標 月次/日次 + SKU×日付）。
//   GET /api/order-plan2?product_code=sc491&start=2026-05-01&end=2026-05-31
export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const pc = (searchParams.get('product_code') || '').trim();
  const start = searchParams.get('start') || '';
  const end = searchParams.get('end') || '';

  if (!pc) return NextResponse.json({ error: '品番（product_code）を指定してください。' }, { status: 400 });
  if (!/^\d{4}-\d{2}-\d{2}$/.test(start) || !/^\d{4}-\d{2}-\d{2}$/.test(end)) {
    return NextResponse.json({ error: '日付は YYYY-MM-DD 形式で指定してください。' }, { status: 400 });
  }
  if (start > end) return NextResponse.json({ error: '開始日が終了日より後になっています。' }, { status: 400 });

  try {
    const plan = await fetchPlan2(pc, start, end);
    if (searchParams.get('format') === 'csv') {
      const csv = matrixToCsv(plan2ToMatrix(plan));
      return new NextResponse(csv, {
        status: 200,
        headers: {
          'Content-Type': 'text/csv; charset=utf-8',
          'Content-Disposition': `attachment; filename="plan2_${pc}_${start}_${end}.csv"`,
        },
      });
    }
    return NextResponse.json({ ...plan, generated_at: new Date().toISOString() });
  } catch (err) {
    console.error('[api/order-plan2] Error:', err);
    return NextResponse.json({ error: '推移集計の集計に失敗しました: ' + String(err).slice(0, 200) }, { status: 500 });
  }
}
