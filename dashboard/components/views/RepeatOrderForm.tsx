'use client';

import { useState } from 'react';
import { FileSpreadsheet, Search, Calendar, Tag, Sliders, Plus } from 'lucide-react';

const HOW_TO_USE = [
  { num: '1.', title: '品番を入力して確認', body: 'ブランド品番を入力し「確認」ボタンを押すと、ショップ・SKU情報が表示されます。' },
  { num: '2.', title: '発注数量・納期を入力', body: 'リピート発注の合計着数、暫定納期、在庫カバー月数を入力します。' },
  { num: '3.', title: '抑揚・新色を設定（任意）', body: '1番色重視モードや新色追加が必要な場合に設定します。' },
  { num: '4.', title: 'スプレッドシートを確認', body: '「作成」ボタンを押すと、V2ロジックで配分計算し、分析コメント付きの発注管理表が生成されます。' },
];

const ALLOC_STEPS = [
  { num: 1,  title: '参照期間の決定' },
  { num: 2,  title: '欠品期間の検出・除外' },
  { num: 3,  title: 'カラー構成比の算出' },
  { num: 4,  title: '新色枠の差し引き' },
  { num: 5,  title: 'カラー別仮配分' },
  { num: 6,  title: 'カラーミニマム判定（100着）' },
  { num: 7,  title: 'サイズ構成比の算出' },
  { num: 8,  title: 'イレギュラーSKU判定' },
  { num: 9,  title: '抑揚モード適用' },
  { num: 10, title: '10着丸め・端数処理' },
];

const OUTPUT_SHEETS = [
  { name: '発注表',        desc: 'V2配分＋分析コメント＋比較表＋画像' },
  { name: '売上実績',      desc: '10日刻みのカラー別販売推移' },
  { name: '在庫分析',      desc: 'SKU別の在庫状況データ' },
  { name: '予約管理表',    desc: '入荷予定の一覧' },
  { name: '予約一覧',      desc: '予約管理表データ' },
];

