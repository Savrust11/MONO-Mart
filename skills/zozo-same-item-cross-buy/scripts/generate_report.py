#!/usr/bin/env python3
"""
同一品番併売分析 PDF1枚レポート生成スクリプト

使い方:
  python3 generate_report.py <analysis_json> [--out <output_pdf>]

引数:
  analysis_json   analyze_same_item.py の出力JSONファイルパス
  --out           出力PDFファイルパス（デフォルト: report.pdf）

前提:
  - matplotlib, weasyprint がインストール済み
  - Noto Sans CJK JP フォントがインストール済み
"""
import argparse
import json
import base64
import io
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams['font.family'] = 'Noto Sans CJK JP'
plt.rcParams['axes.unicode_minus'] = False

C_MAIN = '#2563EB'
C_COMP = '#F59E0B'
C_AVG  = '#94A3B8'


def fig_to_b64(fig, dpi=150):
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=dpi, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()


def make_chart_bar_compare(target, compare, cat_avg):
    """横棒: 対象 vs 比較 vs カテゴリ平均"""
    fig, ax = plt.subplots(figsize=(4.2, 1.1))
    labels = [f'カテゴリ平均\n({target["カテゴリ内順位"].split("/")[1]})',
              f'{target["ブランド品番"]}\n({target["カラー展開数"]}色)',
              f'{compare["ブランド品番"]}\n({compare["カラー展開数"]}色)']
    vals = [cat_avg, target['同一品番併売率'], compare['同一品番併売率']]
    bars = ax.barh(labels, vals, color=[C_AVG, C_MAIN, C_COMP], height=0.5, edgecolor='white')
    for bar, val in zip(bars, vals):
        ax.text(bar.get_width()+0.3, bar.get_y()+bar.get_height()/2, f'{val:.1f}%', va='center', fontsize=8, fontweight='bold')
    ax.set_xlim(0, max(vals)*1.4)
    ax.set_xlabel('同一品番併売率 (%)', fontsize=7)
    ax.tick_params(labelsize=7); ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
    return fig_to_b64(fig)


def make_chart_scatter(category, target, compare):
    """散布図: カラー展開数 vs 併売率"""
    fig, ax = plt.subplots(figsize=(4.2, 2.0))
    ranking = category['ランキング']
    xs = [r['カラー展開数'] for r in ranking]
    ys = [r['同一品番併売率'] for r in ranking]
    ax.scatter(xs, ys, alpha=0.35, s=20, color=C_AVG, edgecolors='white', linewidth=0.3, zorder=2)
    ax.scatter([target['カラー展開数']], [target['同一品番併売率']], s=70, color=C_MAIN, edgecolors='white', linewidth=1, zorder=5)
    ax.annotate(target['ブランド品番'], (target['カラー展開数'], target['同一品番併売率']),
                textcoords='offset points', xytext=(7,-7), fontsize=7, fontweight='bold', color=C_MAIN)
    ax.scatter([compare['カラー展開数']], [compare['同一品番併売率']], s=70, color=C_COMP, edgecolors='white', linewidth=1, zorder=5)
    ax.annotate(compare['ブランド品番'], (compare['カラー展開数'], compare['同一品番併売率']),
                textcoords='offset points', xytext=(7,-7), fontsize=7, fontweight='bold', color=C_COMP)
    z = np.polyfit(xs, ys, 1); p = np.poly1d(z)
    x_line = np.linspace(min(xs), max(xs), 50)
    ax.plot(x_line, p(x_line), '--', color='#64748B', linewidth=1, alpha=0.7, zorder=1)
    ax.set_xlabel('カラー展開数', fontsize=7); ax.set_ylabel('同一品番併売率 (%)', fontsize=7)
    ax.tick_params(labelsize=6.5); ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
    ax.text(0.97, 0.05, f'r = {category["相関_カラー展開数"]:.2f}', transform=ax.transAxes, fontsize=7, ha='right', color='#64748B')
    ax.set_title('カラー展開数 vs 同一品番併売率', fontsize=8, fontweight='bold', pad=4)
    return fig_to_b64(fig)


