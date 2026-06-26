'use client';

import { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ChevronRight, ChevronDown } from 'lucide-react';

interface TreeItem {
  label: string;
  href?: string;
  children?: { label: string; href: string }[];
}

// 分析タブのツリー（/dashboard/analytics と /dashboard/seasonal で共用）
const ANALYTICS_TREE: TreeItem[] = [
  {
    label: '併売分析',
    children: [
      { label: '同一品番併売',  href: '/dashboard/analytics?view=cross-buy' },
      { label: 'ブランド間併売', href: '/dashboard/analytics?view=brand-cross' },
      { label: 'カテゴリ間併売', href: '/dashboard/analytics?view=category-cross' },
    ],
  },
  {
    label: '売上分析',
    children: [
      { label: '日別売上推移',  href: '/dashboard/analytics?view=daily-sales' },
      { label: 'カテゴリ別売上', href: '/dashboard/analytics?view=cat-sales' },
      { label: '品番別売上',    href: '/dashboard/analytics?view=sku-sales' },
    ],
  },
  {
    label: '在庫分析',
    children: [
      { label: '在庫消化予測', href: '/dashboard/analytics?view=stock-forecast' },
      { label: '不動在庫分析', href: '/dashboard/analytics?view=dead-stock' },
    ],
  },
  {
    label: 'リピート分析',
    children: [
      { label: 'リピートシミュレーション', href: '/dashboard/analytics?view=repeat-sim' },
      { label: '発注推奨データ',          href: '/dashboard/analytics?view=order-recommend' },
      { label: 'リピート発注表作成',      href: '/dashboard/analytics?view=repeat-order' },
      { label: '52週 季節係数',           href: '/dashboard/seasonal' },
    ],
  },
  {
    label: 'MD計画',
    children: [
      { label: 'MD計画・提案', href: '/dashboard/analytics?view=md-plan' },
    ],
  },
  {
    label: 'ダッシュボード',
    children: [
      { label: '商品ダッシュボード', href: '/dashboard/product' },
    ],
  },
  {
    label: 'システム監視',
    children: [
      { label: 'データ取得状況', href: '/dashboard/ingestion' },
    ],
  },
];

// Tree per top-tab section. Renders the section matching current path prefix.
const TREES: Record<string, TreeItem[]> = {
  '/dashboard/analytics': ANALYTICS_TREE,
  '/dashboard/seasonal': ANALYTICS_TREE,
  '/dashboard/product': [
    {
      label: '併売分析',
      children: [
        { label: '同一品番併売', href: '/dashboard/analytics?view=cross-buy' },
        { label: 'ブランド間併売', href: '/dashboard/analytics?view=brand-cross' },
        { label: 'カテゴリ間併売', href: '/dashboard/analytics?view=category-cross' },
      ],
    },
    {
      label: '売上分析',
      children: [],
    },
    {
      label: '在庫分析',
      children: [],
    },
    {
      label: 'リピート分析',
      children: [],
    },
    {
      label: 'MD計画',
      children: [],
    },
    {
      label: 'ダッシュボード',
      children: [
        { label: '商品ダッシュボード', href: '/dashboard/product' },
      ],
    },
  ],
};

function getActiveTree(pathname: string | null): TreeItem[] | null {
  if (!pathname) return null;
  for (const [prefix, tree] of Object.entries(TREES)) {
    if (pathname.startsWith(prefix)) return tree;
  }
  return null;
}

export function TreeSidebar() {
  const pathname = usePathname();
  const tree = getActiveTree(pathname);

  // Track open state per group label
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>(() => {
    const initial: Record<string, boolean> = {};
    if (tree) {
      tree.forEach((g, i) => { initial[g.label] = i === 0; });
    }
    return initial;
  });

  if (!tree) return null;

  const toggle = (label: string) =>
    setOpenGroups((prev) => ({ ...prev, [label]: !prev[label] }));

  // Read query "view" so we can highlight the active sub-item
  const search = typeof window !== 'undefined'
    ? new URLSearchParams(window.location.search)
    : null;
  const currentView = search?.get('view');

  const isActive = (href: string) => {
    const [path, query] = href.split('?');
    if (path !== pathname) return false;
    if (!query) return !currentView;
    const view = new URLSearchParams(query).get('view');
    return view === currentView;
  };

  return (
    <aside className="w-56 bg-white border-r border-gray-200 flex flex-col text-[13px] overflow-y-auto">
      <ul className="py-2">
        {tree.map((group) => {
          const open = openGroups[group.label] ?? true;
          const Chevron = open ? ChevronDown : ChevronRight;

          return (
            <li key={group.label}>
              <button
                onClick={() => toggle(group.label)}
                className="w-full flex items-center gap-1 px-3 py-2 hover:bg-gray-50 text-left"
              >
                <Chevron className="w-3.5 h-3.5 text-gray-500 shrink-0" />
                <span className="font-bold text-gray-800">{group.label}</span>
              </button>

              {open && group.children && group.children.length > 0 && (
                <ul>
                  {group.children.map((child) => (
                    <li key={child.href}>
                      <Link
                        href={child.href}
                        className={`block pl-8 pr-3 py-1.5 text-[13px] transition-colors ${
                          isActive(child.href)
                            ? 'bg-sky-50 text-sky-600 font-bold border-l-[3px] border-sky-500 -ml-[3px] pl-[33px]'
                            : 'text-gray-700 hover:bg-gray-50 hover:text-gray-900'
                        }`}
                      >
                        ・{child.label}
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          );
        })}
      </ul>
    </aside>
  );
}
