#!/usr/bin/env python3
"""
同一品番併売分析スクリプト

使い方:
  python3 analyze_same_item.py <csv_path> <brand_item_code> [--compare <compare_item_code>] [--brand-key <brand_key>] [--out <output_json>]

引数:
  csv_path           ZOZO併売データCSVファイルパス
  brand_item_code    分析対象のブランド品番
  --compare          比較対象のブランド品番（省略時: 同カテゴリ×同性別で併売率上位の品番を自動選択）
  --brand-key        ブランドキー（省略時: CSVのショップ名から自動判定）
  --out              結果出力先JSONファイルパス（デフォルト: analysis_result.json）

出力:
  JSON形式で以下を含む:
  - target: 対象品番の分析結果
  - compare: 比較品番の分析結果
  - category: カテゴリ全体の統計
  - correlation: カラー展開数・メインカラー数と併売率の相関データ
"""
import argparse
import json
import os
import sys
import pandas as pd
import numpy as np
from itertools import combinations

# ── ブランド別カラー分類 ──

_PALETTES = None

def _load_palettes():
    global _PALETTES
    if _PALETTES is None:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         '..', 'references', 'brand_color_palettes.json')
        with open(p, encoding='utf-8') as f:
            _PALETTES = json.load(f)
    return _PALETTES

# フォールバック用汎用キーワード
_MAIN_FALLBACK = ['ブラック','ホワイト','オフホワイト','スミクロ','ライトグレー',
                  'グレー','チャコール','ダークグレー','アイボリー','グレージュ',
                  'アッシュグレー','オートミール','スノーホワイト']
_SEASON_FALLBACK = ['ネイビー','ブラウン','モカ','ベージュ','カーキ','オリーブ',
                    'キャメル','ダークブラウン','ライトベージュ','トープ',
                    'コーヒーブラウン','ミッドナイトブルー','ダークネイビー']


def classify_color(c, brand_key=None):
    """ブランド別カラーパレットに基づいてカラーを分類する。"""
    cn = c.strip()
    palettes = _load_palettes()
    palette = palettes.get(brand_key) if brand_key else None

    if palette:
        if any(kw in cn for kw in palette['main']):
            return 'メインカラー'
        elif any(kw in cn for kw in palette['season']):
            return 'シーズンカラー'
        else:
            return 'アクセントカラー'

    # フォールバック
    if any(kw in cn for kw in _MAIN_FALLBACK):
        return 'メインカラー'
    elif any(kw in cn for kw in _SEASON_FALLBACK):
        return 'シーズンカラー'
    return 'アクセントカラー'


def detect_brand_key(df, item_code):
    """CSVのショップ名等からブランドキーを推定する。"""
    palettes = _load_palettes()
    t = df[df['ブランド品番'] == item_code]
    if t.empty:
        return None

    # ショップ名列があればそれを使う
    shop_col = None
    for col_name in ['ショップ名', 'ブランド名', 'ショップ']:
        if col_name in t.columns:
            shop_col = col_name
            break

    if shop_col is None:
        return None

    shop_name = str(t[shop_col].iloc[0]).strip()

    # 完全一致 or 部分一致でブランドキーを特定
    candidates = []
    for key, pal in palettes.items():
        for bn in pal.get('brand_names', []):
            if bn in shop_name or shop_name in bn:
                candidates.append(key)

    if len(candidates) == 1:
        return candidates[0]
    elif len(candidates) > 1:
        # MONO-MART系の場合、テイスト情報では自動判別が難しいので最初の候補を返す
        # （--brand-key で明示指定を推奨）
        return candidates[0]

    return None


