import { NextResponse } from 'next/server';
import { BigQuery } from '@google-cloud/bigquery';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

const PROJECT = process.env.GCP_PROJECT_ID || 'mono-back-office-system';
const LOC = 'asia-northeast1';
let _bq: BigQuery | null = null;
const bq = () => (_bq ??= new BigQuery({ projectId: PROJECT }));

// 顧客#14: 52週 季節係数（男女別 × 商品タイプ子別）の確認用API。
export async function GET() {
  try {
    const [rows] = await bq().query({
      query: `SELECT gender, child_item_type, week_number, coefficient, week_qty,
                     CAST(MAX(updated_at) OVER () AS STRING) AS updated_at
              FROM \`${PROJECT}.analytics_layer.seasonal_coefficients\`
              ORDER BY gender, child_item_type, week_number`,
      location: LOC,
    });
    const map = new Map<string, { gender: string; child_item_type: string; weeks: (number | null)[]; total: number }>();
    let updatedAt: string | null = null;
    for (const r of rows as any[]) {
      updatedAt = r.updated_at ?? updatedAt;
      const key = `${r.gender}|||${r.child_item_type}`;
      if (!map.has(key)) map.set(key, { gender: r.gender, child_item_type: r.child_item_type, weeks: Array(54).fill(null), total: 0 });
      const g = map.get(key)!;
      g.weeks[Number(r.week_number)] = Number(r.coefficient);
      g.total += Number(r.week_qty) || 0;
    }
    const categories = [...map.values()].sort((a, b) => b.total - a.total);
    return NextResponse.json({ categories, count: categories.length, updated_at: updatedAt });
  } catch (err) {
    return NextResponse.json({ error: '季節係数の取得に失敗しました: ' + String(err).slice(0, 200) }, { status: 500 });
  }
}
