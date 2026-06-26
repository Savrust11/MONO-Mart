'use client';
import { STOCK_STATUS_DEFS } from '@/lib/utils';

// 在庫ステータスの判定基準を画面に表示（社内共有用・日本語）。
export function StockStatusLegend() {
  return (
    <details className="bg-white border border-gray-200 rounded text-[12px]">
      <summary className="px-3 py-2 cursor-pointer text-gray-700 font-medium select-none">
        在庫ステータスの判定基準（クリックで開く）
      </summary>
      <div className="px-3 pb-3 pt-1 space-y-1.5">
        <p className="text-[11px] text-gray-500">
          在庫日数 ＝ フリー在庫 ÷ 直近の日販。「あと何日で売り切れるか」を表します。
        </p>
        <table className="border-collapse">
          <tbody>
            {STOCK_STATUS_DEFS.map((s) => (
              <tr key={s.key} className="align-top">
                <td className="py-1 pr-3 whitespace-nowrap">
                  <span className={`inline-block font-bold rounded px-2 py-0.5 text-[11px] ${s.badge}`}>{s.label}</span>
                </td>
                <td className="py-1 text-gray-700">{s.rule}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="text-[11px] text-amber-600">
          ※ 季節品（春・夏・秋・冬）は、本来「シーズン期限前の消化」を基準とします（春4/30・夏7/31・秋10/31・冬1月末）。
          現在は品番ごとの季節区分データが未整備のため、暫定で通年基準（90日）を適用しています。
        </p>
      </div>
    </details>
  );
}