def make_chart_main_color(category, target_rate):
    """棒グラフ: メインカラー数別平均併売率"""
    data = category.get('メインカラー数別平均併売率', {})
    if not data:
        return None
    xs = sorted([int(k) for k in data.keys()])
    ys = [data[str(x)] if str(x) in data else data.get(x, 0) for x in xs]
    fig, ax = plt.subplots(figsize=(4.2, 1.5))
    ax.bar(xs, ys, color='#3B82F6', width=0.6, edgecolor='white')
    for x, y in zip(xs, ys):
        ax.text(x, y+0.4, f'{y:.1f}%', ha='center', fontsize=6, fontweight='bold')
    ax.axhline(y=target_rate, color=C_MAIN, linestyle='--', linewidth=1, alpha=0.7)
    ax.text(max(xs)+0.2, target_rate+0.3, f'{target_rate:.1f}%', fontsize=6, color=C_MAIN)
    ax.set_xlabel('メインカラー数', fontsize=7); ax.set_ylabel('平均併売率 (%)', fontsize=7)
    ax.tick_params(labelsize=6.5); ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
    ax.set_title('メインカラー数と平均併売率', fontsize=8, fontweight='bold', pad=4)
    return fig_to_b64(fig)


def make_chart_cat_pair(target, compare):
    """積み上げ横棒: カラー分類ペア構成比"""
    all_keys = ['メインカラー×メインカラー','シーズンカラー×メインカラー','シーズンカラー×シーズンカラー',
                'アクセントカラー×メインカラー','アクセントカラー×シーズンカラー','アクセントカラー×アクセントカラー']
    labels_short = ['メイン×メイン','シーズン×メイン','シーズン×シーズン','アクセント×メイン','アクセント×シーズン','アクセント×アクセント']
    colors_stack = ['#3B82F6','#F97316','#FBBF24','#A78BFA','#FB923C','#EC4899']

    fig, ax = plt.subplots(figsize=(4.2, 1.1))
    brands = [target['ブランド品番'], compare['ブランド品番']]
    bottoms = [0, 0]
    for i, key in enumerate(all_keys):
        vals = [target['カラー分類ペア構成比'].get(key, 0), compare['カラー分類ペア構成比'].get(key, 0)]
        ax.barh(brands, vals, left=bottoms, color=colors_stack[i], label=labels_short[i], height=0.45, edgecolor='white', linewidth=0.3)
        for j in range(2):
            if vals[j] > 6:
                ax.text(bottoms[j]+vals[j]/2, j, f'{vals[j]:.0f}%', ha='center', va='center', fontsize=6, color='white', fontweight='bold')
        bottoms = [b+v for b, v in zip(bottoms, vals)]
    ax.set_xlim(0, 105); ax.tick_params(labelsize=7)
    ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
    ax.legend(fontsize=5, ncol=3, loc='upper center', bbox_to_anchor=(0.5, -0.2), frameon=False)
    ax.set_title('色違い併売のカラー分類ペア構成比', fontsize=8, fontweight='bold', pad=4)
    return fig_to_b64(fig)


def build_pair_table_html(item, label_color):
    """色ペアTOP5テーブルHTML"""
    rows = ''
    for p in item['色ペアTOP10'][:5]:
        bold = ' style="font-weight:bold"' if p == item['色ペアTOP10'][0] else ''
        rows += f'<tr><td>{p["ペア"]}</td><td{bold}>{p["件数"]}件</td></tr>\n'
    return f'''<div class="pair-title" style="color:{label_color};">{item["ブランド品番"]} 色ペアTOP5</div>
<table>{rows}</table>'''


