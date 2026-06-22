'use client';

import { AppHeader } from '@/components/AppHeader';
import { BookOpen, Code, Mail, AlertCircle } from 'lucide-react';

export default function HelpPage() {
  return (
    <>
      <AppHeader breadcrumbs={['ヘルプ']} />
      <main className="flex-1 px-8 py-6 overflow-y-auto max-w-4xl">
        <h1 className="text-2xl font-bold text-gray-900 mb-6">ヘルプ・サポート</h1>

        <div className="space-y-6">
          <section className="p-5 bg-white border border-gray-200 rounded-lg">
            <h2 className="text-base font-semibold text-gray-900 flex items-center gap-2 mb-3">
              <BookOpen className="w-4 h-4 text-indigo-600" />
              システム概要
            </h2>
            <p className="text-sm text-gray-700 leading-relaxed">
              MONO BACK OFFICE は、ZOZOTOWN多ブランド運営のための統合分析プラットフォームです。
              バックエンドは GCP（BigQuery）上に構築され、Manus スキルと連携して
              発注判断支援・MD計画・併売分析等を提供します。
            </p>
          </section>

          <section className="p-5 bg-white border border-gray-200 rounded-lg">
            <h2 className="text-base font-semibold text-gray-900 flex items-center gap-2 mb-3">
              <Code className="w-4 h-4 text-indigo-600" />
              データソース
            </h2>
            <ul className="text-sm text-gray-700 space-y-1.5 list-disc list-inside">
              <li>ZOZO バックオフィス CSV（受注・発送・在庫・予約・商品マスタ・ZOZOAD・セール・クーポン除外）</li>
              <li>MMS（原価・着荷データ）</li>
              <li>Tableau（発注明細・予約管理）</li>
              <li>sitateru（商品マスタ・アイテムリスト）</li>
              <li>Google スプレッドシート（PF手数料・予約管理表）</li>
            </ul>
          </section>

          <section className="p-5 bg-amber-50 border border-amber-200 rounded-lg">
            <h2 className="text-base font-semibold text-amber-900 flex items-center gap-2 mb-3">
              <AlertCircle className="w-4 h-4" />
              既知の制約
            </h2>
            <ul className="text-sm text-amber-900 space-y-1.5 list-disc list-inside">
              <li>KPI 計算式は <code>分析表イメージ.pdf</code> から逆算した推定値です。本番運用前にクライアント側での確認が必要です。</li>
              <li>sitateru 商品マスタの絞り込み条件は協議中です（10月切替・3月切替案）。</li>
              <li>Phase 2 機能（買い回りデータ・検索キーワード分析・アクセス実績）は未実装です。</li>
            </ul>
          </section>

          <section className="p-5 bg-white border border-gray-200 rounded-lg">
            <h2 className="text-base font-semibold text-gray-900 flex items-center gap-2 mb-3">
              <Mail className="w-4 h-4 text-indigo-600" />
              お問い合わせ
            </h2>
            <p className="text-sm text-gray-700">
              担当: 山口由人（yujin-yamaguchi@mono-mart.jp）
            </p>
          </section>
        </div>
      </main>
    </>
  );
}
