'use client';

import { useEffect, useRef, useState } from 'react';

// データ取得中の進捗バー。数値%を表示。
//   active=true（取得中）: 0→約92% へ減速しながら上昇。
//   active=false（取得完了）: 100% まで上げてから onDone を呼ぶ（親はそこで本体表示に切替）。
// ※ BigQuery API は途中経過を返さないため % は時間ベースの推定。完了時のみ実値100%。
export function LoadingProgress({ active, label = '集計中', onDone }:
  { active: boolean; label?: string; onDone?: () => void }) {
  const [pct, setPct] = useState(6);
  const idRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const onDoneRef = useRef(onDone);
  onDoneRef.current = onDone;

  useEffect(() => {
    if (active) {
      // 取得中: 92% に向けて減速しながら上昇
      idRef.current = setInterval(() => {
        setPct((p) => Math.min(92, p + Math.max(0.5, (92 - p) * 0.08)));
      }, 130);
      return () => { if (idRef.current) { clearInterval(idRef.current); idRef.current = null; } };
    }
    // 完了: 100% へ上げ、少し見せてから親へ完了通知
    if (idRef.current) { clearInterval(idRef.current); idRef.current = null; }
    setPct(100);
    const t = setTimeout(() => onDoneRef.current?.(), 550);
    return () => clearTimeout(t);
  }, [active]);

  const done = pct >= 100;
  return (
    <div className="px-6 py-12 max-w-xl mx-auto">
      <div className="flex items-end justify-between mb-2">
        <span className="text-sm font-medium text-gray-700">{done ? '完了' : `${label}…`}</span>
        <span className="text-3xl font-bold tabular-nums bg-gradient-to-r from-indigo-600 to-cyan-500 bg-clip-text text-transparent">
          {Math.round(pct)}<span className="text-lg">%</span>
        </span>
      </div>
      <div className="h-3.5 w-full rounded-full bg-gray-200/70 overflow-hidden shadow-inner">
        <div
          className={`h-full rounded-full bg-gradient-to-r from-indigo-500 via-blue-500 to-cyan-400 transition-[width] ease-out relative ${done ? 'duration-300' : 'duration-200'}`}
          style={{ width: `${pct}%` }}
        >
          {!done && <div className="absolute inset-0 bg-white/25 animate-pulse" />}
        </div>
      </div>
      <p className="mt-2 text-[11px] text-gray-400">
        {done ? 'データ取得が完了しました' : 'BigQuery から実数を集計しています…'}
      </p>
    </div>
  );
}
