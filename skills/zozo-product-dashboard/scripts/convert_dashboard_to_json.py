"""
ダッシュボード商品別実績.xlsx → CDN用JSON変換スクリプト

出力構造:
{
  "items": {
    "<brandItemCode>": {
      "productName": "...",
      "brand": "...",
      "subBrand": "...",
      "shopName": "...",
      "parentCategory": "...",
      "childCategory": "...",
      "gender": "MEN|WOMEN|KIDS",
      "productCode": "...",
      "daily": {
        "2026-03-01": {
          "orders": 138, "revenue": 360800, "favorites": 300,
          "cartAdds": 277, "stock": 9723, "stockWithReserve": 9723,
          "uu": 3858, "pv": 6989, "buyers": 126,
          "male": 87, "female": 34, "newUsers": 26, "existing": 77, "reactivated": 23,
          "avgAge": 29.2, "avgPrice": 2614.49,
          "cvrUU": 0.0358, "cvrPV": 0.0197, "favRate": 0.0778
        }, ...
      }
    }
  },
  "categoryStats": {
    "<childCategory>_<gender>": {
      "childCategory": "...",
      "gender": "...",
      "itemCount": 123,
      "avgFavRate": 0.05,
      "avgCvrUU": 0.03,
      "avgUU": 500,
      "avgOrders": 50,
      "topFavRate": [...],
      "topCvrUU": [...]
    }
  },
  "meta": {
    "dateRange": ["2026-03-01", "2026-03-31"],
    "dates": [...],
    "totalItems": 10483,
    "brands": [...],
    "shops": [...]
  }
}
"""

import json
import openpyxl
from collections import defaultdict

print("Loading Excel file...")
wb = openpyxl.load_workbook('/home/ubuntu/dashboard_product_data.xlsx', read_only=True, data_only=True)
ws = wb['商品別実績 (2)']

items = {}
dates_set = set()
brands_set = set()
shops_set = set()

def safe_float(v, default=0.0):
    if v is None or v == '' or str(v) == '#DIV/0!':
        return default
    try:
        return round(float(v), 6)
    except:
        return default

def safe_int(v, default=0):
    if v is None or v == '':
        return default
    try:
        return int(float(v))
    except:
        return default

print("Processing rows...")
count = 0
for row in ws.iter_rows(min_row=2, values_only=True):
    count += 1
    if count % 50000 == 0:
        print(f"  {count:,} rows processed...")
    
    date_val = str(row[0])[:10] if row[0] else None
    if not date_val:
        continue
    
    brand_item_code = str(row[8]) if row[8] else None
    if not brand_item_code:
        continue
    
    dates_set.add(date_val)
    
    shop_name = str(row[2]) if row[2] else ''
    brand = str(row[3]) if row[3] else ''
    sub_brand = str(row[4]) if row[4] else ''
    parent_cat = str(row[5]) if row[5] else ''
    child_cat = str(row[6]) if row[6] else ''
    gender = str(row[7]) if row[7] else ''
    product_code = str(row[9]) if row[9] else ''
    product_name = str(row[10]) if row[10] else ''
    
    brands_set.add(brand)
    shops_set.add(shop_name)
    
    if brand_item_code not in items:
        items[brand_item_code] = {
            'productName': product_name[:60],
            'brand': brand,
            'subBrand': sub_brand,
            'shopName': shop_name,
            'parentCategory': parent_cat,
            'childCategory': child_cat,
            'gender': gender,
            'productCode': product_code,
            'daily': {}
        }
    
    items[brand_item_code]['daily'][date_val] = {
        'orders': safe_int(row[11]),
        'revenue': safe_int(row[12]),
        'favorites': safe_int(row[13]),
        'cartAdds': safe_int(row[14]),
        'stock': safe_int(row[15]),
        'stockWithReserve': safe_int(row[16]),
        'uu': safe_int(row[17]),
        'pv': safe_int(row[18]),
        'buyers': safe_int(row[19]),
        'male': safe_int(row[20]),
        'female': safe_int(row[21]),
        'newUsers': safe_int(row[22]),
        'existing': safe_int(row[23]),
        'reactivated': safe_int(row[24]),
        'avgAge': safe_float(row[25]),
        'avgPrice': safe_float(row[26]),
        'cvrUU': safe_float(row[27]),
        'cvrPV': safe_float(row[28]),
        'favRate': safe_float(row[29]),
    }

wb.close()
print(f"Total rows: {count:,}, Items: {len(items):,}")

