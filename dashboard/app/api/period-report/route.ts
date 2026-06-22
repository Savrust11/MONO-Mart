import { NextRequest, NextResponse } from 'next/server';
import { fetchPeriodReport } from '@/lib/order-report';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

// 品番 × 指定期間 の実数（発注管理表 項目詳細）。
//   GET /api/period-report?product_code=sc1032&start=2026-05-01&end=2026-05-31
export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const pc = (searchParams.get('product_code') || '').trim();
  const start = searchParams.get('start') || '';
  const end = searchParams.get('end') || '';

  if (!pc) {
    return NextResponse.json({ error: '品番（product_code）を指定してください。' }, { status: 400 });
  }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(start) || !/^\d{4}-\d{2}-\d{2}$/.test(end)) {
    return NextResponse.json({ error: '日付は YYYY-MM-DD 形式で指定してください。' }, { status: 400 });
  }
  if (start > end) {
    return NextResponse.json({ error: '開始日が終了日より後になっています。' }, { status: 400 });
  }

  const format = searchParams.get('format');

  try {
    const rows = await fetchPeriodReport(pc, start, end);

    // ③ CSVエクスポート（Excelで文字化けしないよう UTF-8 BOM）
    if (format === 'csv') {
      const esc = (s: unknown): string => {
        const v = s == null ? '' : String(s);
        return /[",\n\r]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
      };
      const lines: string[] = [
        `発注管理表（項目詳細）,品番=${pc},期間=${start}〜${end}`,
        ['区分', '項目', '値', '備考'].join(','),
      ];
      let section = '';
      for (const r of rows) {
        if (r.kind === 'title' || r.kind === 'blank') continue;
        if (r.kind === 'sec') { section = r.label; continue; }
        lines.push([esc(section), esc(r.label), esc(r.value), esc(r.note)].join(','));
      }
      const csv = '﻿' + lines.join('\r\n') + '\r\n';
      return new NextResponse(csv, {
        status: 200,
        headers: {
          'Content-Type': 'text/csv; charset=utf-8',
          'Content-Disposition': `attachment; filename="order_${pc}_${start}_${end}.csv"`,
        },
      });
    }

    return NextResponse.json({
      data: rows,
      product_code: pc,
      start,
      end,
      generated_at: new Date().toISOString(),
    });
  } catch (err) {
    console.error('[api/period-report] Error:', err);
    return NextResponse.json(
      { error: 'BigQuery からの集計に失敗しました。' },
      { status: 500 },
    );
  }
}
