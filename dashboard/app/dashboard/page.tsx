'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import {
  Package, ShoppingBag, Boxes, AlertCircle, Activity,
  TrendingUp, BarChart3, Calendar, Sparkles, ArrowRight
} from 'lucide-react';

interface SystemStats {
  total_products: number;
  total_skus: number;
  total_inventory: number;
  critical_count: number;
  warning_count: number;
}

const SHORTCUTS = [
  { title: '同一品番併売',     desc: '同一品番のカラー・サイズ別併売状況', href: '/dashboard/analytics?view=cross-buy', icon: Package, color: 'cyan' },
  { title: '発注推奨データ',    desc: '在庫日数・トレンドから発注推奨',      href: '/dashboard/analytics?view=order-recommend', icon: ShoppingBag, color: 'green' },
  { title: 'リピート発注表作成', desc: '発注管理表をV2ロジックで自動生成',     href: '/dashboard/analytics?view=repeat-order', icon: TrendingUp, color: 'rose' },
  { title: 'MD計画',           desc: 'カテゴリ別MD計画と提案',              href: '/dashboard/analytics?view=md-plan',  icon: BarChart3, color: 'amber' },
  { title: '商品ダッシュボード', desc: '品番別の詳細KPI表示',                href: '/dashboard/product',                icon: Boxes,  color: 'blue' },
  { title: 'データ取得状況',    desc: 'ZOZO自動取得の最終状態を監視',         href: '/dashboard/ingestion',              icon: Activity, color: 'green' },
  { title: 'Manus スキル',     desc: '12種のManusスキルをUIから実行',       href: '/dashboard/manus',                  icon: Sparkles, color: 'violet' },
];

export default function DashboardHome() {
  const [stats, setStats] = useState<SystemStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/stats')
      .then(r => r.ok ? r.json() : null)
      .then(setStats)
      .catch(() => setStats(null))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="px-6 py-4">
      {/* Welcome */}
      <div className="mb-4">
        <p className="text-xs text-gray-500">商品管理</p>
        <h1 className="text-lg font-bold text-gray-900 mt-0.5">ようこそ、MONO BACK OFFICE へ</h1>
        <p className="text-xs text-gray-600 mt-1">
          ZOZOTOWN 多ブランド運営のための統合管理プラットフォーム
        </p>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-5">
        <Stat label="商品マスタ"  value={stats?.total_products}  unit="品番" icon={Package}     color="indigo" loading={loading} />
        <Stat label="登録 SKU"   value={stats?.total_skus}      unit="SKU"  icon={Boxes}       color="blue"   loading={loading} />
        <Stat label="在庫数"     value={stats?.total_inventory} unit="点"   icon={ShoppingBag} color="green"  loading={loading} />
        <Stat label="欠品 SKU"   value={stats?.critical_count}  unit="件"   icon={AlertCircle} color="red"    loading={loading} />
        <Stat label="警告 SKU"   value={stats?.warning_count}   unit="件"   icon={Activity}    color="amber"  loading={loading} />
      </div>

      {/* Shortcuts */}
      <h2 className="text-xs font-bold text-gray-700 mb-2">よく使う機能</h2>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        {SHORTCUTS.map(s => (
          <Shortcut key={s.title} {...s} />
        ))}
      </div>
    </div>
  );
}

function Stat({
  label, value, unit, icon: Icon, color, loading,
}: any) {
  const accents: Record<string, string> = {
    indigo: 'from-indigo-500 to-indigo-600',
    blue:   'from-blue-500   to-blue-600',
    green:  'from-emerald-500 to-emerald-600',
    red:    'from-red-500    to-red-600',
    amber:  'from-amber-500  to-amber-600',
  };
  return (
    <div className="bg-white border border-gray-200 rounded p-3 relative overflow-hidden">
      <div className={`absolute top-0 left-0 right-0 h-0.5 bg-gradient-to-r ${accents[color]}`} />
      <div className="flex items-center gap-1.5 mb-1">
        <Icon className="w-3 h-3 text-gray-400" />
        <span className="text-[10px] font-medium text-gray-500 uppercase tracking-wider">{label}</span>
      </div>
      <div className="text-xl font-bold text-gray-900 tabular-nums">
        {loading ? <span className="text-gray-300">—</span> : (value != null ? value.toLocaleString('ja-JP') : '—')}
        <span className="text-[10px] text-gray-400 font-normal ml-1">{unit}</span>
      </div>
    </div>
  );
}

function Shortcut({ title, desc, href, icon: Icon, color }: any) {
  const colorMap: Record<string, { bg: string; text: string }> = {
    cyan:   { bg: 'bg-cyan-50',   text: 'text-cyan-600' },
    green:  { bg: 'bg-green-50',  text: 'text-green-600' },
    rose:   { bg: 'bg-rose-50',   text: 'text-rose-600' },
    amber:  { bg: 'bg-amber-50',  text: 'text-amber-600' },
    blue:   { bg: 'bg-blue-50',   text: 'text-blue-600' },
    violet: { bg: 'bg-violet-50', text: 'text-violet-600' },
  };
  const c = colorMap[color] || colorMap.cyan;
  return (
    <Link
      href={href}
      className="group block bg-white border border-gray-200 rounded p-3 hover:border-cyan-400 hover:shadow-sm transition-all"
    >
      <div className="flex items-start justify-between mb-2">
        <div className={`w-8 h-8 rounded ${c.bg} ${c.text} flex items-center justify-center`}>
          <Icon className="w-4 h-4" />
        </div>
        <ArrowRight className="w-3.5 h-3.5 text-gray-300 group-hover:text-cyan-600 group-hover:translate-x-0.5 transition-all" />
      </div>
      <h3 className="text-sm font-bold text-gray-900">{title}</h3>
      <p className="text-[11px] text-gray-600 mt-0.5">{desc}</p>
    </Link>
  );
}