def analyze_item(df, item_code, brand_key=None):
    """1品番の同一品番併売を分析"""
    t = df[df['ブランド品番'] == item_code].copy()
    if t.empty:
        print(f"ERROR: ブランド品番 '{item_code}' がデータに存在しません", file=sys.stderr)
        sys.exit(1)

    info = {
        '商品名': t['商品名'].iloc[0],
        '子商品タイプ': t['子商品タイプ'].iloc[0],
        '性別': t['性別'].iloc[0],
        '親カテゴリ': t['親カテゴリ'].iloc[0],
    }

    # カラー展開
    colors = t['カラー'].unique().tolist()
    color_cats = {c: classify_color(c, brand_key) for c in colors}
    main_count = sum(1 for v in color_cats.values() if v == 'メインカラー')
    season_count = sum(1 for v in color_cats.values() if v == 'シーズンカラー')
    accent_count = sum(1 for v in color_cats.values() if v == 'アクセントカラー')

    # 注文ベースの集計
    order_grp = t.groupby('注文番号').agg(
        行数=('CS品番', 'size'),
        ユニークカラー数=('カラー', 'nunique'),
        ユニークサイズ数=('サイズ', 'nunique'),
        カラー一覧=('カラー', lambda x: list(x.unique()))
    ).reset_index()

    total_orders = len(order_grp)
    multi_orders = (order_grp['行数'] >= 2).sum()
    rate = multi_orders / total_orders * 100 if total_orders > 0 else 0

    color_diff = (order_grp['ユニークカラー数'] >= 2).sum()
    size_diff = ((order_grp['行数'] >= 2) & (order_grp['ユニークカラー数'] == 1)).sum()

    # 色ペア分析
    mc = order_grp[order_grp['ユニークカラー数'] >= 2]
    pair_counts = {}
    cat_pair_counts = {}
    for _, row in mc.iterrows():
        for p in combinations(sorted(row['カラー一覧']), 2):
            key = f'{p[0]} × {p[1]}'
            pair_counts[key] = pair_counts.get(key, 0) + 1
            cat_key = tuple(sorted([classify_color(p[0], brand_key),
                                     classify_color(p[1], brand_key)]))
            cat_pair_counts[cat_key] = cat_pair_counts.get(cat_key, 0) + 1

    total_pairs = sum(cat_pair_counts.values())
    cat_pair_pcts = {}
    if total_pairs > 0:
        for k, v in cat_pair_counts.items():
            cat_pair_pcts[f'{k[0]}×{k[1]}'] = round(v / total_pairs * 100, 1)

    top_pairs = sorted(pair_counts.items(), key=lambda x: -x[1])[:10]

    return {
        'ブランド品番': item_code,
        '商品名': info['商品名'],
        '子商品タイプ': info['子商品タイプ'],
        '性別': info['性別'],
        '親カテゴリ': info['親カテゴリ'],
        'ブランドキー': brand_key,
        'カラー展開数': len(colors),
        'メインカラー数': main_count,
        'シーズンカラー数': season_count,
        'アクセントカラー数': accent_count,
        'カラー一覧': {c: color_cats[c] for c in colors},
        '注文件数': int(total_orders),
        '同一品番併売件数': int(multi_orders),
        '同一品番併売率': round(rate, 1),
        '色違い併売件数': int(color_diff),
        'サイズ違い併売件数': int(size_diff),
        'カラー分類ペア構成比': cat_pair_pcts,
        '色ペアTOP10': [{'ペア': k, '件数': v} for k, v in top_pairs],
    }


def compute_category_stats(df, child_type, gender, brand_key=None, min_orders=100):
    """同一カテゴリ×性別の品番別併売率を集計"""
    cat_df = df[(df['子商品タイプ'] == child_type) & (df['性別'] == gender)].copy()
    cat_df['カラー分類'] = cat_df['カラー'].apply(lambda c: classify_color(c, brand_key))

    items = []
    for item, grp in cat_df.groupby('ブランド品番'):
        orders = grp.groupby('注文番号').agg(行数=('CS品番', 'size'))
        total = len(orders)
        multi = (orders['行数'] >= 2).sum()
        tc = grp['カラー'].nunique()
        mc = grp[grp['カラー分類'] == 'メインカラー']['カラー'].nunique()
        sc = grp[grp['カラー分類'] == 'シーズンカラー']['カラー'].nunique()
        ac = grp[grp['カラー分類'] == 'アクセントカラー']['カラー'].nunique()
        items.append({
            'ブランド品番': item,
            '注文件数': total,
            '同一品番併売率': round(multi / total * 100, 1) if total > 0 else 0,
            'カラー展開数': tc,
            'メインカラー数': mc,
            'シーズンカラー数': sc,
            'アクセントカラー数': ac,
        })

    stats = pd.DataFrame(items)
    stats_filtered = stats[stats['注文件数'] >= min_orders].copy()
    stats_filtered = stats_filtered.sort_values('同一品番併売率', ascending=False).reset_index(drop=True)

    # 相関データ
    corr_color = float(stats_filtered['カラー展開数'].corr(stats_filtered['同一品番併売率']))
    main_group = stats_filtered.groupby('メインカラー数')['同一品番併売率'].mean().to_dict()
    main_group = {int(k): round(v, 1) for k, v in main_group.items()}

    return {
        '子商品タイプ': child_type,
        '性別': gender,
        '対象品番数': int(len(stats_filtered)),
        '平均併売率': round(float(stats_filtered['同一品番併売率'].mean()), 1),
        'ランキング': stats_filtered[['ブランド品番', '注文件数', '同一品番併売率', 'カラー展開数']].to_dict('records'),
        '相関_カラー展開数': round(corr_color, 2),
        'メインカラー数別平均併売率': main_group,
    }


