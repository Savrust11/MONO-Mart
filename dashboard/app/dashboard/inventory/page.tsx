'use client';

import { AppHeader } from '@/components/AppHeader';
import { Boxes, AlertCircle, Package, TrendingDown } from 'lucide-react';

export default function InventoryPage() {
  return (
    <>
      <AppHeader breadcrumbs={['在庫管理']} />
      <main className="flex-1 px-8 py-6 overflow-y-auto">
        <h1 className="text-2xl font-bold text-gray-900 mb-2">在庫管理</h1>
        <p className="text-sm text-gray-600 mb-6">SKU別在庫状況・滞留商品・入荷予定の一元管理</p>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <PlaceholderCard
            icon={Boxes}
            title="倉庫在庫"
            desc="SKU毎・入荷日毎の在庫状況"
            href="/dashboard/analytics"
          />
          <PlaceholderCard
            icon={AlertCircle}
            title="欠品アラート"
            desc="在庫切れ・低在庫商品の通知"
            href="/dashboard/analytics?urgency=CRITICAL"
          />
          <PlaceholderCard
            icon={Package}
            title="入荷予定"
            desc="MMS・Tableau連携の入荷スケジュール"
            href="/dashboard/analytics"
          />
          <PlaceholderCard
            icon={TrendingDown}
            title="滞留在庫"
            desc="90日超の過剰在庫分析"
            href="/dashboard/analytics?urgency=OVERSTOCK"
          />
        </div>
      </main>
    </>
  );
}

function PlaceholderCard({ icon: Icon, title, desc, href }: any) {
  return (
    <a href={href} className="block p-5 bg-white border border-gray-200 rounded-lg hover:border-indigo-400 hover:shadow-md transition-all">
      <Icon className="w-6 h-6 text-indigo-600 mb-2" />
      <h3 className="text-sm font-semibold text-gray-900">{title}</h3>
      <p className="text-xs text-gray-600 mt-1">{desc}</p>
    </a>
  );
}
