#!/usr/bin/env python3
"""
MD計画 Step3: クロス分析 & MD提案JSON生成
Step1（外部環境）とStep2（内部環境）の結果を統合し、
最終的なMD計画データJSONを生成する。
"""

import json
import os

# ===== 入力ファイル =====
STEP1_FILE = '/home/ubuntu/md_plan_step1_result.json'
STEP2_FILE = '/home/ubuntu/md_plan_step2_result.json'
OUTPUT_FILE = '/home/ubuntu/md_plan_final.json'

# 主要分析対象ブランド（買い回りデータあり）
KAIMAWARI_BRANDS = ['MONO-MART', 'EMMA CLOTHES', 'CLEL', 'ADRER', 'WYM LIDNM']

# 内部データあり（注文データあり）のブランド
INTERNAL_BRANDS = [
    'MONO-MART', 'CLEL', 'WYM LIDNM', 'THE CRAFT CREW PRODUCTS',
    'forksy.', 'Alfred Alex', 'GRANCY', 'cussil', "MONO-MART LADY'S",
    'Parts Lab.', 'LUENNA', 'RUUBON', 'Aunely', 'Elishe', 'EMMA CLOTHES', 'Heart Tattoo'
]

# 主要カテゴリ（正規化済み）
MAIN_CATEGORIES = [
    'トップス', 'パンツ', 'ジャケット/アウター', 'シューズ', 'バッグ',
    'アクセサリー', 'ワンピース/ドレス', 'スカート', 'スーツ/ネクタイ',
    'レッグウェア', '帽子', '水着/着物・浴衣', 'ルームウェア',
    '財布/小物', 'ファッション雑貨', '時計', 'アンダーウェア/インナー',
]

# 価格帯の順序
PRICE_BAND_ORDER = [
    '〜1,999円', '2,000〜3,999円', '4,000〜5,999円',
    '6,000〜7,999円', '8,000〜11,999円', '12,000円〜'
]

def load_data():
    with open(STEP1_FILE, 'r', encoding='utf-8') as f:
        step1 = json.load(f)
    with open(STEP2_FILE, 'r', encoding='utf-8') as f:
        step2 = json.load(f)
    return step1, step2

def build_internal_lookup(step2):
    """内部データをブランド×カテゴリでルックアップ可能にする"""
    cat_lookup = {}
    for item in step2['categories']:
        key = (item['ブランド'], item['カテゴリ'])
        cat_lookup[key] = item
    
    cat_price_lookup = {}
    for item in step2['category_price']:
        key = (item['ブランド'], item['カテゴリ'], item['価格帯'])
        cat_price_lookup[key] = item
    
    brand_lookup = {}
    for item in step2['brands']:
        brand_lookup[item['ブランド']] = item
    
    return cat_lookup, cat_price_lookup, brand_lookup

