'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Search, LayoutGrid, Bell } from 'lucide-react';
import Link from 'next/link';

export function TopHeader() {
  const router = useRouter();
  const [target, setTarget]   = useState('');
  const [compare, setCompare] = useState('');
  const [dashCode, setDashCode] = useState('');

  const onAnalyze = () => {
    const params = new URLSearchParams();
    if (target)  params.set('q', target);
    if (compare) params.set('compare', compare);
    router.push(`/dashboard/analytics${params.toString() ? '?' + params.toString() : ''}`);
  };

  const onDashboard = () => {
    const params = new URLSearchParams();
    if (dashCode) params.set('q', dashCode);
    router.push(`/dashboard/product${params.toString() ? '?' + params.toString() : ''}`);
  };

  return (
    <header className="h-12 bg-[#1f2937] text-gray-200 flex items-center px-4 gap-4">
      {/* Logo */}
      <Link href="/dashboard" className="font-bold text-white text-[15px] tracking-tight whitespace-nowrap">
        MONO BACK OFFICE
      </Link>

      {/* Global search */}
      <div className="flex-1 flex items-center gap-2 text-xs">
        <label className="text-gray-300 whitespace-nowrap ml-2">対象品番</label>
        <input
          type="text"
          value={target}
          onChange={(e) => setTarget(e.target.value)}
          placeholder="例: ls891"
          className="px-2 py-1 w-32 text-xs bg-white text-gray-900 rounded border border-gray-300
                     focus:outline-none focus:ring-1 focus:ring-cyan-400 focus:border-cyan-400"
        />

        <label className="text-gray-300 whitespace-nowrap ml-2">比較品番</label>
        <input
          type="text"
          value={compare}
          onChange={(e) => setCompare(e.target.value)}
          placeholder="空欄で自動選択"
          className="px-2 py-1 w-36 text-xs bg-white text-gray-900 rounded border border-gray-300
                     focus:outline-none focus:ring-1 focus:ring-cyan-400 focus:border-cyan-400"
        />

        <span className="text-gray-500 mx-1">|</span>

        <label className="text-orange-300 whitespace-nowrap font-medium">ダッシュボード品番</label>
        <input
          type="text"
          value={dashCode}
          onChange={(e) => setDashCode(e.target.value)}
          placeholder="例: AAsh1357"
          className="px-2 py-1 w-32 text-xs bg-white text-gray-900 rounded border border-gray-300
                     focus:outline-none focus:ring-1 focus:ring-orange-400 focus:border-orange-400"
        />

        <button
          onClick={onAnalyze}
          className="ml-2 inline-flex items-center gap-1 px-3 py-1 bg-cyan-600 hover:bg-cyan-700 text-white text-xs font-medium rounded"
        >
          <Search className="w-3 h-3" />
          分析
        </button>
        <button
          onClick={onDashboard}
          className="inline-flex items-center gap-1 px-3 py-1 bg-orange-500 hover:bg-orange-600 text-white text-xs font-medium rounded"
        >
          <LayoutGrid className="w-3 h-3" />
          ダッシュボード
        </button>
      </div>

      {/* Right side */}
      <div className="flex items-center gap-3 text-xs">
        <span className="text-gray-300">株式会社MONO-MART</span>
        <button className="p-1.5 text-gray-400 hover:text-white hover:bg-gray-700 rounded">
          <Bell className="w-4 h-4" />
        </button>
      </div>
    </header>
  );
}
