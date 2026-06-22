#!/usr/bin/env python3
"""
指定カテゴリの週別係数を表示するユーティリティ。

Usage:
    python show_coefficients.py <coefficients_json> <category> [--weeks START-END]

Examples:
    python show_coefficients.py coefficients.json パーカー
    python show_coefficients.py coefficients.json パーカー --weeks 13-22
"""
import sys
import json
import argparse


def main():
    parser = argparse.ArgumentParser(description='カテゴリ別52週係数の表示')
    parser.add_argument('coefficients_json', help='52週係数JSONファイル')
    parser.add_argument('category', help='カテゴリ(子)名')
    parser.add_argument('--weeks', default='1-52', help='表示週範囲 (例: 13-22)')
    parser.add_argument('--base-week', type=int, default=None, help='基準週（比率計算用）')
    args = parser.parse_args()

    with open(args.coefficients_json, 'r', encoding='utf-8') as f:
        coefficients = json.load(f)

    if args.category not in coefficients:
        print(f"Error: カテゴリ '{args.category}' が見つかりません。")
        print(f"利用可能なカテゴリ: {', '.join(sorted(coefficients.keys()))}")
        sys.exit(1)

    coef = coefficients[args.category]['weekly_coefficients']
    total = coefficients[args.category]['total_sales']

    start, end = map(int, args.weeks.split('-'))
    base_week = args.base_week or start
    base_coef = coef[str(base_week)]

    print(f"カテゴリ: {args.category} (年間販売数: {total:,})")
    print(f"基準週: 第{base_week}週 (係数: {base_coef:.5f})")
    print(f"\n{'週':>4} {'係数':>10} {'基準週比':>10}")
    print("-" * 28)
    for w in range(start, end + 1):
        c = coef[str(w)]
        ratio = c / base_coef if base_coef > 0 else 0
        print(f"{w:>4} {c:>10.5f} {ratio:>10.4f}")


if __name__ == '__main__':
    main()