def generate_md_proposals(step1, step2, cat_lookup, cat_price_lookup, brand_lookup):
    """クロス分析によるMD提案を生成"""
    proposals = []
    
    for brand in KAIMAWARI_BRANDS:
        # 外部データ: カテゴリ別買い回り
        ext_cats = step1.get('category_kaimawari', {}).get(brand, [])
        ext_cat_price = step1.get('category_price_matrix', {}).get(brand, [])
        
        # 外部カテゴリ×価格帯をルックアップ化
        ext_cp_lookup = {}
        for item in ext_cat_price:
            key = (item['カテゴリ'], item['価格帯'])
            ext_cp_lookup[key] = item
        
        brand_internal = brand_lookup.get(brand, None)
        
        for ext_cat in ext_cats:
            cat_name = ext_cat['カテゴリ']
            
            # 主要カテゴリのみ対象
            if cat_name not in MAIN_CATEGORIES:
                continue
            
            # 内部データとのクロス
            int_data = cat_lookup.get((brand, cat_name), None)
            
            # 買い回り需要スコア（件数ベース、正規化）
            demand_score = min(ext_cat['件数'] / 1000, 100)  # 1000件=1pt, max 100
            
            # 内部パフォーマンス
            has_internal = int_data is not None and int_data['売上金額'] > 0
            
            if has_internal:
                # 既存カテゴリ: 強化 or 維持 or 縮小の判断
                gross_margin = int_data.get('粗利率')
                proper_ratio = int_data.get('プロパー比率', 0)
                type_count = int_data.get('型数', 0)
                sales = int_data.get('売上金額', 0)
                avg_price = int_data.get('平均単価', 0)
                
                # MDスコア算出
                # 外部需要（40%）+ 粗利率（30%）+ プロパー比率（20%）+ 型数効率（10%）
                margin_score = (gross_margin / 100 * 100) if gross_margin and gross_margin > 0 else 30
                proper_score = proper_ratio
                efficiency = min(sales / max(type_count, 1) / 10000, 100)  # 型あたり売上効率
                
                md_score = round(
                    demand_score * 0.4 +
                    margin_score * 0.3 +
                    proper_score * 0.2 +
                    efficiency * 0.1,
                    1
                )
                
                # 価格帯別の詳細
                price_details = []
                for pb in PRICE_BAND_ORDER:
                    ext_pb = ext_cp_lookup.get((cat_name, pb), None)
                    int_pb = cat_price_lookup.get((brand, cat_name, pb), None)
                    
                    if ext_pb or int_pb:
                        price_details.append({
                            '価格帯': pb,
                            '買い回り件数': ext_pb['件数'] if ext_pb else 0,
                            '買い回り金額': ext_pb['金額'] if ext_pb else 0,
                            '自社売上': int_pb['売上金額'] if int_pb else 0,
                            '自社点数': int_pb['売上点数'] if int_pb else 0,
                            '自社型数': int_pb['型数'] if int_pb else 0,
                            '自社P比率': int_pb['プロパー比率'] if int_pb else None,
                            'ギャップ': '需要あり・未展開' if (ext_pb and ext_pb['件数'] > 50 and (not int_pb or int_pb['売上金額'] == 0)) else (
                                '強化推奨' if (ext_pb and ext_pb['件数'] > 100 and int_pb and int_pb['型数'] < 5) else '展開中'
                            ),
                        })
                
                action = '強化推奨' if md_score >= 50 else ('維持' if md_score >= 30 else '見直し')
                
                proposals.append({
                    'ブランド': brand,
                    'カテゴリ': cat_name,
                    'タイプ': '既存強化',
                    'MDスコア': md_score,
                    'アクション': action,
                    '買い回り件数': ext_cat['件数'],
                    '買い回り金額': ext_cat['金額'],
                    '他社平均単価': ext_cat['平均単価'],
                    '自社売上': sales,
                    '自社型数': type_count,
                    '自社FKU': int_data.get('FKU', 0),
                    '自社平均単価': avg_price,
                    '粗利率': gross_margin,
                    'プロパー比率': proper_ratio,
                    '価格帯詳細': price_details,
                })
            else:
                # 未展開カテゴリ: 新規参入の判断
                # 買い回り需要が高いカテゴリは参入候補
                md_score = round(demand_score * 0.7 + 30 * 0.3, 1)  # 需要重視
                
                # 価格帯別の詳細
                price_details = []
                for pb in PRICE_BAND_ORDER:
                    ext_pb = ext_cp_lookup.get((cat_name, pb), None)
                    if ext_pb and ext_pb['件数'] > 10:
                        price_details.append({
                            '価格帯': pb,
                            '買い回り件数': ext_pb['件数'],
                            '買い回り金額': ext_pb['金額'],
                            '自社売上': 0,
                            '自社点数': 0,
                            '自社型数': 0,
                            '自社P比率': None,
                            'ギャップ': '需要あり・未展開',
                        })
                
                if ext_cat['件数'] >= 100:
                    proposals.append({
                        'ブランド': brand,
                        'カテゴリ': cat_name,
                        'タイプ': '新規参入',
                        'MDスコア': md_score,
                        'アクション': '参入検討' if md_score >= 30 else '要調査',
                        '買い回り件数': ext_cat['件数'],
                        '買い回り金額': ext_cat['金額'],
                        '他社平均単価': ext_cat['平均単価'],
                        '自社売上': 0,
                        '自社型数': 0,
                        '自社FKU': 0,
                        '自社平均単価': 0,
                        '粗利率': None,
                        'プロパー比率': None,
                        '価格帯詳細': price_details,
                    })
    
    # MDスコア降順でソート
    proposals.sort(key=lambda x: x['MDスコア'], reverse=True)
    return proposals

