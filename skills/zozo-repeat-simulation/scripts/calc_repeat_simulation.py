#!/usr/bin/env python3
"""
ZOZO リピート発注シミュレーションスクリプト
入力JSONから各品番の予測販売数、在庫持ち月数、リピート推奨数量を算出する。

使い方:
  python calc_repeat_simulation.py <入力JSON> <出力JSON> [--coefficients <係数JSON>]

入力JSON形式: list[dict] で各品番に以下のキーを含む:
  item_id, category, current_inv, monthly_sales (12要素, 4月始まり),
  gm_score, sales_score, season_score, cross_score, gm_rate, gm_change
"""
import json
import sys
import os
import math
import statistics
import argparse

# デフォルトの季節係数ファイルパス（スキルディレクトリからの相対パス）
DEFAULT_COEFF_PATH = os.path.join(os.path.dirname(__file__), '..', 'references', 'monthly_coefficients.json')

# 月順序（4月始まり）
MONTH_ORDER = [4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2, 3]

# スコア重み
W_GM = 0.40       # 粗利率
W_SALES = 0.25    # 販売数
W_SEASON = 0.20   # 季節安定性
W_CROSS = 0.15    # 併売率

def load_coefficients(coeff_path):
    """月別係数JSONを読み込み、{カテゴリ: {月番号: 係数}} 形式に変換"""
    with open(coeff_path, 'r', encoding='utf-8') as f:
        raw = json.load(f)
    coeffs = {}
    for cat, vals in raw.items():
        coeffs[cat] = {MONTH_ORDER[i]: vals[i] for i in range(12)}
    return coeffs

def score_to_months(score):
    """スコアから在庫持ち月数を決定"""
    if score >= 75: return 5.0
    elif score >= 60: return 4.0
    elif score >= 40: return 3.0
    elif score >= 25: return 2.5
    else: return 2.0

def get_coefficients(category, monthly_coeffs):
    """カテゴリから月別係数を取得（fallback: Tシャツ/カットソー）"""
    if category in monthly_coeffs:
        return monthly_coeffs[category]
    for k in monthly_coeffs:
        if category in k:
            return monthly_coeffs[k]
    return monthly_coeffs.get('Tシャツ/カットソー', {m: 1.0 for m in range(1, 13)})

def calc_peak_demand(months_hold, forecast_8to3, coeffs_8to3):
    """
    係数上位N月の需要合計を算出（ピーク月選択方式）
    8月〜3月の中から季節係数の高い順にN月分を選択する。
    端数月（例: 2.5ヶ月）は、上位2月の全量 + 3番目の月の50%。
    """
    # 月ごとの(月番号, 係数, 予測値)をリスト化し、係数降順にソート
    aug_to_mar = [8, 9, 10, 11, 12, 1, 2, 3]
    pairs = [(aug_to_mar[i], coeffs_8to3[i], forecast_8to3[i]) for i in range(8)]
    sorted_pairs = sorted(pairs, key=lambda x: x[1], reverse=True)
    
    full_months = int(months_hold)
    frac = months_hold - full_months
    
    demand = sum(x[2] for x in sorted_pairs[:full_months])
    if frac > 0 and full_months < len(sorted_pairs):
        demand += round(sorted_pairs[full_months][2] * frac)
    
    selected_months = sorted([x[0] for x in sorted_pairs[:int(math.ceil(months_hold))]])
    return demand, selected_months

