---
name: mono-fitting
description: MONO FITTING（AI試着体験Webアプリ）のプロジェクト構成・機能仕様・開発手順・API設計を提供するスキル。MONO FITTINGの機能追加、UI修正、バグ修正、カタログ管理、試着フロー改善の依頼時に使用する。
---

# MONO FITTING

AI試着体験Webアプリ。ユーザーの顔写真とMONO-MARTカタログ（または自分の服画像）を組み合わせ、AIが試着イメージを生成する。

## プロジェクト情報

- **プロジェクト名**: shichaku-taiken
- **パス**: `/home/ubuntu/shichaku-taiken`
- **スタック**: React 19 + Tailwind 4 + Express 4 + tRPC 11 + Drizzle ORM + MySQL
- **認証**: Manus OAuth（role: admin / user）
- **デプロイ先**: shichakuxp-8nrdslht.manus.space

## ページ構成

| ルート | ファイル | 概要 |
|--------|----------|------|
| `/` | `Home.tsx` | ランディング。管理者のみ「商品管理」リンク表示 |
| `/tryon` | `TryOn.tsx` | 3ステップ試着フロー（顔写真→服選択→結果） |
| `/snaps` | `Snaps.tsx` | ストック済み画像一覧・スナップ作成 |
| `/admin` | `Admin.tsx` | 管理者専用カタログ商品管理 |

## 試着フロー（TryOn.tsx）

3ステップ構成: `FaceStep` → `OutfitStep` → `ResultsStep`

### FaceStep
1. **select mode**: 「撮影する」（capture=user）or「フォルダから選ぶ」（accept=image/*）。ストック済み顔があればサムネイル一覧表示。初期状態は未選択。
2. **preview mode**: アップロード画像のプレビュー。「AI美化」ボタン（10%スリム・2-3歳若返り）、修正指示テキスト入力、「この顔で確定」ボタン。
3. 顔ストックは最後の1枚も削除可能。削除ボタンは常時表示（hover不要）。

### OutfitStep
2パス選択UI:
- **MONO-MARTを試着する** → `CatalogMode`: DBからカタログ商品一覧をグリッド表示。カテゴリフィルタータブ（「すべて」+ 動的カテゴリ）。商品タップで即座に試着生成。
- **自分のワードローブから** → `WardrobeMode`: 画像アップロード or ZOZO URL入力。アップロード済み服一覧から選択して生成。

### ResultsStep
生成済み画像を一覧表示。各画像に「修正する」「ストック/ストック済（トグル）」「ダウンロード」「削除」ボタン。

## DBスキーマ（drizzle/schema.ts）

| テーブル | 主要フィールド |
|----------|---------------|
| `users` | id, openId, name, role(admin/user) |
| `facePhotos` | userId, originalUrl, currentUrl, isConfirmed, faceType(original/ai_generated) |
| `outfitImages` | userId, imageUrl, fileName |
| `generatedImages` | userId, facePhotoId, outfitImageId, generatedUrl, prompt, status |
| `stockedImages` | userId, imageUrl, sourceType(face/generated), sourceId |
| `snaps` | userId, title, imageUrl, imageIds(JSON) |
| `catalogProducts` | name, imageUrl, category, brand, sortOrder, isActive |

## tRPC API（server/routers.ts）

| ルーター | プロシージャ | 概要 |
|----------|-------------|------|
| `face` | upload, refine, aiEnhance, confirm, getConfirmed, getLatest, list, delete | 顔写真CRUD・AI美化 |
| `outfit` | upload, list, delete | 服画像CRUD |
| `generate` | create, refine, list, delete | 試着画像生成・修正・削除 |
| `stock` | add, list, remove | ストック追加/解除 |
| `snap` | create, list, delete | スナップ作成 |
| `catalog` | list, add, delete, update | カタログ商品管理（admin） |
| `zozo` | fetchImage | ZOZO URLからOGP画像取得 |

## AI生成ロジック（generate.create）

1. LLM Visionで服画像を分析 → CLOTHING/POSE/EXPRESSION をテキスト抽出
2. 顔写真のみを参照画像として `generateImage` に渡す（服画像は渡さない＝モデルの顔コピー防止）
3. テキストプロンプトで服装・ポーズ・表情を指示

## カタログ管理（/admin）

管理者（role=admin）のみアクセス可。機能:
- 商品追加（画像アップロード + 商品名 + カテゴリ）
- 商品削除・編集（名前・カテゴリ）
- 並び順変更（sortOrder上下）
- 表示/非表示切り替え（isActive）

## 開発手順

1. スキーマ変更 → `drizzle/schema.ts` 編集 → `pnpm drizzle-kit generate` → SQL適用
2. DBヘルパー追加 → `server/db.ts`
3. tRPCプロシージャ追加 → `server/routers.ts`
4. フロントエンド → `client/src/pages/` で `trpc.*.useQuery/useMutation`
5. テスト → `server/tryon.test.ts`（vitest）
6. 画像アセット → `manus-upload-file --webdev` でCDN URL取得

## デザイン方針

- Googleのようなシンプル・ミニマルデザイン
- ライトテーマ、白背景ベース
- フォント: Inter + Noto Sans JP
- shadcn/ui コンポーネント使用
- モバイルファースト設計
