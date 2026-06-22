'use client';

import { Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import { LayoutGrid } from 'lucide-react';
import { EmptyState } from '@/components/EmptyState';
import { ProductDashboardView } from '@/components/views/ProductDashboardView';

function ProductDashContent() {
  const search = useSearchParams();
  const code = search.get('q');

  if (!code) {
    return (
      <EmptyState
        icon={LayoutGrid}
        title="商品ダッシュボード"
        description="ヘッダーの「ダッシュボード品番」にブランド品番を入力して「ダッシュボード」ボタンをクリックしてください"
      />
    );
  }

  return <ProductDashboardView code={code} />;
}

export default function ProductDashboardPage() {
  return (
    <Suspense fallback={<div className="p-8 text-gray-400">読み込み中…</div>}>
      <ProductDashContent />
    </Suspense>
  );
}
