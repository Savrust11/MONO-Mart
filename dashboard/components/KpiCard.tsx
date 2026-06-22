'use client';
import { ReactNode } from 'react';
import { clsx } from 'clsx';

interface KpiCardProps {
  label: string;
  value: string | number;
  sub?: string;
  accent?: 'red' | 'amber' | 'green' | 'blue' | 'default';
  icon?: ReactNode;
}

const accentMap = {
  red:     'border-red-400 bg-red-50',
  amber:   'border-amber-400 bg-amber-50',
  green:   'border-green-400 bg-green-50',
  blue:    'border-blue-400 bg-blue-50',
  default: 'border-gray-200 bg-white',
};

export function KpiCard({ label, value, sub, accent = 'default', icon }: KpiCardProps) {
  return (
    <div className={clsx(
      'rounded-lg border-l-4 p-4 shadow-sm',
      accentMap[accent]
    )}>
      <div className="flex items-center justify-between">
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{label}</p>
        {icon && <span className="text-gray-400">{icon}</span>}
      </div>
      <p className="mt-1 text-2xl font-bold text-gray-900">{value}</p>
      {sub && <p className="mt-0.5 text-xs text-gray-500">{sub}</p>}
    </div>
  );
}
