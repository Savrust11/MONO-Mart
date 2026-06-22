import type { Metadata } from 'next';
import { Noto_Sans_JP } from 'next/font/google';
import './globals.css';

const notoSansJP = Noto_Sans_JP({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  display: 'swap',
  variable: '--font-noto-sans-jp',
});

export const metadata: Metadata = {
  title: 'MONO BACK OFFICE',
  description: 'ZOZOTOWN 多ブランド運営のための統合分析プラットフォーム',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ja" className={`antialiased ${notoSansJP.variable}`}>
      <body className="font-sans">{children}</body>
    </html>
  );
}
