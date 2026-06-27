import { NextResponse } from 'next/server';
import { GoogleAuth } from 'google-auth-library';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

// 発注管理表.xlsx は非公開バケットにある（毎朝07:00 JST再生成）。
//   storage.googleapis.com の直リンクは匿名アクセス→403 になるため、ここで
//   サービスアカウント認証（BigQuery と同じ ADC）で読み出してブラウザへ配信する。
//   バケットは非公開のまま＝公開設定は不要。
const BUCKET = 'mono-back-office-system-exports';
const OBJECT = 'order_management/latest/発注管理表.xlsx';

export async function GET() {
  try {
    const auth = new GoogleAuth({ scopes: ['https://www.googleapis.com/auth/devstorage.read_only'] });
    const client = await auth.getClient();
    const token = (await client.getAccessToken()).token;
    if (!token) throw new Error('認証トークン取得失敗');

    const url = `https://storage.googleapis.com/storage/v1/b/${BUCKET}/o/${encodeURIComponent(OBJECT)}?alt=media`;
    const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
    if (!res.ok) {
      const body = await res.text();
      return NextResponse.json(
        { error: `GCS取得に失敗しました(${res.status})。生成ジョブ未完了の可能性: ${body.slice(0, 160)}` },
        { status: 502 });
    }
    const buf = Buffer.from(await res.arrayBuffer());
    const ymd = new Date(Date.now() + 9 * 3600 * 1000).toISOString().slice(0, 10);
    const filename = `発注管理表_${ymd}.xlsx`;
    return new NextResponse(buf, {
      status: 200,
      headers: {
        'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'Content-Disposition': `attachment; filename*=UTF-8''${encodeURIComponent(filename)}`,
        'Cache-Control': 'no-store',
      },
    });
  } catch (err) {
    return NextResponse.json(
      { error: 'Excel取得に失敗しました: ' + String(err).slice(0, 200) }, { status: 500 });
  }
}