export function RepeatOrderForm() {
  const [productCode, setProductCode] = useState('');
  const [totalQty, setTotalQty] = useState('');
  const [delivery, setDelivery] = useState('');
  const [coverMonths, setCoverMonths] = useState('3');
  const [colorScope, setColorScope] = useState<'existing'|'all'|'specified'>('existing');
  const [emphasisMode, setEmphasisMode] = useState<'normal'|'top1'>('normal');
  const [addNewColor, setAddNewColor] = useState(false);
  const [memo, setMemo] = useState('');

  return (
    <div className="px-6 py-4">
      {/* Page header */}
      <div className="flex items-center gap-2 mb-3">
        <div className="w-1 h-6 bg-rose-400 rounded-r" />
        <FileSpreadsheet className="w-5 h-5 text-gray-700" />
        <h1 className="text-base font-bold text-gray-900">リピート発注表作成</h1>
        <span className="text-[11px] font-bold bg-rose-100 text-rose-600 px-1.5 py-0.5 rounded">V2</span>
        <span className="text-xs text-gray-500 ml-2">
          品番を入力してGoogle Spreadsheetに発注管理表を自動生成
        </span>
      </div>

      <div className="grid grid-cols-12 gap-4">
        {/* Main form (left, wider) */}
        <div className="col-span-12 lg:col-span-9 space-y-4">

          {/* 品番情報 */}
          <section className="bg-white border border-gray-200 rounded">
            <header className="flex items-center gap-2 px-4 py-2.5 border-b border-gray-100">
              <Tag className="w-3.5 h-3.5 text-gray-500" />
              <h2 className="text-sm font-bold text-gray-800">品番情報</h2>
            </header>
            <div className="p-4">
              <label className="block text-sm font-medium text-gray-700 mb-1.5">
                ブランド品番 <span className="text-red-500">*</span>
              </label>
              <div className="flex gap-2">
                <input
                  value={productCode}
                  onChange={(e) => setProductCode(e.target.value)}
                  placeholder="例: sc841, pt165"
                  className="flex-1 px-3 py-2 text-sm border border-gray-300 rounded
                           focus:outline-none focus:ring-2 focus:ring-cyan-500 focus:border-transparent"
                />
                <button className="inline-flex items-center gap-1 px-4 py-2 bg-cyan-600 text-white text-sm rounded hover:bg-cyan-700 disabled:opacity-50">
                  <Search className="w-3.5 h-3.5" />
                  確認
                </button>
              </div>
            </div>
          </section>

          {/* 発注設定 */}
          <section className="bg-white border border-gray-200 rounded">
            <header className="px-4 py-2.5 border-b border-gray-100">
              <h2 className="text-sm font-bold text-gray-800">発注設定</h2>
            </header>
            <div className="p-4 space-y-4">

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">
                  リピート発注総数 <span className="text-red-500">*</span>
                </label>
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    value={totalQty}
                    onChange={(e) => setTotalQty(e.target.value)}
                    placeholder="例: 6000"
                    className="flex-1 px-3 py-2 text-sm border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-cyan-500"
                  />
                  <span className="text-sm text-gray-500">着</span>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5 flex items-center gap-1.5">
                  <Calendar className="w-3.5 h-3.5 text-gray-500" />
                  暫定納期 <span className="text-red-500">*</span>
                </label>
                <input
                  type="date"
                  value={delivery}
                  onChange={(e) => setDelivery(e.target.value)}
                  className="px-3 py-2 text-sm border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-cyan-500"
                />
                <p className="text-[11px] text-gray-500 mt-1">リピートが納品される（販売開始される）日付</p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">
                  在庫カバー月数 <span className="text-red-500">*</span>
                </label>
                <select
                  value={coverMonths}
                  onChange={(e) => setCoverMonths(e.target.value)}
                  className="px-3 py-2 text-sm border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-cyan-500"
                >
                  <option value="1">1ヶ月</option>
                  <option value="2">2ヶ月</option>
                  <option value="3">3ヶ月（標準）</option>
                  <option value="4">4ヶ月</option>
                  <option value="6">6ヶ月</option>
                </select>
                <p className="text-[11px] text-gray-500 mt-1">暫定納期からこの期間分の在庫としてシミュレーション</p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">対象カラー</label>
                <div className="flex items-center gap-4 text-sm">
                  <label className="inline-flex items-center gap-1.5">
                    <input type="radio" checked={colorScope==='existing'} onChange={()=>setColorScope('existing')} />
                    既存色のみ
                  </label>
                  <label className="inline-flex items-center gap-1.5">
                    <input type="radio" checked={colorScope==='all'} onChange={()=>setColorScope('all')} />
                    全色
                  </label>
                  <label className="inline-flex items-center gap-1.5">
                    <input type="radio" checked={colorScope==='specified'} onChange={()=>setColorScope('specified')} />
                    指定色のみ
                  </label>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5 flex items-center gap-1.5">
                  <Sliders className="w-3.5 h-3.5 text-gray-500" />
                  抑揚モード
                </label>
                <div className="flex items-center gap-4 text-sm">
                  <label className="inline-flex items-center gap-1.5">
                    <input type="radio" checked={emphasisMode==='normal'} onChange={()=>setEmphasisMode('normal')} />
                    通常（統計通り）
                  </label>
                  <label className="inline-flex items-center gap-1.5">
                    <input type="radio" checked={emphasisMode==='top1'} onChange={()=>setEmphasisMode('top1')} />
                    1番色重視
                  </label>
                </div>
                <p className="text-[11px] text-gray-500 mt-1">販売実績の構成比に基づいてそのまま配分</p>
              </div>

              <div>
                <label className="inline-flex items-center gap-1.5 text-sm">
                  <input type="checkbox" checked={addNewColor} onChange={()=>setAddNewColor(!addNewColor)} />
                  <Plus className="w-3.5 h-3.5 text-gray-500" />
                  新色を追加する
                </label>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">要望・メモ（任意）</label>
                <textarea
                  value={memo}
                  onChange={(e) => setMemo(e.target.value)}
                  placeholder="例: ブラックは少なめに、Lサイズ多めに"
                  rows={3}
                  className="w-full px-3 py-2 text-sm border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-cyan-500"
                />
              </div>
            </div>
          </section>

          {/* Submit button */}
          <button className="inline-flex items-center gap-2 px-6 py-3 bg-rose-300 text-white font-bold rounded hover:bg-rose-400 transition">
            <FileSpreadsheet className="w-4 h-4" />
            スプレッドシートを作成
          </button>
        </div>

        {/* Right sidebar: 使い方 + ロジック + シート */}
        <div className="col-span-12 lg:col-span-3 space-y-4">

          <section className="bg-white border border-gray-200 rounded p-4">
            <h3 className="text-sm font-bold text-gray-800 flex items-center gap-1.5 mb-3">
              <span className="text-cyan-600">ⓘ</span>
              使い方
            </h3>
            <ol className="space-y-3 text-xs">
              {HOW_TO_USE.map((s) => (
                <li key={s.num}>
                  <div className="font-bold text-gray-800">{s.num} {s.title}</div>
                  <div className="text-gray-600 mt-0.5 leading-relaxed">{s.body}</div>
                </li>
              ))}
            </ol>
          </section>

          <section className="bg-white border border-gray-200 rounded p-4">
            <h3 className="text-sm font-bold text-gray-800 flex items-center gap-1.5 mb-3">
              <span className="text-emerald-600">↗</span>
              V2配分ロジック
            </h3>
            <p className="text-xs text-gray-600 mb-2">V2では以下の10ステップで配分を計算します：</p>
            <ol className="space-y-1.5 text-xs">
              {ALLOC_STEPS.map((s) => (
                <li key={s.num} className="flex items-center gap-2">
                  <span className="w-5 h-5 rounded bg-gray-100 text-gray-600 text-[10px] flex items-center justify-center shrink-0">
                    {s.num}
                  </span>
                  <span className="text-gray-700">{s.title}</span>
                </li>
              ))}
            </ol>
          </section>

          <section className="bg-white border border-gray-200 rounded p-4">
            <h3 className="text-sm font-bold text-gray-800 flex items-center gap-1.5 mb-3">
              <FileSpreadsheet className="w-3.5 h-3.5 text-gray-500" />
              生成されるシート
            </h3>
            <table className="w-full text-xs">
              <tbody>
                {OUTPUT_SHEETS.map((s) => (
                  <tr key={s.name} className="border-b border-gray-100 last:border-0">
                    <td className="py-1.5 pr-2 font-bold text-gray-700 whitespace-nowrap">{s.name}</td>
                    <td className="py-1.5 text-gray-600">{s.desc}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </div>
      </div>
    </div>
  );
}
