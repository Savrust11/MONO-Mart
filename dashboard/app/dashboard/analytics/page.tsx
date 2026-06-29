'use client';

import { Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import { EmptyState } from '@/components/EmptyState';
import { BarChart3, Package, ShoppingCart, FileSpreadsheet, Repeat, TrendingUp } from 'lucide-react';
import { RepeatOrderForm } from '@/components/views/RepeatOrderForm';
import { OrderAnalysisView } from '@/components/views/OrderAnalysisView';
import { MdPlanView } from '@/components/views/MdPlanView';
import { CategoryTrendView } from '@/components/views/CategoryTrendView';

function AnalyticsContent() {
  const search = useSearchParams();
  const view = search.get('view');

  // Switch between views based on ?view= query
  switch (view) {
    case 'repeat-order':
      return <RepeatOrderForm />;
    case 'md-plan':
      return <MdPlanView />;
    case 'category-trend':
      return <CategoryTrendView />;
    case 'order-recommend':
      return <OrderAnalysisView />;
    case 'cross-buy':
      return (
        <EmptyState
          icon={BarChart3}
          title="同一品番併売分析"
          description="ヘッダーの検索バーにブランド品番を入力して分析を開始してください"
          hint="例: ls891 (比較品番は空欄で自動選択されます)"
        />
      );
    case 'brand-cross':
      return (
        <EmptyState
          icon={TrendingUp}
          title="ブランド間併売分析"
          description="ヘッダーの「対象品番」を入力すると、ブランド間の購買パターンを分析します"
        />
      );
    case 'category-cross':
      return (
        <EmptyState
          icon={Package}
          title="カテゴリ間併売分析"
          description="カテゴリ間の併売傾向と相関分析を表示します"
        />
      );
    case 'daily-sales':
      return (
        <EmptyState
          icon={TrendingUp}
          title="日別売上推移"
          description="ヘッダーの「対象品番」を入力すると、日別売上推移を表示します"
        />
      );
    case 'cat-sales':
      return (
        <EmptyState
          icon={BarChart3}
          title="カテゴリ別売上"
          description="ブランド・カテゴリ別の売上推移と予測を表示します"
        />
      );
    case 'sku-sales':
      return (
        <EmptyState
          icon={ShoppingCart}
          title="品番別売上"
          description="ヘッダーの「対象品番」を入力すると、品番ごとの売上推移を表示します"
        />
      );
    case 'stock-forecast':
      return (
        <EmptyState
          icon={TrendingUp}
          title="在庫消化予測"
          description="カテゴリ別係数と在庫データから将来の在庫消化を予測します"
        />
      );
    case 'dead-stock':
      return (
        <EmptyState
          icon={Package}
          title="不動在庫分析"
          description="90日以上滞留している過剰在庫を分析します"
        />
      );
    case 'repeat-sim':
      return (
        <EmptyState
          icon={Repeat}
          title="リピートシミュレーション"
          description="リピート発注の各種シナリオをシミュレーションします"
        />
      );
    default:
      // No view selected — default landing
      return (
        <EmptyState
          icon={BarChart3}
          title="分析を開始"
          description="左メニューから分析項目を選択してください"
        />
      );
  }
}

export default function AnalyticsPage() {
  return (
    <Suspense fallback={<div className="p-8 text-gray-400">読み込み中…</div>}>
      <AnalyticsContent />
    </Suspense>
  );
}
