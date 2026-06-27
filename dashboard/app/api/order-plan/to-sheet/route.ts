import { NextRequest, NextResponse } from 'next/server';
import { fetchPlan1, plan1ToMatrix } from '@/lib/order-plan';
import { fetchPlan2, plan2ToMatrix } from '@/lib/order-plan2';
import { buildPlan1Format } from '@/lib/plan1-sheet-format';
import { writeMultiSheetToNewSheet } from '@/lib/sheets-out';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

const jstYmd = (): string => new Date(Date.now() + 9 * 3600 * 1000).toISOString().slice(0, 10).replace(/-/g, '');

// 統合スプシ出力: 1つの新規スプレッドシートに「期間集計」「推移集計」の2タブを出力（顧客要望）。
//   POST /api/order-plan/to-sheet?product_code=sc491&start=...&end=...&exclude=SKU,SKU
export async function POST(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const pc = (searchParams.get('product_code') || '').trim();
  const start = searchParams.get('start') || '';
  const end = searchParams.get('end') || '';
  const exclude = (searchParams.get('exclude') || '').split(',').map((s) => s.trim()).filter(Boolean);
  const exSet = new Set(exclude.map((s) => s.toUpperCase()));
  if (!pc) return NextResponse.json({ error: '品番を指定してください。' }, { status: 400 });
  if (!/^\d{4}-\d{2}-\d{2}$/.test(start) || !/^\d{4}-\d{2}-\d{2}$/.test(end)) {
    return NextResponse.json({ error: '日付は YYYY-MM-DD 形式で指定してください。' }, { status: 400 });
  }
  if (start > end) return NextResponse.json({ error: '開始日が終了日より後です。' }, { status: 400 });

  try {
    // ── 期間集計（Plan1）──
    const plan1 = await fetchPlan1(pc, start, end);
    let excludedColors: Set<string> | undefined;
    if (exSet.size > 0) {
      const colors = new Set(plan1.skus.map((s) => s.color_name).filter((c): c is string => !!c));
      excludedColors = new Set([...colors].filter((c) => {
        const grp = plan1.skus.filter((s) => s.color_name === c);
        return grp.length > 0 && grp.every((s) => exSet.has((s.sku_code ?? '').toUpperCase()));
      }));
      const active = plan1.skus.filter((s) => !exSet.has((s.sku_code ?? '').toUpperCase()));
      const rev = active.reduce((a, s) => a + (s.period_rev || 0), 0);
      const cost = active.reduce((a, s) => a + (s.period_cost || 0), 0);
      const lst = active.reduce((a, s) => a + (s.period_lst || 0), 0);
      const qty = active.reduce((a, s) => a + (s.sales_qty || 0), 0);
      plan1.skus = active;
      plan1.header = {
        ...plan1.header,
        total_margin_pct: rev > 0 ? Math.round((rev - cost) / rev * 1000) / 10 : null,
        total_discount_pct: lst > 0 ? Math.round((1 - rev / lst) * 1000) / 10 : null,
        total_list_amount: lst, total_revenue: rev, total_qty: qty,
      };
    }
    const matrix1 = plan1ToMatrix(plan1, excludedColors);

    // ── 推移集計（Plan2・サーバ側で除外再計算）──
    const plan2 = await fetchPlan2(pc, start, end, exclude);
    if (exSet.size > 0) plan2.skuPivot = plan2.skuPivot.filter((s) => !exSet.has((s.sku_code ?? '').toUpperCase()));
    const matrix2 = plan2ToMatrix(plan2);

    // ── 1ファイルに2タブで出力 ──
    const res = await writeMultiSheetToNewSheet(`${pc}-${jstYmd()}`, [
      { tabName: '期間集計', values: matrix1, opts: { valueInputOption: 'USER_ENTERED', format: buildPlan1Format } },
      { tabName: '推移集計', values: matrix2, opts: { valueInputOption: 'USER_ENTERED' } },
    ]);
    return NextResponse.json({ ok: true, ...res });
  } catch (err) {
    console.error('[api/order-plan/to-sheet] Error:', err);
    return NextResponse.json({ error: 'スプレッドシート出力に失敗しました: ' + String(err).slice(0, 200) }, { status: 500 });
  }
}
