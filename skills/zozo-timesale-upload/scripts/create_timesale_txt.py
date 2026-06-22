#!/usr/bin/env python3
"""タイムセール用TXTファイルを自動生成するスクリプト。

Usage:
    python create_timesale_txt.py <output_file> <start_dt> <end_dt> <items_json>

Args:
    output_file: 出力ファイルパス（例: /home/ubuntu/sc841ver2.txt）
    start_dt:    開始日時 YYYYMMDDhh（例: 2026041409）
    end_dt:      終了日時 YYYYMMDDhh（例: 2026042809）
    items_json:  品番・価格のJSON配列
                 例: '[{"brand":"sc678","price":1800,"reset_price":1817},{"brand":"hc991","price":1500,"reset_price":1540}]'

Output:
    タブ区切りTXTファイル（ヘッダーなし）を生成。
"""
import sys
import json


def main():
    if len(sys.argv) != 5:
        print(__doc__)
        sys.exit(1)

    output_file = sys.argv[1]
    start_dt = sys.argv[2]
    end_dt = sys.argv[3]
    items = json.loads(sys.argv[4])

    lines = []
    for item in items:
        brand = item["brand"]
        price = item["price"]
        reset_price = item["reset_price"]
        lines.append(f"{brand}\t{price}\t{start_dt}\t{end_dt}\t{reset_price}")

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"Created: {output_file} ({len(lines)} items)")
    for line in lines:
        print(f"  {line}")


if __name__ == "__main__":
    main()
