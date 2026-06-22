'use client';
import { URGENCY_STYLES } from '@/lib/utils';

type Urgency = 'CRITICAL' | 'WARNING' | 'OK' | 'OVERSTOCK';

interface AlertBadgeProps {
  urgency: Urgency;
  size?: 'sm' | 'md';
}

export function AlertBadge({ urgency, size = 'md' }: AlertBadgeProps) {
  const style = URGENCY_STYLES[urgency];
  const padding = size === 'sm' ? 'px-1.5 py-0.5 text-[10px]' : 'px-2 py-1 text-xs';

  return (
    <span className={`inline-block font-bold rounded ${padding} ${style.badge}`}>
      {style.label}
    </span>
  );
}
