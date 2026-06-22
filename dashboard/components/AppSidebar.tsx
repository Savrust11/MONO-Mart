'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Package, Truck, Boxes, Users, Calculator,
  BarChart3, Globe, Database, HelpCircle,
  Sparkles, Layout, ChevronDown
} from 'lucide-react';

const NAV_GROUPS = [
  {
    title: '運営',
    items: [
      { href: '/dashboard',           label: '商品管理',          icon: Package    },
      { href: '/dashboard/logistics', label: '物流管理',          icon: Truck      },
      { href: '/dashboard/inventory', label: '在庫管理',          icon: Boxes      },
      { href: '/dashboard/customers', label: '顧客・注文管理',     icon: Users      },
      { href: '/dashboard/finance',   label: '会計・精算',         icon: Calculator },
    ],
  },
  {
    title: '分析・運用',
    items: [
      { href: '/dashboard/analytics', label: '分析ダッシュボード', icon: BarChart3  },
      { href: '/dashboard/site',      label: 'サイト管理',         icon: Globe      },
      { href: '/dashboard/master',    label: 'マスター管理',       icon: Database   },
    ],
  },
  {
    title: 'Manus 連携',
    items: [
      { href: '/dashboard/monobo',    label: 'MONOPO (UI)',        icon: Layout    },
      { href: '/dashboard/manus',     label: 'Manus スキル',       icon: Sparkles  },
    ],
  },
];

export function AppSidebar() {
  const pathname = usePathname();

  const renderItem = (item: { href: string; label: string; icon: any }) => {
    const Icon = item.icon;
    const isActive = pathname === item.href ||
                     (item.href !== '/dashboard' && pathname?.startsWith(item.href));
    return (
      <Link
        key={item.href}
        href={item.href}
        className={`
          group relative flex items-center gap-3 px-3 py-2 text-sm rounded-lg transition-all
          ${isActive
            ? 'bg-indigo-50 text-indigo-700 font-semibold'
            : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'}
        `}
      >
        {isActive && (
          <span className="absolute left-0 top-1.5 bottom-1.5 w-1 rounded-r bg-indigo-600" />
        )}
        <Icon className={`w-4 h-4 shrink-0 ${isActive ? 'text-indigo-600' : 'text-gray-400 group-hover:text-gray-600'}`} />
        <span>{item.label}</span>
      </Link>
    );
  };

  return (
    <aside className="w-64 bg-white border-r border-gray-200 flex flex-col h-screen sticky top-0 shadow-sm">
      {/* Brand */}
      <div className="h-16 flex items-center px-5 border-b border-gray-200">
        <Link href="/dashboard" className="flex items-center gap-2.5 group">
          <div className="w-9 h-9 rounded-lg gradient-indigo flex items-center justify-center text-white font-bold text-base shadow-md">
            M
          </div>
          <div>
            <div className="text-sm font-bold text-gray-900 tracking-tight leading-tight">
              MONO BACK OFFICE
            </div>
            <div className="text-[10px] text-gray-500 leading-tight">統合分析プラットフォーム</div>
          </div>
        </Link>
      </div>

      {/* Workspace switcher */}
      <div className="px-3 pt-3 pb-2">
        <button className="w-full flex items-center justify-between px-3 py-2 text-sm rounded-lg bg-gray-50 hover:bg-gray-100 border border-gray-200">
          <div className="flex items-center gap-2 min-w-0">
            <div className="w-6 h-6 rounded bg-gradient-to-br from-pink-500 to-orange-500 text-white text-xs font-bold flex items-center justify-center shrink-0">
              M
            </div>
            <span className="font-medium text-gray-900 truncate">MONO-MART</span>
          </div>
          <ChevronDown className="w-3.5 h-3.5 text-gray-400 shrink-0" />
        </button>
      </div>

      {/* Nav groups */}
      <nav className="flex-1 px-3 py-2 space-y-5 overflow-y-auto">
        {NAV_GROUPS.map((g) => (
          <div key={g.title}>
            <div className="px-3 pb-1.5 text-[10px] font-semibold text-gray-400 uppercase tracking-wider">
              {g.title}
            </div>
            <div className="space-y-0.5">
              {g.items.map(renderItem)}
            </div>
          </div>
        ))}
      </nav>

      {/* Footer */}
      <div className="px-3 py-3 border-t border-gray-200">
        <Link
          href="/dashboard/help"
          className="flex items-center gap-3 px-3 py-2 text-sm rounded-lg text-gray-600 hover:bg-gray-50 hover:text-gray-900"
        >
          <HelpCircle className="w-4 h-4 text-gray-400" />
          <span>ヘルプ</span>
        </Link>
      </div>
    </aside>
  );
}
