'use client';

import { useEffect, useRef, useState } from 'react';

// 画面中央に表示する円形プログレス。
//   active=true（取得中）: 0→約92% へ減速しながら上昇。
//   active=false（完了）  : 100% に。
// ※ BigQuery API は途中経過を返さないため % は時間ベースの推定（完了時のみ実値100%）。
export function CircularProgress({ active, label = '読み込み中', size = 132, onDone }:
  { active: boolean; label?: string; size?: number; onDone?: () => void }) {
  const [pct, setPct] = useState(6);
  const idRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const onDoneRef = useRef(onDone);
  onDoneRef.current = onDone;

  useEffect(() => {
    if (active) {
      setPct(6);   // 再取得（フィルタ変更等）でも 6%→92% の上昇を毎回やり直す
      idRef.current = setInterval(() => {
        setPct((p) => Math.min(92, p + Math.max(0.5, (92 - p) * 0.08)));
      }, 130);
      return () => { if (idRef.current) { clearInterval(idRef.current); idRef.current = null; } };
    }
    // 完了: 100% まで満たしてから（リングが切れないよう）親へ完了通知
    if (idRef.current) { clearInterval(idRef.current); idRef.current = null; }
    setPct(100);
    const t = setTimeout(() => onDoneRef.current?.(), 480);
    return () => clearTimeout(t);
  }, [active]);

  const stroke = 9;
  const r = (size - stroke) / 2;
  const circ = 2 * Math.PI * r;
  const offset = circ * (1 - Math.min(100, pct) / 100);
  const done = pct >= 100;

  return (
    <div className="flex flex-col items-center justify-center min-h-[65vh] gap-5">
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} className="-rotate-90">
          <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#e5e7eb" strokeWidth={stroke} />
          <circle
            cx={size / 2} cy={size / 2} r={r} fill="none" stroke="url(#cpgrad)" strokeWidth={stroke}
            strokeLinecap="round" strokeDasharray={circ} strokeDashoffset={offset}
            style={{ transition: 'stroke-dashoffset 0.2s ease-out' }}
          />
          <defs>
            <linearGradient id="cpgrad" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor="#6366f1" />
              <stop offset="100%" stopColor="#22d3ee" />
            </linearGradient>
          </defs>
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-2xl font-bold tabular-nums bg-gradient-to-r from-indigo-600 to-cyan-500 bg-clip-text text-transparent">
            {Math.round(pct)}<span className="text-base">%</span>
          </span>
        </div>
      </div>
      <div className="text-center">
        <div className="text-sm font-medium text-gray-700">{done ? '完了' : `${label}…`}</div>
        <div className="text-[11px] text-gray-400 mt-0.5">BigQuery から集計しています</div>
      </div>
    </div>
  );
}
