/**
 * Excel export API.
 * POST /api/export — triggers Python excel_generator via Cloud Run,
 *                    returns a signed GCS URL for download.
 * GET  /api/export — streams a direct download (for small datasets).
 */
import { NextRequest, NextResponse } from 'next/server';
import { fetchOrderAnalysis, fetchLatestAnalysisDate } from '@/lib/bigquery';
import { todayJST } from '@/lib/utils';

export const dynamic = 'force-dynamic';
export const maxDuration = 60;

const EXCEL_EXPORT_URL = process.env.EXCEL_EXPORT_URL ?? '';
const MOCK_URL = process.env.MOCK_API_URL;

/**
 * POST /api/export
 * Body: { date?: string, product_codes?: string[], urgency?: string }
 *
 * If EXCEL_EXPORT_URL is set, delegates to the Python Cloud Run service.
 * Otherwise returns an error (Python service required for Excel generation).
 */
export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}));
  const date          = body.date          || todayJST();
  const product_codes = body.product_codes as string[] | undefined;
  const urgency       = body.urgency       as string | undefined;

  if (!EXCEL_EXPORT_URL) {
    return NextResponse.json(
      { error: 'EXCEL_EXPORT_URL not configured. Deploy the Python excel-export Cloud Run service.' },
      { status: 503 }
    );
  }

  try {
    const resp = await fetch(`${EXCEL_EXPORT_URL}/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ date, product_codes, urgency }),
    });

    if (!resp.ok) {
      const err = await resp.text();
      return NextResponse.json({ error: err }, { status: resp.status });
    }

    const result = await resp.json();
    return NextResponse.json(result);
  } catch (err) {
    console.error('[api/export] Error:', err);
    return NextResponse.json({ error: 'Export service unavailable.' }, { status: 502 });
  }
}

/**
 * GET /api/export?date=YYYY-MM-DD&format=csv
 * Streams a CSV download directly from BigQuery (no Python service needed).
 * Use POST for full Excel format.
 */
export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const dateParam = (searchParams.get('date') || 'latest').trim();
  // date=latest（既定）→ マート最新日を採用（/api/products と整合）。
  const date = dateParam === 'latest' ? ((await fetchLatestAnalysisDate()) || todayJST()) : dateParam;
  // 顧客要望2026: 画面の絞り込み（ステータス/ショップ/親カテゴリ/性別）をCSVにも反映。
  const urgency         = searchParams.get('urgency')         || undefined;
  const shop            = searchParams.get('shop')            || undefined;
  const parent_category = searchParams.get('parent_category') || undefined;
  const gender          = searchParams.get('gender')          || undefined;

  if (MOCK_URL) {
    const resp = await fetch(`${MOCK_URL}/api/export`);
    const body = await resp.arrayBuffer();
    return new NextResponse(body, {
      headers: {
        'Content-Type': 'text/csv; charset=utf-8',
        'Content-Disposition': `attachment; filename="order_analysis_${date}.csv"`,
      },
    });
  }

  try {
    const { rows } = await fetchOrderAnalysis({ date, urgency, shop, parent_category, gender, limit: 10000 });

    const headers = [
      'メーカーカラー名', '品番', '商品名', 'カラー', 'サイズ', 'CS品番',
      '店舗棚情報', '在庫', '入荷残', 'フリー在庫', '予約未処理数',
      '7日間', '一ヶ月', '直近2週間', '年度累計',
      '7日間分(日)', '1ヶ月差分', 'トレンド係数', '推奨発注数', '緊急度',
      '原価', '売価', '粗利率',
    ];

    const csvRows = rows.map((r) => [
      r.maker_color_code, r.product_code, r.product_name, r.color_name, r.size, r.sku_code,
      r.shelf_type, r.inventory, r.incoming_stock, r.free_inventory, r.reservations_pending,
      r.sales_7d, r.sales_30d, r.sales_2w, r.sales_ytd,
      r.stock_days_7d != null ? Math.round(r.stock_days_7d) : '',
      r.monthly_gap,
      r.trend_coefficient != null ? r.trend_coefficient.toFixed(2) : '',
      r.recommended_order_qty, r.order_urgency,
      r.cost_price, r.retail_price,
      r.gross_margin_pct != null ? (r.gross_margin_pct * 100).toFixed(1) + '%' : '',
    ]);

    const csv = [headers, ...csvRows]
      .map((row) => row.map((v) => `"${String(v ?? '').replace(/"/g, '""')}"`).join(','))
      .join('\r\n');

    // BOM for Excel UTF-8 compatibility
    const bom = '\uFEFF';
    const csvWithBom = bom + csv;

    return new NextResponse(csvWithBom, {
      headers: {
        'Content-Type': 'text/csv; charset=utf-8',
        'Content-Disposition': `attachment; filename="order_analysis_${date}.csv"`,
      },
    });
  } catch (err) {
    console.error('[api/export GET] Error:', err);
    return NextResponse.json({ error: 'CSV export failed.' }, { status: 500 });
  }
}