def generate_executive_summary(proposals, step1, brand_lookup):
    """エグゼクティブサマリーを生成"""
    summary = {}
    
    for brand in KAIMAWARI_BRANDS:
        brand_proposals = [p for p in proposals if p['ブランド'] == brand]
        
        # 強化推奨（既存カテゴリで高スコア）
        strengthen = [p for p in brand_proposals if p['タイプ'] == '既存強化' and p['MDスコア'] >= 50]
        strengthen.sort(key=lambda x: x['MDスコア'], reverse=True)
        
        # 新規参入推奨
        new_entry = [p for p in brand_proposals if p['タイプ'] == '新規参入']
        new_entry.sort(key=lambda x: x['MDスコア'], reverse=True)
        
        # 見直し対象
        review = [p for p in brand_proposals if p['タイプ'] == '既存強化' and p['MDスコア'] < 30]
        
        # ブランドサマリー
        brand_info = brand_lookup.get(brand, {})
        
        summary[brand] = {
            'ブランドサマリー': {
                '売上金額': brand_info.get('売上金額', 0),
                '型数': brand_info.get('型数', 0),
                '粗利率': brand_info.get('粗利率'),
                'プロパー比率': brand_info.get('プロパー比率', 0),
            },
            '強化推奨': [{
                'カテゴリ': p['カテゴリ'],
                'スコア': p['MDスコア'],
                '買い回り件数': p['買い回り件数'],
                '自社売上': p['自社売上'],
                '自社型数': p['自社型数'],
                '粗利率': p['粗利率'],
                '主要価格帯': max(p['価格帯詳細'], key=lambda x: x['買い回り件数'])['価格帯'] if p['価格帯詳細'] else '不明',
                '他社平均単価': p['他社平均単価'],
            } for p in strengthen[:5]],
            '新規参入推奨': [{
                'カテゴリ': p['カテゴリ'],
                'スコア': p['MDスコア'],
                '買い回り件数': p['買い回り件数'],
                '主要価格帯': max(p['価格帯詳細'], key=lambda x: x['買い回り件数'])['価格帯'] if p['価格帯詳細'] else '不明',
                '他社平均単価': p['他社平均単価'],
            } for p in new_entry[:5]],
            '見直し対象': [{
                'カテゴリ': p['カテゴリ'],
                'スコア': p['MDスコア'],
                '自社売上': p['自社売上'],
                '粗利率': p['粗利率'],
            } for p in review[:3]],
        }
    
    return summary

def main():
    print('=== MD計画 Step3: クロス分析 & MD提案生成 ===')
    
    # 1. データ読み込み
    print('\n[1] Loading step1 & step2 results...')
    step1, step2 = load_data()
    
    # 2. ルックアップ構築
    print('[2] Building lookups...')
    cat_lookup, cat_price_lookup, brand_lookup = build_internal_lookup(step2)
    
    # 3. MD提案生成
    print('[3] Generating MD proposals...')
    proposals = generate_md_proposals(step1, step2, cat_lookup, cat_price_lookup, brand_lookup)
    print(f'  Generated {len(proposals)} proposals')
    
    # 4. エグゼクティブサマリー
    print('[4] Generating executive summary...')
    summary = generate_executive_summary(proposals, step1, brand_lookup)
    
    # 5. 最終JSON構築
    final = {
        'meta': {
            'analysis_date': '2026-04-03',
            'data_period': '2026年1月〜3月',
            'brands': KAIMAWARI_BRANDS,
            'internal_brands': [b for b in INTERNAL_BRANDS if brand_lookup.get(b)],
        },
        'executive_summary': summary,
        'affinity': step1.get('affinity', {}),
        'category_kaimawari': step1.get('category_kaimawari', {}),
        'category_price_matrix': step1.get('category_price_matrix', {}),
        'internal_performance': {
            'categories': step2.get('categories', []),
            'brands': step2.get('brands', []),
            'category_price': step2.get('category_price', []),
        },
        'md_proposals': proposals,
    }
    
    # 6. 保存
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(final, f, ensure_ascii=False, indent=2)
    
    print(f'\n=== Step3 完了: {OUTPUT_FILE} ===')
    print(f'File size: {os.path.getsize(OUTPUT_FILE) / 1024:.1f} KB')
    
    # サマリー表示
    for brand in KAIMAWARI_BRANDS:
        s = summary.get(brand, {})
        bs = s.get('ブランドサマリー', {})
        strengthen = s.get('強化推奨', [])
        new_entry = s.get('新規参入推奨', [])
        review = s.get('見直し対象', [])
        
        print(f'\n--- {brand} ---')
        if bs.get('売上金額'):
            print(f'  売上: ¥{bs["売上金額"]:,.0f} / 型数: {bs["型数"]} / 粗利率: {bs["粗利率"]}%')
        
        if strengthen:
            print(f'  強化推奨 ({len(strengthen)}):')
            for item in strengthen[:3]:
                print(f'    {item["カテゴリ"]} (スコア{item["スコア"]}, 買い回り{item["買い回り件数"]:,}件, 型数{item["自社型数"]})')
        
        if new_entry:
            print(f'  新規参入推奨 ({len(new_entry)}):')
            for item in new_entry[:3]:
                print(f'    {item["カテゴリ"]} (スコア{item["スコア"]}, 買い回り{item["買い回り件数"]:,}件, 単価¥{item["他社平均単価"]:,})')
        
        if review:
            print(f'  見直し対象 ({len(review)}):')
            for item in review[:3]:
                print(f'    {item["カテゴリ"]} (スコア{item["スコア"]}, 粗利率{item["粗利率"]}%)')

if __name__ == '__main__':
    main()
