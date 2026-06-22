---
name: zozo-product-dashboard
description: ZOZOの商品別実績Excelから品番ダッシュボード用JSONを生成し、MONO BACK OFFICEで品番別の日次KPI・カテゴリ内順位・トレンド分析を表示するスキル。ダッシュボードデータ更新、品番パフォーマンス分析、カテゴリベンチマーク比較の依頼時に使用する。
---

# ZOZO品番ダッシュボードスキル

商品別実績Excel（ZOZO管理画面からエクスポート）をJSON変換し、MONO BACK OFFICEのダッシュボードページで品番別KPIを表示する。

## ワークフロー

```
1. 商品別実績Excelの準備
2. JSON変換（scripts/convert_dashboard_to_json.py）
3. CDNアップロード（manus-upload-file --webdev）
4. フロントエンド更新（useProductDashboard.ts の DATA_URL）
```

## Step 1: データ準備

商品別実績Excelは `商品別実績 (2)` シートを使用。列構造:

| 列 | 内容 |
|---|---|
| 0 | 日付（YYYY-MM-DD） |
| 2 | ショップ名 |
| 3 | ブランド |
| 4 | サブブランド |
| 5 | 親カテゴリ |
| 6 | 子カテゴリ |
| 7 | 性別（MEN/WOMEN/KIDS） |
| 8 | ブランド品番（キー） |
| 9 | 商品コード |
| 10 | 商品名 |
| 11-29 | 日次メトリクス（注文数、売上、お気に入り、カート追加、在庫、UU、PV、購入者数、性別内訳、新規/既存/復活、平均年齢、平均売価、CVR_UU、CVR_PV、お気に入り率） |

## Step 2: JSON変換

```bash
python3 /home/ubuntu/skills/zozo-product-dashboard/scripts/convert_dashboard_to_json.py
```

**入力**: `/home/ubuntu/dashboard_product_data.xlsx`（シート名: `商品別実績 (2)`）
**出力**: `/home/ubuntu/dashboard_data.json`

スクリプト内のファイルパスを実際のパスに合わせて編集すること。

### 出力JSON構造

```json
{
  "items": {
    "<brandItemCode>": {
      "productName", "brand", "subBrand", "shopName",
      "parentCategory", "childCategory", "gender", "productCode",
      "daily": { "<YYYY-MM-DD>": { "orders", "revenue", "favorites", "cartAdds",
        "stock", "stockWithReserve", "uu", "pv", "buyers",
        "male", "female", "newUsers", "existing", "reactivated",
        "avgAge", "avgPrice", "cvrUU", "cvrPV", "favRate" } }
    }
  },
  "categoryStats": {
    "<childCategory>_<gender>": {
      "childCategory", "gender", "itemCount", "significantCount",
      "avgFavRate", "avgCvrUU", "avgUU", "avgOrders",
      "topFavRate": [...], "topCvrUU": [...],
      "favRankMap": {}, "cvrRankMap": {}
    }
  },
  "meta": { "dateRange", "dates", "totalItems", "brands", "shops" }
}
```

### カテゴリ統計の算出ルール

- UU >= 100 のアイテムのみで平均を計算（ノイズ除去）
- 該当アイテムがない場合は全アイテムで計算
- TOP10はお気に入り率順・CVR_UU順でそれぞれ算出
- ランキングマップ（favRankMap, cvrRankMap）はカテゴリ内全品番の順位

## Step 3: CDNアップロードとフロントエンド更新

```bash
cp /home/ubuntu/dashboard_data.json /home/ubuntu/webdev-static-assets/
manus-upload-file --webdev /home/ubuntu/webdev-static-assets/dashboard_data.json

# useProductDashboard.ts の DATA_URL を新しいCDN URLに変更
```

## フロントエンド表示

ダッシュボードページ（`/dashboard?item=<品番>`）の構成:

| セクション | 内容 |
|---|---|
| KPIカード | 月間お気に入り率・CVR_UU（カテゴリ平均との比較、カテゴリ内順位表示） |
| カテゴリ相対比較 | カテゴリ平均に対する各指標の相対値 |
| 日次メトリクステーブル | 日別の全指標一覧（展開可能な詳細列付き） |
| トレンド分析 | 全期間データを使用したトレンド表示 |

品番検索はヘッダーの「ダッシュボード品番」入力欄から実行。
