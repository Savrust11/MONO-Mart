'use client';

import { AppHeader } from '@/components/AppHeader';
import { Construction } from 'lucide-react';

export function PlaceholderPage({
  title,
  description,
  breadcrumbs,
}: {
  title: string;
  description: string;
  breadcrumbs: string[];
}) {
  return (
    <>
      <AppHeader breadcrumbs={breadcrumbs} />
      <main className="flex-1 px-8 py-6 overflow-y-auto">
        <h1 className="text-2xl font-bold text-gray-900 mb-2">{title}</h1>
        <p className="text-sm text-gray-600 mb-8">{description}</p>

        <div className="max-w-md mx-auto mt-12 text-center">
          <Construction className="w-12 h-12 text-amber-400 mx-auto mb-3" />
          <h2 className="text-base font-medium text-gray-700">準備中</h2>
          <p className="text-sm text-gray-500 mt-1">
            この機能は Phase 2 で実装予定です。
          </p>
        </div>
      </main>
    </>
  );
}