def generate_conclusion(target, compare, category):
    """カラー展開提案の結論テキストを生成"""
    t_main = target['メインカラー数']
    t_season = target['シーズンカラー数']
    t_accent = target['アクセントカラー数']
    main_avg = category.get('メインカラー数別平均併売率', {})
    t_main_pct = target['カラー分類ペア構成比'].get('メインカラー×メインカラー', 0)
    next_main = main_avg.get(str(t_main + 1), main_avg.get(t_main + 1, None))

    if t_main_pct >= 40 and next_main and next_main > target['同一品番併売率']:
        main_conclusion = f'メインカラーを1色追加（計{t_main+1}色）することを最優先で推奨'
        detail = (f'現状{target["カラー展開数"]}色（メイン{t_main}/シーズン{t_season}/アクセント{t_accent}）。'
                  f'併売ペアの{t_main_pct:.0f}%がメインカラー同士のため、メインカラー拡充が最も効果的。'
                  f'メインカラー{t_main+1}色品番群の平均併売率は{next_main}%と現在の{target["同一品番併売率"]}%を上回る。'
                  f'既存色と明度差のあるメインカラー追加を推奨。')
    elif t_season <= 1:
        main_conclusion = f'シーズンカラーを1〜2色追加することを推奨'
        detail = (f'現状{target["カラー展開数"]}色（メイン{t_main}/シーズン{t_season}/アクセント{t_accent}）。'
                  f'シーズンカラーが少なく、メインカラーとの組み合わせ余地が大きい。')
    else:
        main_conclusion = f'メインカラーを1色追加（計{t_main+1}色）することを推奨'
        detail = (f'現状{target["カラー展開数"]}色（メイン{t_main}/シーズン{t_season}/アクセント{t_accent}）。'
                  f'メインカラーは全分類と組み合わせやすく、併売率向上に直結する。')

    # 比較品番の提案
    c_main_pct = compare['カラー分類ペア構成比'].get('メインカラー×メインカラー', 0)
    if c_main_pct >= 30:
        compare_detail = (f'{compare["カラー展開数"]}色展開だが併売ペアの{c_main_pct:.0f}%がメインカラー同士で最多。'
                          f'さらに伸ばすにはメインカラー追加が最も効率的。')
    else:
        compare_detail = (f'{compare["カラー展開数"]}色展開。シーズンカラーやアクセントカラーとの組み合わせが多く、'
                          f'多色展開が併売を牽引している。')

    return main_conclusion, detail, compare_detail


