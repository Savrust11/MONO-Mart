#!/usr/bin/env python3
"""
MD計画 Step2: 内部環境分析
注文データ（2026年1-3月）× 原価データ

出力:
- ブランド別 × カテゴリ別の売上・粗利率・型数・FKU
- ブランド別 × カテゴリ × 価格帯の詳細
"""

import pandas as pd
import numpy as np
import json
import os
import gc
from collections import defaultdict
import csv

# ===== 設定 =====
ORDER_FILES = [
    '/home/ubuntu/order_data/order_202601a.csv',
    '/home/ubuntu/order_data/order_202601b.csv',
    '/home/ubuntu/order_data/order_202602a.csv',
    '/home/ubuntu/order_data/order_202602b.csv',
    '/home/ubuntu/order_data/order_202603.csv',
]

COST_FILE = '/home/ubuntu/sales_data/cost_data.csv'

# 注文データの正しい列名（29フィールド: ヘッダー28列 + 先頭の親ショップ名）
CORRECT_COLS = [
    '親ショップ名',   # 0: always MONO-MART
    'ショップ名',      # 1: brand shop name
    'ブランド名',      # 2: brand name within shop
    '親カテゴリ',      # 3: parent category (トップス, パンツ, etc.)
    '子カテゴリ',      # 4: sub category (ニット/セーター, etc.)
    '性別',            # 5: MEN/WOMEN
    'ブランド品番',    # 6: brand item number
    'CS品番',          # 7: CS code
    '商品名',          # 8: product name
    'カラー',          # 9: color
    'サイズ',          # 10: size
    '販売開始日',      # 11: sales start date
    '販売価格',        # 12: sales price (tax excluded)
    '販売タイプ',      # 13: 通常
    '価格タイプ',      # 14: プロパー/セール
    'プロパー価格',    # 15: proper price (tax excluded)
    '注文番号',        # 16: order number
    '注文数',          # 17: order quantity
    '合計金額',        # 18: total amount (tax excluded)
    '注文日',          # 19: order date
    '発送日',          # 20: shipping date
    '注文時端末',      # 21: device
    'キャンセル',      # 22: cancel flag (empty = valid)
    '会員ID',          # 23: member ID
    '年齢',            # 24: age
    '会員性別',        # 25: member gender
    '県名',            # 26: prefecture
    'モール',          # 27: mall
    '_trailing_',      # 28: empty trailing field
]

# 自社ブランド一覧
OWN_BRANDS = {
    'MONO-MART', 'EMMA CLOTHES', 'WYM LIDNM', 'THE CRAFT CREW',
    'THE CRAFT CREW PRODUCTS',
    'Alfred Alex', 'Anchor Smith', 'ADRER', 'CLEL', 'LOOSE', 'cussil',
    'GRANCY', 'SERACE', 'LUENNA', 'RUUBON', 'forksy.', "MONO-MART LADY'S",
    'BONLECILL', 'Heart Tattoo', 'ELUNIS', 'Elishe', 'Parts Lab.', 'Aunely',
}

# 価格帯定義
PRICE_BANDS = [
    (0, 1999, '〜1,999円'),
    (2000, 3999, '2,000〜3,999円'),
    (4000, 5999, '4,000〜5,999円'),
    (6000, 7999, '6,000〜7,999円'),
    (8000, 11999, '8,000〜11,999円'),
    (12000, float('inf'), '12,000円〜'),
]

def get_price_band(price):
    try:
        p = float(price)
    except (ValueError, TypeError):
        return '不明'
    for low, high, label in PRICE_BANDS:
        if low <= p <= high:
            return label
    return '不明'

