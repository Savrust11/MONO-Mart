import { NextRequest, NextResponse } from 'next/server';
import ExcelJS from 'exceljs';
import { fetchOrderAnalysis, fetchLatestAnalysisDate } from '@/lib/bigquery';
import { todayJST } from '@/lib/utils';

export const dynamic = 'force-dynamic';
export const revalidate = 0;
export const maxDuration = 60;

// 顧客要望2026: 発注推奨データの「絞り込み（ショップ/親カテゴリ/性別/ステータス）」を保持したまま
//   Excel(.xlsx)でダウンロード。BigQueryから絞り込み済みの行を取得し exceljs で生成する。
//   （全件の発注管理表.xlsx は /api/order-xlsx＝GCS生成物。本ルートは絞り込み版を都度生成。）
const HEADERS = [
  'メーカーカラー名', '品番', '商品名', 'ショップ', '親カテゴリ', '商品主性別',
  'カラー', 'サイズ', 'CS品番', '店舗棚情報', '在庫', '入荷残', 'フリー在庫', '予約未処理数',
  '7日販売', '30日販売', '直近2週間', '年度累計', '在庫日数', '1ヶ月差分', 'トレンド係数',
  '推奨発注数', '緊急度', '原価', '売価', '粗利率(%)',
];

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const dateParam       = (searchParams.get('date') || 'latest').trim();
  const urgency         = searchParams.get('urgency')         || undefined;
  const shop            = searchParams.get('shop')            || undefined;
  const parent_category = searchParams.get('parent_category') || undefined;
  const gender          = searchParams.get('gender')          || undefined;
  const date = dateParam === 'latest' ? ((await fetchLatestAnalysisDate()) || todayJST()) : dateParam;

  try {
    const { rows } = await fetchOrderAnalysis({ date, urgency, shop, parent_category, gender, limit: 10000 });

    const wb = new ExcelJS.Workbook();
    const ws = wb.addWorksheet('発注推奨データ');
    // 絞り込み条件の見出し行
    const cond = [
      shop ? `ショップ=${shop}` : null, parent_category ? `親カテゴリ=${parent_category}` : null,
      gender ? `性別=${gender}` : null, urgency ? `ステータス=${urgency}` : null,
    ].filter(Boolean).join(' / ') || '全件';
    ws.addRow([`発注推奨データ（${date}）  絞り込み: ${cond}  ${rows.length}件`]);
    ws.addRow([]);
    const head = ws.addRow(HEADERS);
    head.font = { bold: true };
    head.eachCell((c) => { c.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FFEFEFEF' } }; });

    for (const r of rows) {
      ws.addRow([
        r.maker_color_code, r.product_code, r.product_name, r.shop_name ?? '', r.parent_category ?? '', r.gender ?? '',
        r.color_name, r.size, r.sku_code, r.shelf_type, r.inventory, r.incoming_stock, r.free_inventory, r.reservations_pending,
        r.sales_7d, r.sales_30d, r.sales_2w, r.sales_ytd,
        r.stock_days_7d != null ? Math.round(r.stock_days_7d) : '',
        r.monthly_gap, r.trend_coefficient != null ? Number(r.trend_coefficient.toFixed(2)) : '',
        r.recommended_order_qty, r.order_urgency, r.cost_price, r.retail_price,
        r.gross_margin_pct != null ? Number((r.gross_margin_pct * 100).toFixed(1)) : '',
      ]);
    }
    ws.views = [{ state: 'frozen', ySplit: 3 }];

    const buf = await wb.xlsx.writeBuffer();
    const fname = `発注推奨データ_${date}.xlsx`;
    return new NextResponse(Buffer.from(buf), {
      status: 200,
      headers: {
        'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'Content-Disposition': `attachment; filename*=UTF-8''${encodeURIComponent(fname)}`,
        'Cache-Control': 'no-store',
      },
    });
  } catch (err) {
    console.error('[api/order-xlsx-filtered] Error:', err);
    return NextResponse.json({ error: 'Excel(絞り込み)生成に失敗しました: ' + String(err).slice(0, 200) }, { status: 500 });
  }
}
