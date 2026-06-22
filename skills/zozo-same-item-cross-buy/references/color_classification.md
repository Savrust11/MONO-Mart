# カラー分類ルール

ZOZO併売データの「カラー」列を **メインカラー・シーズンカラー・アクセントカラー** の3分類に振り分ける。
分類は **ブランドごと（MONO-MARTはテイスト別）** に定義されたカラーパレットに基づく。

## 分類の定義

| 分類 | 説明 |
|---|---|
| メインカラー | 定番色。無彩色・モノトーン系が中心で、どの色とも合わせやすく併売の軸になる色群 |
| シーズンカラー | 季節感のある中間色。メインカラーとの組み合わせが多い |
| アクセントカラー | 鮮やかな色や個性的な色。上記いずれにも該当しない色はすべてアクセントカラーに分類 |

## ブランド別カラーパレット

カラーパレットの具体的な定義は `references/brand_color_palettes.json` に格納。
ブランドキー一覧:

| ブランドキー | ブランド名 | 備考 |
|---|---|---|
| `MONO-MART_CASUAL_M1` | MONO-MART CASUAL(M1) NEW | メンズカジュアル |
| `MONO-MART_CASUAL_F1` | MONO-MART CASUAL(F1) | レディースカジュアル |
| `MONO-MART_CASUAL_F1.5` | MONO-MART CASUAL(F1.5) | レディースカジュアル上位 |
| `MONO-MART_CODDERR` | MONO-MART CODDERR New | カジュアル(M1) |
| `MONO-MART_MINIMAL_M1` | MONO-MART ミニマル(M1) | メンズミニマル |
| `MONO-MART_MINIMAL_M1.5` | MONO-MART ミニマル(M1.5) | メンズミニマル上位 |
| `MONO-MART_MINIMAL_F1.5` | MONO-MART ミニマル(F1.5) | レディースミニマル |
| `EASENCE` | EASENCE New | |
| `Aunely` | Aunely | |
| `HECT` | HECT NEW | |
| `TCCP_MEN` | TCCP MEN | |
| `TCCP_WOMEN` | TCCP WOMEN | |
| `Alfred_Alex` | Alfred Alex (NEW) | |
| `forksy` | forksy. | |
| `Unblend` | Unblend (NEW) | |
| `EMMA_CLOTHES` | EMMA CLOTHES | |
| `Anchor_Smith` | Anchor Smith (NEW) | |
| `Snap_club` | Snap club (NEW) | |
| `CIYOT` | CIYOT (NEW) | |

## 判定ロジック（Python）

```python
import json, os

_PALETTES = None

def _load_palettes():
    global _PALETTES
    if _PALETTES is None:
        p = os.path.join(os.path.dirname(__file__),
                         '..', 'references', 'brand_color_palettes.json')
        with open(p, encoding='utf-8') as f:
            _PALETTES = json.load(f)
    return _PALETTES

def classify_color(color_name: str, brand_key: str = None) -> str:
    """ブランド別カラーパレットに基づいてカラーを分類する。
    brand_key が None またはパレットに存在しない場合はフォールバック判定を使用。
    """
    palettes = _load_palettes()
    palette = palettes.get(brand_key) if brand_key else None

    if palette:
        cn = color_name.strip()
        if any(kw in cn for kw in palette['main']):
            return 'メインカラー'
        elif any(kw in cn for kw in palette['season']):
            return 'シーズンカラー'
        else:
            return 'アクセントカラー'

    # フォールバック: ブランド指定なしの場合は汎用判定
    return _classify_fallback(color_name)

def _classify_fallback(color_name: str) -> str:
    MAIN_KW = ['ブラック','ホワイト','オフホワイト','スミクロ','ライトグレー',
               'グレー','チャコール','ダークグレー','アイボリー','グレージュ',
               'アッシュグレー','オートミール','スノーホワイト']
    SEASON_KW = ['ネイビー','ブラウン','モカ','ベージュ','カーキ','オリーブ',
                 'キャメル','ダークブラウン','ライトベージュ','トープ',
                 'コーヒーブラウン','ミッドナイトブルー','ダークネイビー']
    cn = color_name.strip()
    if any(kw in cn for kw in MAIN_KW):
        return 'メインカラー'
    elif any(kw in cn for kw in SEASON_KW):
        return 'シーズンカラー'
    else:
        return 'アクセントカラー'
```

## 運用上の注意

- 新ブランド追加時は `brand_color_palettes.json` にエントリを追加する
- 併売データCSVのブランド名から `brand_key` へのマッピングは分析スクリプト内で行う
- ブランドが特定できない場合はフォールバック判定（汎用キーワードベース）を使用する
- 「トレンドカラー」はスプレッドシート上のログ用であり、分類定義には含めない
