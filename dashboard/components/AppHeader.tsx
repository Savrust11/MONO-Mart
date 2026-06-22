'use client';

import { useState } from 'react';
import { Search, Bell, ChevronDown, User } from 'lucide-react';

export function AppHeader({ breadcrumbs }: { breadcrumbs?: string[] }) {
  const [search, setSearch] = useState('');

  return (
    <header className="h-14 bg-white border-b border-gray-200 flex items-center px-6 sticky top-0 z-30">
      {/* Breadcrumbs */}
      <div className="flex-1 flex items-center gap-2 text-sm text-gray-600">
        <span className="text-gray-900 font-medium">MONO BACK OFFICE</span>
        {breadcrumbs?.map((b, i) => (
          <span key={i} className="flex items-center gap-2">
            <span className="text-gray-400">/</span>
            <span className={i === (breadcrumbs.length - 1) ? 'text-gray-900' : ''}>{b}</span>
          </span>
        ))}
      </div>

      {/* Search */}
      <div className="relative w-80">
        <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="ブランド品番で検索 (例: ls891)"
          className="w-full pl-9 pr-4 py-2 text-sm border border-gray-300 rounded-md
                     focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
        />
      </div>

      {/* Right actions */}
      <div className="ml-4 flex items-center gap-3">
        <button className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-md">
          <Bell className="w-4 h-4" />
        </button>
        <button className="flex items-center gap-2 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-100 rounded-md">
          <div className="w-7 h-7 rounded-full bg-indigo-100 flex items-center justify-center">
            <User className="w-4 h-4 text-indigo-600" />
          </div>
          <span>山口</span>
          <ChevronDown className="w-3 h-3" />
        </button>
      </div>
    </header>
  );
}
