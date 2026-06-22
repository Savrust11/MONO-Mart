---
name: zozo-affinity-analysis
description: ZOZO内の買い回りデータ（ブランド別Excelシート）とショップ指標データ（月次Excel）を組み合わせて、各ブランドと相性の良い他社ショップを母数補正済みの相性スコアで特定・ランキングする分析スキル。株式会社MONO-MARTの自社ブランド（MONO-MART, EMMA CLOTHES, CLEL, ADRER等）の買い回り分析依頼に使用する。
---

# ZOZO 買い回り相性分析スキル

## 概要

2種類のデータを組み合わせて「真の相性スコア」を算出する。

- **買い回りデータ**：ブランドごとのシートに分かれた月次Excel。同月内に自社ブランドと他社ショップの両方で購入したユーザーの実績。
- **ショップ指標データ**：ZOZOTOWNの全ショップの売上・購入者数・客単価等の月次Excel（Sheet1）。

**相性スコア（%）＝ 買い回り件数 ÷ ショップの購入者数 × 100**

Classical Elfのように「買い回り件数が多いが購入者数も多い」ショップはスコアが希薄化され、規模に関わらず真に相性の良いショップが浮かび上がる。

## ワークフロー

```
1. データ受け取り・確認
2. build_combined.py で中間CSV生成
3. affinity_score.py で相性スコア算出・Excel出力
4. 結果報告
```

## Step 1: データ受け取り時の確認事項

- 買い回りデータのシート名（＝ブランド名一覧）
- ショップ指標データの対象月（ファイル名から判断）
- 分析対象ブランドの指定があるか（なければ全ブランド）

## Step 2: build_combined.py の実行

```bash
python /home/ubuntu/skills/zozo-affinity-analysis/scripts/build_combined.py \
  --buyback <買い回りデータ.xlsx> \
  --shop_files <26年1月.xlsx> [<26年2月.xlsx> ...] \
  --output_dir <出力ディレクトリ>
```

生成される中間ファイル：
- `merged_all.csv`：全ブランド×全ショップの結合データ
- `merged_other.csv`：自社ショップを除いた他社のみ
- `shop_master_<月>.csv`：月別ショップ指標

**ショップ指標Excelの読み込み注意点**：
- ヘッダーが2行目にある → `header=None` で読み込み、行0をカラム名として使用
- カラムマッピングは `references/data_schema.md` を参照

## Step 3: affinity_score.py の実行

```bash
python /home/ubuntu/skills/zozo-affinity-analysis/scripts/affinity_score.py \
  --merged_other <merged_other.csv> \
  --output <相性分析レポート.xlsx> \
  --min_buyback 30 \
  --min_buyers 100
```

フィルタ条件（デフォルト）：
- `min_buyback 30`：最低買い回り件数 → 信頼性確保
- `min_buyers 100`：ショップ最低購入者数 → 母数確保

出力Excelのシート構成：
- `★複数ブランド相性良TOP30`：3ブランド以上と相性が良いショップ
- `全ブランド横断TOP50`：全ブランド平均スコアTOP50
- 各ブランド名シート：ブランド別相性スコア上位20ショップ

## Step 4: 結果報告のポイント

1. **相性スコアの読み方**：単純な買い回り件数との違いを説明する
2. **規模×相性のバランス**：スコアが高く買い回り件数も多いショップを特に強調する
3. **複数ブランドと相性が良いショップ**：自社全体のターゲット顧客が集まる場所として注目
4. **成長中のショップ**：売上昨対比が高いショップは今後の相性強化が期待できる

## 自社ブランド除外リスト

買い回り先から自社ショップを除外する際に使用する（ブランド追加時はユーザーに確認）：

```python
OWN_BRANDS = [
    'MONO-MART', 'EMMA CLOTHES', 'WYM LIDNM', 'THE CRAFT CREW',
    'Alfred Alex', 'Anchor Smith', 'ADRER', 'CLEL', 'LOOSE', 'cussil',
    'GRANCY', 'SERACE', 'LUENNA', 'RUUBON', 'forksy.', "MONO-MART LADY'S",
    'BONLECILL', 'Heart Tattoo', 'ELUNIS', 'Elishe', 'Parts Lab.', 'Aunely'
]
```

## データスキーマ

詳細は `references/data_schema.md` を参照。
