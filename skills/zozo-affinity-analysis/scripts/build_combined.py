"""
ZOZO買い回り相性分析 Step 2: データ読み込み・結合
買い回りデータとショップ指標データを読み込み、中間CSVを生成する。

Usage:
  python build_combined.py \
    --buyback <買い回りデータ.xlsx> \
    --shop_files <26年1月.xlsx> [<26年2月.xlsx> ...] \
    --output_dir <出力ディレクトリ>
"""
import argparse
import pandas as pd
import os
import warnings
warnings.filterwarnings('ignore')

# 自社ブランド除外リスト（買い回り先から自社ショップを除外）
OWN_BRANDS = [
    'MONO-MART', 'EMMA CLOTHES', 'WYM LIDNM', 'THE CRAFT CREW',
    'Alfred Alex', 'Anchor Smith', 'ADRER', 'CLEL', 'LOOSE', 'cussil',
    'GRANCY', 'SERACE', 'LUENNA', 'RUUBON', 'forksy.', "MONO-MART LADY'S",
    'BONLECILL', 'Heart Tattoo', 'ELUNIS', 'Elishe', 'Parts Lab.', 'Aunely'
]

# ショップ指標Excelのカラムマッピング（ヘッダーが2行目にある構造に対応）
SHOP_COL_NAMES = [
    'ショップ名', '受注売上', '受注数', 'ゲスト購入者注文数', '販売枚数',
    '新規再入荷品番数', '購入者数', '購入者男性比率', '購入者女性比率', '購入者平均年齢',
    '企業名', '_空白',
    '昨年同月売上', '昨年同月販売枚数', '昨年同月1枚単価',
    '売上昨対比', '販売枚数昨対比', '1枚単価昨対比',
    '1枚単価', '1件平均', '客単価', 'セット率',
    '今年度累計売上', '前年度累計売上', '年度累計売上昨対比',
    '今年度累計販売枚数', '前年度累計販売枚数', '年度累計販売枚数昨対比'
]

NUM_COLS = [
    '受注売上', '受注数', 'ゲスト購入者注文数', '販売枚数', '新規再入荷品番数',
    '購入者数', '購入者男性比率', '購入者女性比率', '購入者平均年齢',
    '昨年同月売上', '昨年同月販売枚数', '昨年同月1枚単価',
    '売上昨対比', '販売枚数昨対比', '1枚単価昨対比',
    '1枚単価', '1件平均', '客単価', 'セット率',
    '今年度累計売上', '前年度累計売上', '年度累計売上昨対比',
    '今年度累計販売枚数', '前年度累計販売枚数', '年度累計販売枚数昨対比'
]


def load_shop_master(path, month_label):
    """ショップ指標Excelを読み込んでDataFrameを返す。"""
    raw = pd.read_excel(path, sheet_name='Sheet1', header=None)
    df = raw.iloc[1:].copy()
    df.columns = SHOP_COL_NAMES[:len(df.columns)]
    df = df[df['ショップ名'].notna() & (df['ショップ名'] != 'ショップ名')].copy()
    for c in NUM_COLS:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce')
    df['月'] = month_label
    df = df.drop(columns=['_空白'], errors='ignore')
    print(f"  {month_label}: {len(df)}ショップ読み込み完了")
    return df


def load_buyback(path):
    """買い回りデータExcelを全シート読み込んでショップ別集計DataFrameを返す。"""
    xl = pd.ExcelFile(path)
    brand_sheets = xl.sheet_names
    print(f"  ブランド数: {len(brand_sheets)}")
    frames = []
    for brand in brand_sheets:
        df = pd.read_excel(path, sheet_name=brand)
        if 'ショップ名' not in df.columns:
            print(f"  警告: {brand} シートに「ショップ名」列がありません。スキップします。")
            continue
        grp = df.groupby('ショップ名').agg(
            買い回り件数=('売上点数', 'count'),
            買い回り売上点数=('売上点数', 'sum'),
            買い回り売上金額=('売上金額', 'sum')
        ).reset_index()
        grp['ブランド'] = brand
        frames.append(grp)
    buyback_all = pd.concat(frames, ignore_index=True)
    print(f"  買い回り集計レコード数: {len(buyback_all)}")
    return buyback_all


def main():
    parser = argparse.ArgumentParser(description='ZOZO買い回り相性分析 データ結合')
    parser.add_argument('--buyback', required=True, help='買い回りデータExcelパス')
    parser.add_argument('--shop_files', nargs='+', required=True, help='ショップ指標Excelパス（複数可）')
    parser.add_argument('--output_dir', required=True, help='中間CSV出力ディレクトリ')
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    # ショップ指標読み込み
    print("=== ショップ指標データ読み込み ===")
    shop_frames = []
    for path in args.shop_files:
        month_label = os.path.basename(path).replace('.xlsx', '')
        df = load_shop_master(path, month_label)
        shop_frames.append(df)
        df.to_csv(f"{args.output_dir}/shop_master_{month_label}.csv", index=False, encoding='utf-8-sig')
    shop_all = pd.concat(shop_frames, ignore_index=True)

    # 最新月のショップ指標を結合用に使用
    latest_month = shop_all['月'].max()
    shop_latest = shop_all[shop_all['月'] == latest_month][
        ['ショップ名', '受注売上', '受注数', '購入者数', '販売枚数',
         '購入者男性比率', '購入者女性比率', '購入者平均年齢',
         '1枚単価', '1件平均', '客単価', 'セット率', '売上昨対比']
    ].copy()
    print(f"  結合用ショップ指標: {latest_month}（{len(shop_latest)}ショップ）")

    # 買い回りデータ読み込み
    print("\n=== 買い回りデータ読み込み ===")
    buyback_all = load_buyback(args.buyback)

    # 結合
    print("\n=== データ結合 ===")
    merged = buyback_all.merge(shop_latest, on='ショップ名', how='left')
    print(f"  結合後レコード数: {len(merged)}")
    print(f"  ショップ名マッチ率: {merged['受注売上'].notna().sum()} / {len(merged)}")

    # 自社ショップ除外
    merged_other = merged[~merged['ショップ名'].isin(OWN_BRANDS)].copy()
    print(f"  他社ショップのみ: {len(merged_other)}レコード")

    # 保存
    merged.to_csv(f"{args.output_dir}/merged_all.csv", index=False, encoding='utf-8-sig')
    merged_other.to_csv(f"{args.output_dir}/merged_other.csv", index=False, encoding='utf-8-sig')
    print(f"\n完了。中間CSVを {args.output_dir} に保存しました。")


if __name__ == '__main__':
    main()
