'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Package, Truck, Boxes, Users, Calculator,
  BarChart3, LayoutGrid, Globe, Database, HelpCircle
} from 'lucide-react';

const TABS = [
  { href: '/dashboard',           label: '商品管理',       icon: Package    },
  { href: '/dashboard/logistics', label: '物流管理',       icon: Truck      },
  { href: '/dashboard/inventory', label: '在庫管理',       icon: Boxes      },
  { href: '/dashboard/customers', label: '顧客・注文管理', icon: Users      },
  { href: '/dashboard/finance',   label: '会計・精算',      icon: Calculator },
  { href: '/dashboard/analytics', label: '分析',           icon: BarChart3,  highlight: 'cyan'   },
  { href: '/dashboard/product',   label: 'ダッシュボード', icon: LayoutGrid, highlight: 'orange' },
  { href: '/dashboard/site',      label: 'サイト管理',      icon: Globe      },
  { href: '/dashboard/master',    label: 'マスター管理',    icon: Database   },
  { href: '/dashboard/help',      label: 'ヘルプ',         icon: HelpCircle },
];

export function TabNav() {
  const pathname = usePathname();

  return (
    <nav className="h-10 bg-[#374151] flex items-center px-2 text-xs">
      {TABS.map((tab) => {
        const Icon = tab.icon;
        const isActive = pathname === tab.href ||
                         (tab.href !== '/dashboard' && pathname?.startsWith(tab.href));

        let bg = '';
        if (isActive) {
          if (tab.highlight === 'cyan')        bg = 'bg-cyan-600 text-white';
          else if (tab.highlight === 'orange') bg = 'bg-orange-500 text-white';
          else                                  bg = 'bg-gray-600 text-white';
        } else {
          bg = 'text-gray-300 hover:text-white hover:bg-gray-600';
        }

        return (
          <Link
            key={tab.href}
            href={tab.href}
            className={`inline-flex items-center gap-1.5 h-full px-3 transition-colors ${bg}`}
          >
            <Icon className="w-3.5 h-3.5" />
            <span>{tab.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