def load_cost_data():
    """原価データを読み込み"""
    cost_dict = {}
    with open(COST_FILE, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        next(reader)  # header
        for row in reader:
            if len(row) >= 2:
                item_code = row[0].strip()
                cost_str = row[1].strip().replace('¥', '').replace(',', '')
                try:
                    cost = float(cost_str)
                    cost_dict[item_code] = cost
                except ValueError:
                    pass
    print(f'  Loaded {len(cost_dict)} cost entries')
    return cost_dict

def process_order_data(cost_dict):
    """注文データを処理して内部パフォーマンスを算出"""
    
    # ブランド別 × カテゴリ別集計
    brand_cat = defaultdict(lambda: {
        '売上金額': 0, '売上点数': 0, 'プロパー売上': 0, 'プロパー点数': 0,
        'セール売上': 0, 'セール点数': 0, '原価合計': 0, '原価件数': 0,
        '品番set': set(), 'カラーset': set(), 'SKUset': set(),
    })
    
    # ブランド別 × カテゴリ × 価格帯集計
    brand_cat_price = defaultdict(lambda: {
        '売上金額': 0, '売上点数': 0, 'プロパー売上': 0, 'プロパー点数': 0,
        'セール売上': 0, 'セール点数': 0, '品番set': set(),
    })
    
    # ブランド別集計
    brand_total = defaultdict(lambda: {
        '売上金額': 0, '売上点数': 0, 'プロパー売上': 0, 'プロパー点数': 0,
        'セール売上': 0, 'セール点数': 0, '原価合計': 0, '原価件数': 0,
        '品番set': set(),
    })
    
    total_rows = 0
    valid_rows = 0
    
    for fpath in ORDER_FILES:
        print(f'  Processing {os.path.basename(fpath)}...')
        
        with open(fpath, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader)  # skip original header
            
            for row in reader:
                total_rows += 1
                
                if len(row) < 28:
                    continue
                
                # Apply correct column mapping (data has 29 fields, first is extra)
                cancel = row[22].strip() if len(row) > 22 else ''
                
                # Skip cancelled orders (empty = valid, non-empty = cancelled)
                if cancel:
                    continue
                
                brand_name = row[2].strip() if row[2] else ''
                shop_name = row[1].strip() if row[1] else ''
                category = row[3].strip() if row[3] else ''
                sub_category = row[4].strip() if row[4] else ''
                gender = row[5].strip() if row[5] else ''
                item_code = row[6].strip() if row[6] else ''
                color = row[9].strip() if row[9] else ''
                size = row[10].strip() if row[10] else ''
                
                try:
                    sell_price = float(row[12]) if row[12] else 0
                except (ValueError, TypeError):
                    sell_price = 0
                
                price_type = row[14].strip() if len(row) > 14 and row[14] else ''
                
                try:
                    proper_price = float(row[15]) if len(row) > 15 and row[15] else 0
                except (ValueError, TypeError):
                    proper_price = 0
                
                try:
                    qty = int(row[17]) if len(row) > 17 and row[17] else 0
                except (ValueError, TypeError):
                    qty = 0
                
                try:
                    amount = float(row[18]) if len(row) > 18 and row[18] else 0
                except (ValueError, TypeError):
                    amount = 0
                
                if not brand_name or not category or amount <= 0:
                    continue
                
                # Only process own brands
                if brand_name not in OWN_BRANDS and shop_name not in OWN_BRANDS:
                    continue
                
                valid_rows += 1
                
                # Determine effective brand (use brand_name if it's an own brand, else shop_name)
                effective_brand = brand_name if brand_name in OWN_BRANDS else shop_name
                
                price_band = get_price_band(sell_price)
                is_proper = 'プロパー' in price_type
                
                # Get cost
                cost = cost_dict.get(item_code, None)
                
                # Brand × Category aggregation
                key_bc = (effective_brand, category)
                brand_cat[key_bc]['売上金額'] += amount
                brand_cat[key_bc]['売上点数'] += qty
                brand_cat[key_bc]['品番set'].add(item_code)
                brand_cat[key_bc]['カラーset'].add((item_code, color))
                brand_cat[key_bc]['SKUset'].add((item_code, color, size))
                
                if is_proper:
                    brand_cat[key_bc]['プロパー売上'] += amount
                    brand_cat[key_bc]['プロパー点数'] += qty
                else:
                    brand_cat[key_bc]['セール売上'] += amount
                    brand_cat[key_bc]['セール点数'] += qty
                
                if cost is not None:
                    brand_cat[key_bc]['原価合計'] += cost * qty
                    brand_cat[key_bc]['原価件数'] += qty
                
                # Brand × Category × Price band
                key_bcp = (effective_brand, category, price_band)
                brand_cat_price[key_bcp]['売上金額'] += amount
                brand_cat_price[key_bcp]['売上点数'] += qty
                brand_cat_price[key_bcp]['品番set'].add(item_code)
                if is_proper:
                    brand_cat_price[key_bcp]['プロパー売上'] += amount
                    brand_cat_price[key_bcp]['プロパー点数'] += qty
                else:
                    brand_cat_price[key_bcp]['セール売上'] += amount
                    brand_cat_price[key_bcp]['セール点数'] += qty
                
                # Brand total
                brand_total[effective_brand]['売上金額'] += amount
                brand_total[effective_brand]['売上点数'] += qty
                brand_total[effective_brand]['品番set'].add(item_code)
                if is_proper:
                    brand_total[effective_brand]['プロパー売上'] += amount
                    brand_total[effective_brand]['プロパー点数'] += qty
                else:
                    brand_total[effective_brand]['セール売上'] += amount
                    brand_total[effective_brand]['セール点数'] += qty
                if cost is not None:
                    brand_total[effective_brand]['原価合計'] += cost * qty
                    brand_total[effective_brand]['原価件数'] += qty
        
        gc.collect()
    
    print(f'  Total rows: {total_rows:,}, Valid own-brand rows: {valid_rows:,}')
    
    return brand_cat, brand_cat_price, brand_total

def main():
    print('=== MD計画 Step2: 内部環境分析 ===')
    
    # 1. 原価データ読み込み
    print('\n[1] Loading cost data...')
    cost_dict = load_cost_data()
    
    # 2. 注文データ処理
    print('\n[2] Processing order data...')
    brand_cat, brand_cat_price, brand_total = process_order_data(cost_dict)
    
    # 3. 結果を構造化
    result = {
        'categories': [],    # ブランド×カテゴリ別パフォーマンス
        'brands': [],        # ブランド別サマリー
        'category_price': [], # ブランド×カテゴリ×価格帯
    }
    
    # ブランド×カテゴリ
    for (brand, cat), data in brand_cat.items():
        if data['売上金額'] < 1000:
            continue
        
        gross_margin = None
        if data['原価件数'] > 0 and data['売上金額'] > 0:
            avg_cost = data['原価合計'] / data['原価件数']
            avg_price = data['売上金額'] / data['売上点数']
            gross_margin = round((1 - avg_cost / avg_price) * 100, 1)
        
        proper_ratio = 0
        if data['売上点数'] > 0:
            proper_ratio = round(data['プロパー点数'] / data['売上点数'] * 100, 1)
        
        result['categories'].append({
            'ブランド': brand,
            'カテゴリ': cat,
            '売上金額': round(data['売上金額']),
            '売上点数': data['売上点数'],
            '型数': len(data['品番set']),
            'FKU': len(data['カラーset']),
            'SKU': len(data['SKUset']),
            '平均単価': round(data['売上金額'] / data['売上点数']) if data['売上点数'] > 0 else 0,
            '粗利率': gross_margin,
            'プロパー比率': proper_ratio,
            'プロパー売上': round(data['プロパー売上']),
            'セール売上': round(data['セール売上']),
        })
    
    # ブランド別サマリー
    for brand, data in brand_total.items():
        gross_margin = None
        if data['原価件数'] > 0 and data['売上金額'] > 0:
            avg_cost = data['原価合計'] / data['原価件数']
            avg_price = data['売上金額'] / data['売上点数']
            gross_margin = round((1 - avg_cost / avg_price) * 100, 1)
        
        proper_ratio = 0
        if data['売上点数'] > 0:
            proper_ratio = round(data['プロパー点数'] / data['売上点数'] * 100, 1)
        
        result['brands'].append({
            'ブランド': brand,
            '売上金額': round(data['売上金額']),
            '売上点数': data['売上点数'],
            '型数': len(data['品番set']),
            '平均単価': round(data['売上金額'] / data['売上点数']) if data['売上点数'] > 0 else 0,
            '粗利率': gross_margin,
            'プロパー比率': proper_ratio,
        })
    
    # ブランド×カテゴリ×価格帯
    for (brand, cat, pb), data in brand_cat_price.items():
        if data['売上金額'] < 500:
            continue
        
        proper_ratio = 0
        if data['売上点数'] > 0:
            proper_ratio = round(data['プロパー点数'] / data['売上点数'] * 100, 1)
        
        result['category_price'].append({
            'ブランド': brand,
            'カテゴリ': cat,
            '価格帯': pb,
            '売上金額': round(data['売上金額']),
            '売上点数': data['売上点数'],
            '型数': len(data['品番set']),
            '平均単価': round(data['売上金額'] / data['売上点数']) if data['売上点数'] > 0 else 0,
            'プロパー比率': proper_ratio,
        })
    
    # ソート
    result['categories'].sort(key=lambda x: x['売上金額'], reverse=True)
    result['brands'].sort(key=lambda x: x['売上金額'], reverse=True)
    result['category_price'].sort(key=lambda x: x['売上金額'], reverse=True)
    
    # 4. 保存
    output_path = '/home/ubuntu/md_plan_step2_result.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f'\n=== Step2 完了: {output_path} ===')
    
    # サマリー
    print(f'\nCategories: {len(result["categories"])} entries')
    print(f'Brands: {len(result["brands"])} entries')
    print(f'Category×Price: {len(result["category_price"])} entries')
    
    print('\n--- Brand Summary ---')
    for b in result['brands'][:10]:
        print(f"  {b['ブランド']}: ¥{b['売上金額']:,.0f} ({b['型数']}型, 粗利率{b['粗利率']}%, P比率{b['プロパー比率']}%)")
    
    print('\n--- Top Categories (all brands) ---')
    for c in result['categories'][:10]:
        print(f"  {c['ブランド']}/{c['カテゴリ']}: ¥{c['売上金額']:,.0f} ({c['型数']}型, 粗利率{c['粗利率']}%)")

if __name__ == '__main__':
    main()