def process_data(input_data, monthly_coeffs):
    """全品番のシミュレーションを実行"""
    results = []
    
    for row in input_data:
        item_id = row.get('item_id', '')
        category = row.get('category', '')
        current_inv = int(row.get('current_inv', 0))
        monthly = row.get('monthly_sales', [0]*12)  # 4月〜3月の12ヶ月配列
        
        # スコア要素
        gm_score = float(row.get('gm_score', 0))
        sales_score = float(row.get('sales_score', 0))
        season_score = float(row.get('season_score', 0))
        cross_score = float(row.get('cross_score', 0))
        gm_rate = float(row.get('gm_rate', 0))
        gm_change = float(row.get('gm_change', 0))
        
        coeffs = get_coefficients(category, monthly_coeffs)
        
        # 販売月数と月平均
        active_months = sum(1 for m in monthly if m > 0)
        active_avg = sum(monthly) / active_months if active_months > 0 else 0
        
        if active_months == 0:
            results.append({
                'item_id': item_id, 'category': category, 'method': 'なし',
                'active_months': 0, 'base_power': 0,
                'forecast_4to7': [0,0,0,0], 'forecast_8to3': [0]*8,
                'inv_monthly': [0,0,0,0], 'inv_end_jul': 0,
                'base_score': 0, 'score_with_penalty': 0,
                'months_no_penalty': 2, 'months_with_penalty': 2,
                'rec_no_penalty': 0, 'rec_with_penalty': 0,
                'pena_gm': 0, 'pena_abs': 0, 'total_penalty': 0,
                'selected_months_1': [], 'selected_months_2': [],
            })
            continue
        
        # ===== 予測方式の決定 =====
        if active_avg <= 1000 and active_months <= 3:
            method = "フラット"
            base_power = active_avg
            forecasts = {m: round(base_power) for m in range(1, 13)}
        elif active_avg <= 1000 and active_months <= 5:
            method = "季節係数（単純平均）"
            base_values = []
            for i, sales in enumerate(monthly):
                if sales > 0:
                    m = MONTH_ORDER[i]
                    coeff = coeffs.get(m, 1.0)
                    if coeff > 0.05:
                        base_values.append(sales / coeff)
            base_power = sum(base_values) / len(base_values) if base_values else active_avg
            forecasts = {m: max(0, round(base_power * coeffs.get(m, 1.0))) for m in range(1, 13)}
        elif active_months >= 6:
            method = "季節係数（直近重み）"
            base_values = []
            for i, sales in enumerate(monthly):
                if sales > 0:
                    m = MONTH_ORDER[i]
                    coeff = coeffs.get(m, 1.0)
                    if coeff > 0.05:
                        base_values.append(sales / coeff)
            if not base_values:
                base_power = active_avg
            else:
                recent_3 = base_values[-3:]
                recent_avg = sum(recent_3) / len(recent_3)
                all_avg = sum(base_values) / len(base_values)
                sorted_bases = sorted(base_values)
                median_base = sorted_bases[len(sorted_bases)//2]
                weighted_avg = recent_avg * 0.6 + all_avg * 0.4
                base_power = min(weighted_avg, median_base * 2)  # 中央値2倍キャップ
            forecasts = {m: max(0, round(base_power * coeffs.get(m, 1.0))) for m in range(1, 13)}
        else:
            method = "季節係数（中央値）"
            base_values = []
            for i, sales in enumerate(monthly):
                if sales > 0:
                    m = MONTH_ORDER[i]
                    coeff = coeffs.get(m, 1.0)
                    if coeff > 0.05:
                        base_values.append(sales / coeff)
            base_power = statistics.median(base_values) if base_values else active_avg
            forecasts = {m: max(0, round(base_power * coeffs.get(m, 1.0))) for m in range(1, 13)}
        
        # ===== 4-7月の予測と在庫消化 =====
        pred_4to7 = [forecasts[m] for m in [4, 5, 6, 7]]
        remaining = current_inv
        inv_monthly = []
        for p in pred_4to7:
            remaining = max(0, remaining - p)
            inv_monthly.append(remaining)
        inv_end_jul = inv_monthly[3]
        
        # ===== 8月〜3月の予測 =====
        forecast_8to3 = [forecasts[m] for m in [8, 9, 10, 11, 12, 1, 2, 3]]
        coeffs_8to3 = [coeffs.get(m, 1.0) for m in [8, 9, 10, 11, 12, 1, 2, 3]]
        
        # ===== スコア計算 =====
        base_score = gm_score * W_GM + sales_score * W_SALES + season_score * W_SEASON + cross_score * W_CROSS
        
        # ===== ペナルティ計算 =====
        pena_gm = min(abs(gm_change) * 0.8, 30) if gm_change < -2 else 0
        pena_abs = (30 - gm_rate) * 1.0 if gm_rate < 30 else 0
        total_penalty = min(pena_gm + pena_abs, 30)
        score_with_penalty = max(0, base_score - total_penalty)
        
        # ===== 在庫持ち月数 =====
        months_no = score_to_months(base_score)
        months_pen = score_to_months(score_with_penalty)
        
        # ===== ピーク月選択方式で需要算出 =====
        demand_1, sel_months_1 = calc_peak_demand(months_no, forecast_8to3, coeffs_8to3)
        demand_2, sel_months_2 = calc_peak_demand(months_pen, forecast_8to3, coeffs_8to3)
        
        rec_no = max(0, demand_1 - inv_end_jul)
        rec_pen = max(0, demand_2 - inv_end_jul)
        
        results.append({
            'item_id': item_id,
            'category': category,
            'method': method,
            'active_months': active_months,
            'base_power': round(base_power),
            'forecast_4to7': pred_4to7,
            'forecast_8to3': forecast_8to3,
            'inv_monthly': inv_monthly,
            'inv_end_jul': inv_end_jul,
            'base_score': round(base_score, 1),
            'score_with_penalty': round(score_with_penalty, 1),
            'months_no_penalty': months_no,
            'months_with_penalty': months_pen,
            'selected_months_1': sel_months_1,
            'selected_months_2': sel_months_2,
            'rec_no_penalty': rec_no,
            'rec_with_penalty': rec_pen,
            'pena_gm': round(pena_gm, 1),
            'pena_abs': round(pena_abs, 1),
            'total_penalty': round(total_penalty, 1),
        })
    
    return results

def main():
    parser = argparse.ArgumentParser(description="ZOZO リピート発注シミュレーション")
    parser.add_argument("input", help="入力JSONファイルのパス")
    parser.add_argument("output", help="出力JSONファイルのパス")
    parser.add_argument("--coefficients", default=DEFAULT_COEFF_PATH,
                        help="カテゴリ別月別係数JSONファイルのパス")
    args = parser.parse_args()
    
    monthly_coeffs = load_coefficients(args.coefficients)
    
    with open(args.input, 'r', encoding='utf-8') as f:
        input_data = json.load(f)
    
    results = process_data(input_data, monthly_coeffs)
    
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    # サマリー出力
    total_1 = sum(r['rec_no_penalty'] for r in results)
    total_2 = sum(r['rec_with_penalty'] for r in results)
    print(f"処理完了: {len(results)}件")
    print(f"①ペナなし推奨合計: {total_1:,}着")
    print(f"②ペナあり推奨合計: {total_2:,}着")

if __name__ == "__main__":
    main()