# カテゴリ統計を計算
print("Computing category stats...")
cat_items = defaultdict(list)

for code, item in items.items():
    cat_key = f"{item['childCategory']}_{item['gender']}"
    
    # 月間集計
    total_uu = 0
    total_orders = 0
    total_favorites = 0
    total_buyers = 0
    total_revenue = 0
    days_count = len(item['daily'])
    
    for d in item['daily'].values():
        total_uu += d['uu']
        total_orders += d['orders']
        total_favorites += d['favorites']
        total_buyers += d['buyers']
        total_revenue += d['revenue']
    
    monthly_fav_rate = total_favorites / total_uu if total_uu > 0 else 0
    monthly_cvr_uu = total_buyers / total_uu if total_uu > 0 else 0
    
    cat_items[cat_key].append({
        'code': code,
        'productName': item['productName'],
        'brand': item['brand'],
        'totalUU': total_uu,
        'totalOrders': total_orders,
        'totalFavorites': total_favorites,
        'totalBuyers': total_buyers,
        'totalRevenue': total_revenue,
        'monthlyFavRate': round(monthly_fav_rate, 6),
        'monthlyCvrUU': round(monthly_cvr_uu, 6),
        'daysCount': days_count,
    })

category_stats = {}
for cat_key, cat_list in cat_items.items():
    parts = cat_key.rsplit('_', 1)
    child_cat = parts[0] if len(parts) > 1 else cat_key
    gender = parts[1] if len(parts) > 1 else ''
    
    # UU > 100 のアイテムのみで平均を計算（ノイズ除去）
    significant = [x for x in cat_list if x['totalUU'] >= 100]
    
    if not significant:
        significant = cat_list
    
    avg_fav = sum(x['monthlyFavRate'] for x in significant) / len(significant) if significant else 0
    avg_cvr = sum(x['monthlyCvrUU'] for x in significant) / len(significant) if significant else 0
    avg_uu = sum(x['totalUU'] for x in significant) / len(significant) if significant else 0
    avg_orders = sum(x['totalOrders'] for x in significant) / len(significant) if significant else 0
    
    # TOP10 by favRate
    top_fav = sorted(significant, key=lambda x: x['monthlyFavRate'], reverse=True)[:10]
    top_cvr = sorted(significant, key=lambda x: x['monthlyCvrUU'], reverse=True)[:10]
    
    # ランキング（全品番）
    ranked_fav = sorted(significant, key=lambda x: x['monthlyFavRate'], reverse=True)
    ranked_cvr = sorted(significant, key=lambda x: x['monthlyCvrUU'], reverse=True)
    
    # ランキングマップ
    fav_rank_map = {x['code']: i+1 for i, x in enumerate(ranked_fav)}
    cvr_rank_map = {x['code']: i+1 for i, x in enumerate(ranked_cvr)}
    
    category_stats[cat_key] = {
        'childCategory': child_cat,
        'gender': gender,
        'itemCount': len(cat_list),
        'significantCount': len(significant),
        'avgFavRate': round(avg_fav, 6),
        'avgCvrUU': round(avg_cvr, 6),
        'avgUU': round(avg_uu, 1),
        'avgOrders': round(avg_orders, 1),
        'topFavRate': [{'code': x['code'], 'name': x['productName'], 'brand': x['brand'], 'value': x['monthlyFavRate'], 'uu': x['totalUU']} for x in top_fav],
        'topCvrUU': [{'code': x['code'], 'name': x['productName'], 'brand': x['brand'], 'value': x['monthlyCvrUU'], 'uu': x['totalUU']} for x in top_cvr],
        'favRankMap': fav_rank_map,
        'cvrRankMap': cvr_rank_map,
    }

sorted_dates = sorted(dates_set)

output = {
    'items': items,
    'categoryStats': category_stats,
    'meta': {
        'dateRange': [sorted_dates[0], sorted_dates[-1]],
        'dates': sorted_dates,
        'totalItems': len(items),
        'brands': sorted(brands_set),
        'shops': sorted(shops_set),
    }
}

print("Writing JSON...")
with open('/home/ubuntu/dashboard_data.json', 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, separators=(',', ':'))

import os
size = os.path.getsize('/home/ubuntu/dashboard_data.json')
print(f"Output: /home/ubuntu/dashboard_data.json ({size / 1024 / 1024:.1f} MB)")
print(f"Items: {len(items):,}, Categories: {len(category_stats):,}, Dates: {len(sorted_dates)}")
print("Done!")