def auto_select_compare(category_stats, target_code):
    """同一カテゴリ×性別で対象品番より併売率が高い上位品番を自動選択"""
    ranking = category_stats['ランキング']
    for item in ranking:
        if item['ブランド品番'] != target_code:
            return item['ブランド品番']
    return None


def main():
    parser = argparse.ArgumentParser(description='同一品番併売分析')
    parser.add_argument('csv_path', help='ZOZO併売データCSVファイルパス')
    parser.add_argument('brand_item_code', help='分析対象のブランド品番')
    parser.add_argument('--compare', default=None, help='比較対象のブランド品番')
    parser.add_argument('--brand-key', default=None, help='ブランドキー（例: MONO-MART_CASUAL_M1）')
    parser.add_argument('--out', default='analysis_result.json', help='出力JSONパス')
    args = parser.parse_args()

    print(f"データ読み込み中: {args.csv_path}")
    df = pd.read_csv(args.csv_path, encoding='shift_jis')
    print(f"  行数: {len(df):,}, 品番数: {df['ブランド品番'].nunique():,}")

    # ブランドキーの決定
    brand_key = args.brand_key
    if brand_key is None:
        brand_key = detect_brand_key(df, args.brand_item_code)
        if brand_key:
            print(f"  ブランドキーを自動検出: {brand_key}")
        else:
            print(f"  ブランドキー未検出: フォールバック分類を使用")

    # 対象品番の分析
    print(f"\n対象品番 '{args.brand_item_code}' を分析中...")
    target = analyze_item(df, args.brand_item_code, brand_key)
    print(f"  注文件数: {target['注文件数']:,}, 併売率: {target['同一品番併売率']}%")

    # カテゴリ統計
    print(f"\nカテゴリ統計を集計中: {target['子商品タイプ']} × {target['性別']}")
    cat_stats = compute_category_stats(df, target['子商品タイプ'], target['性別'], brand_key)
    print(f"  対象品番数: {cat_stats['対象品番数']}, 平均併売率: {cat_stats['平均併売率']}%")

    # カテゴリ内順位
    ranking = cat_stats['ランキング']
    target_rank = next((i + 1 for i, r in enumerate(ranking) if r['ブランド品番'] == args.brand_item_code), None)
    target['カテゴリ内順位'] = f"{target_rank}位/{cat_stats['対象品番数']}品番" if target_rank else "N/A"

    # 比較品番
    compare_code = args.compare
    if compare_code is None:
        compare_code = auto_select_compare(cat_stats, args.brand_item_code)
        print(f"\n比較品番を自動選択: {compare_code}")

    compare = None
    if compare_code:
        print(f"\n比較品番 '{compare_code}' を分析中...")
        compare = analyze_item(df, compare_code, brand_key)
        compare_rank = next((i + 1 for i, r in enumerate(ranking) if r['ブランド品番'] == compare_code), None)
        compare['カテゴリ内順位'] = f"{compare_rank}位/{cat_stats['対象品番数']}品番" if compare_rank else "N/A"
        print(f"  注文件数: {compare['注文件数']:,}, 併売率: {compare['同一品番併売率']}%")

    # 結果出力
    result = {
        'target': target,
        'compare': compare,
        'category': cat_stats,
    }

    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n結果を出力しました: {args.out}")


if __name__ == '__main__':
    main()
