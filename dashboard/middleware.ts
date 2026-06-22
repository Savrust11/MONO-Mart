import { NextRequest, NextResponse } from 'next/server';

// シンプルな Basic 認証ゲート。Render の公開URLを「IDとパスワードを知っている顧客のみ」に限定する。
// 環境変数 BASIC_AUTH_USER / BASIC_AUTH_PASS が両方設定されているときだけ有効化。
// （未設定のローカル開発では素通し＝従来どおり）
export function middleware(req: NextRequest) {
  const user = process.env.BASIC_AUTH_USER;
  const pass = process.env.BASIC_AUTH_PASS;
  if (!user || !pass) return NextResponse.next(); // 認証情報が未設定なら無効（開発用）

  const header = req.headers.get('authorization');
  if (header?.startsWith('Basic ')) {
    const decoded = atob(header.slice(6));
    const i = decoded.indexOf(':');
    if (decoded.slice(0, i) === user && decoded.slice(i + 1) === pass) {
      return NextResponse.next();
    }
  }
  return new NextResponse('認証が必要です。', {
    status: 401,
    headers: { 'WWW-Authenticate': 'Basic realm="MONO BACK OFFICE", charset="UTF-8"' },
  });
}

export const config = {
  // 静的アセット以外（全ページ・全API）に適用
  matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'],
};
