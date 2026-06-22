'use client';

import { LucideIcon } from 'lucide-react';

export function EmptyState({
  icon: Icon,
  title,
  description,
  hint,
}: {
  icon: LucideIcon;
  title: string;
  description?: string;
  hint?: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-24 px-6 text-center">
      <div className="w-16 h-16 rounded-lg flex items-center justify-center mb-4">
        <Icon className="w-12 h-12 text-gray-300" strokeWidth={1.5} />
      </div>
      <h2 className="text-base font-bold text-gray-700">{title}</h2>
      {description && (
        <p className="mt-2 text-sm text-gray-500 max-w-md">{description}</p>
      )}
      {hint && (
        <p className="mt-1 text-xs text-gray-400">{hint}</p>
      )}
    </div>
  );
}