def build_html(data):
    """PDF用HTMLを構築"""
    target = data['target']
    compare = data['compare']
    category = data['category']
    cat_avg = category['平均併売率']

    brand_key_label = target.get('ブランドキー', '') or 'フォールバック'

    b64_c1 = make_chart_bar_compare(target, compare, cat_avg)
    b64_c2 = make_chart_scatter(category, target, compare)
    b64_c3 = make_chart_main_color(category, target['同一品番併売率'])
    b64_c4 = make_chart_cat_pair(target, compare)

    pair_html_target = build_pair_table_html(target, C_MAIN)
    pair_html_compare = build_pair_table_html(compare, C_COMP)

    main_conclusion, detail_target, detail_compare = generate_conclusion(target, compare, category)

    # メインカラー数チャート（データがない場合はプレースホルダ）
    main_color_chart_html = ''
    if b64_c3:
        main_color_chart_html = f'<img src="data:image/png;base64,{b64_c3}" style="margin-top:2px;">'
    else:
        main_color_chart_html = '<p style="font-size:6pt; color:#94A3B8; text-align:center; padding:10px;">メインカラー数別データなし</p>'

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<style>
@page {{ size: 420mm 297mm; margin: 6mm 10mm 4mm 10mm; }}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: 'Noto Sans CJK JP', sans-serif; font-size: 7pt; color: #1E293B; line-height: 1.35; background: white; }}
.clearfix::after {{ content: ""; display: table; clear: both; }}
.header {{ background: linear-gradient(135deg, #1E3A8A 0%, #2563EB 100%); color: white; padding: 7px 14px 5px; border-radius: 4px; margin-bottom: 3px; }}
.header h1 {{ font-size: 13pt; font-weight: 700; }}
.header .sub {{ font-size: 6.5pt; opacity: 0.85; margin-top: 1px; }}
.kpi-row {{ margin-bottom: 3px; }}
.kpi-row::after {{ content: ""; display: table; clear: both; }}
.kpi {{ float: left; width: 24.25%; margin-right: 1%; background: #F1F5F9; border: 1px solid #E2E8F0; border-radius: 4px; padding: 3px 5px; text-align: center; }}
.kpi:last-child {{ margin-right: 0; }}
.kpi .label {{ font-size: 5.5pt; color: #64748B; }}
.kpi .value {{ font-size: 12pt; font-weight: 800; color: #1E3A8A; }}
.kpi .unit {{ font-size: 5.5pt; color: #94A3B8; }}
.kpi.red .value {{ color: #DC2626; }}
.col-left {{ float: left; width: 49.5%; }}
.col-right {{ float: right; width: 49.5%; }}
.card {{ background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 4px; padding: 5px 7px; margin-bottom: 3px; }}
.card h3 {{ font-size: 7.5pt; color: #1E3A8A; border-bottom: 1.5px solid #2563EB; padding-bottom: 2px; margin-bottom: 3px; }}
.card img {{ width: 100%; height: auto; display: block; }}
table {{ width: 100%; border-collapse: collapse; font-size: 6pt; }}
th {{ background: #E2E8F0; padding: 2px 3px; text-align: left; font-weight: 600; font-size: 5.5pt; }}
td {{ padding: 1.5px 3px; border-bottom: 1px solid #E2E8F0; }}
.pair-left {{ float: left; width: 49%; }}
.pair-right {{ float: right; width: 49%; }}
.pair-title {{ font-size: 6pt; font-weight: 700; margin-bottom: 1px; }}
.conclusion-box {{ clear: both; background: linear-gradient(135deg, #FEF3C7 0%, #FDE68A 100%); border: 2px solid #F59E0B; border-radius: 5px; padding: 7px 10px; margin-top: 3px; }}
.conclusion-box h3 {{ font-size: 8.5pt; color: #92400E; border-bottom: 1.5px solid #D97706; padding-bottom: 2px; margin-bottom: 4px; }}
.conclusion-main {{ font-size: 12pt; font-weight: 800; color: #DC2626; text-align: center; margin: 3px 0; }}
.concl-left {{ float: left; width: 49%; font-size: 5.8pt; color: #78350F; line-height: 1.3; }}
.concl-right {{ float: right; width: 49%; font-size: 5.8pt; color: #78350F; line-height: 1.3; }}
.concl-left b, .concl-right b {{ color: #92400E; }}
.footer {{ clear: both; text-align: right; font-size: 5pt; color: #94A3B8; margin-top: 3px; }}
</style>
</head>
<body>
<div class="header">
    <h1>同一品番併売分析レポート ── {target['ブランド品番']}</h1>
    <div class="sub">{target['子商品タイプ']}（{target['性別']}）｜ カラー分類: {brand_key_label} ｜ 比較: {compare['ブランド品番']}（同カテゴリ同性別）</div>
</div>
<div class="kpi-row">
    <div class="kpi"><div class="label">{target['ブランド品番']} 注文件数</div><div class="value">{target['注文件数']:,}</div><div class="unit">件</div></div>
    <div class="kpi red"><div class="label">{target['ブランド品番']} 同一品番併売率</div><div class="value">{target['同一品番併売率']}%</div><div class="unit">{target['同一品番併売件数']:,}件 / {target['注文件数']:,}件</div></div>
    <div class="kpi"><div class="label">{compare['ブランド品番']} 同一品番併売率</div><div class="value">{compare['同一品番併売率']}%</div><div class="unit">{compare['同一品番併売件数']:,}件 / {compare['注文件数']:,}件</div></div>
    <div class="kpi"><div class="label">カテゴリ平均</div><div class="value">{cat_avg}%</div><div class="unit">{category['対象品番数']}品番（注文100件以上）</div></div>
</div>
<div class="clearfix">
<div class="col-left">
    <div class="card">
        <h3>1. {target['ブランド品番']} vs {compare['ブランド品番']} 基本比較</h3>
        <table>
            <tr><th style="width:25%"></th><th style="width:37.5%">{target['ブランド品番']}</th><th style="width:37.5%">{compare['ブランド品番']}</th></tr>
            <tr><td>商品名</td><td>{target['商品名']}</td><td>{compare['商品名']}</td></tr>
            <tr><td>カラー展開</td><td>{target['カラー展開数']}色（メイン{target['メインカラー数']} / シーズン{target['シーズンカラー数']} / アクセント{target['アクセントカラー数']}）</td><td>{compare['カラー展開数']}色（メイン{compare['メインカラー数']} / シーズン{compare['シーズンカラー数']} / アクセント{compare['アクセントカラー数']}）</td></tr>
            <tr><td>同一品番併売率</td><td><b style="color:#2563EB">{target['同一品番併売率']}%</b>（{target['カテゴリ内順位']}）</td><td><b style="color:#F59E0B">{compare['同一品番併売率']}%</b>（{compare['カテゴリ内順位']}）</td></tr>
        </table>
        <img src="data:image/png;base64,{b64_c1}" style="margin-top:3px;">
    </div>
    <div class="card">
        <h3>2. 色違い併売のカラー分類構成</h3>
        <img src="data:image/png;base64,{b64_c4}">
        <div class="clearfix" style="margin-top:2px;">
            <div class="pair-left">{pair_html_target}</div>
            <div class="pair-right">{pair_html_compare}</div>
        </div>
    </div>
</div>
<div class="col-right">
    <div class="card">
        <h3>3. カラー展開数・構成と併売率の関係</h3>
        <img src="data:image/png;base64,{b64_c2}">
        {main_color_chart_html}
        <p style="font-size:5.5pt; color:#64748B; margin-top:1px;">展開数が多いほど併売率は上昇（r={category['相関_カラー展開数']}）。メインカラー数の増加で平均併売率が大きく向上。</p>
    </div>
</div>
</div>
<div class="conclusion-box">
    <h3>結論：{target['ブランド品番']} は今後カラー展開を増やすべきか？</h3>
    <div class="conclusion-main">{main_conclusion}</div>
    <div class="clearfix" style="margin-top:4px;">
        <div class="concl-left"><b>【{target['ブランド品番']}への提案】</b><br>{detail_target}</div>
        <div class="concl-right"><b>【補足：{compare['ブランド品番']}への提案】</b><br>{detail_compare}</div>
    </div>
</div>
<div class="footer">データソース: ZOZO 併売データ ｜ 対象カテゴリ: {target['子商品タイプ']}（{target['性別']}）{category['対象品番数']}品番 ｜ カラー分類: {brand_key_label}</div>
</body>
</html>"""
    return html


def main():
    parser = argparse.ArgumentParser(description='同一品番併売分析 PDF1枚レポート生成')
    parser.add_argument('analysis_json', help='analyze_same_item.py の出力JSONファイルパス')
    parser.add_argument('--out', default='report.pdf', help='出力PDFファイルパス')
    args = parser.parse_args()

    with open(args.analysis_json, 'r', encoding='utf-8') as f:
        data = json.load(f)

    html = build_html(data)
    html_path = args.out.replace('.pdf', '.html')
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"HTML生成完了: {html_path}")

    from weasyprint import HTML
    HTML(html_path).write_pdf(args.out)
    print(f"PDF生成完了: {args.out}")


if __name__ == '__main__':
    main()
