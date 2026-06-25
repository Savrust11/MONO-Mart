import { SeasonalCoefficientsView } from '@/components/views/SeasonalCoefficientsView';

export const dynamic = 'force-dynamic';

// 顧客#14: 52週 季節係数（男女別×商品タイプ子別）の確認画面。
export default function SeasonalPage() {
  return <SeasonalCoefficientsView />;
}
