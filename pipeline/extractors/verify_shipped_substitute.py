"""
代替「発送」ファイル（売上集計メニュー）の構造検証ツール。

クライアント主張の検証ポイント:
  1) ヘッダーが何行目か (主張: 3行目にデータリスト追加)
  2) 「出荷日」列が存在し、R列(18番目)か (主張: U列発送日 → R列出荷日)
  3) 最低限の商品情報(ブランド品番/CS品番/商品名)＋日付があるか
  4) 現行の発送パーサー(_ORDER_FIELD_MAP)で読める列・読めない列

使い方:
  python verify_shipped_substitute.py "C:\\path\\to\\代替発送ファイル.csv"
"""
from __future__ import annotations
import csv, io, sys
from pathlib import Path

# 現行パーサーが認識する列名 (zozo_csv_extractor._ORDER_FIELD_MAP より)
KNOWN_COLS = {
    "CS品番", "ブランド品番", "カラー", "サイズ", "商品名", "注文数",
    "合計金額（税抜）", "販売価格（税抜）", "注文日", "発送日", "キャンセル",
    "販売タイプ", "価格タイプ", "プロパー価格（税抜）", "親カテゴリ",
    "子カテゴリ", "性別", "会員ID", "ショップ名", "注文番号", "モール",
    "注文時端末", "年齢", "会員性別", "県名",
}

# 最低限ほしい商品情報＋日付
REQUIRED_INFO = ["ブランド品番", "CS品番", "商品名"]
DATE_CANDIDATES = ["出荷日", "発送日", "注文日", "売上日", "日付"]


def col_letter(idx0: int) -> str:
    """0-based index → Excel列文字 (0→A, 17→R, 20→U)。"""
    s = ""
    n = idx0
    while True:
        s = chr(ord("A") + n % 26) + s
        n = n // 26 - 1
        if n < 0:
            break
    return s


def decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp932", "shift_jis", "utf-8"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("cp932", errors="replace")


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python verify_shipped_substitute.py <csv_path>")
        return 2
    path = Path(sys.argv[1])
    if not path.exists():
        print(f"ファイルが見つかりません: {path}")
        return 2

    text = decode(path.read_bytes())
    rows = list(csv.reader(io.StringIO(text)))
    print(f"=== {path.name} ===")
    print(f"総行数: {len(rows)}\n")

    # --- 先頭5行を表示してヘッダー位置を目視確認 ---
    print("--- 先頭5行 (各行の先頭6セル) ---")
    for i, r in enumerate(rows[:5], start=1):
        preview = " | ".join(c[:14] for c in r[:6])
        print(f"  行{i}: [{len(r)}列] {preview}")
    print()

    # --- ヘッダー行の自動推定 (商品情報の語を最も多く含む行) ---
    def score(r: list[str]) -> int:
        joined = "".join(r)
        return sum(1 for kw in ("品番", "商品名", "出荷日", "発送日",
                                "注文", "カラー", "サイズ") if kw in joined)
    header_idx = max(range(min(len(rows), 6)), key=lambda i: score(rows[i]))
    header = rows[header_idx]
    print(f"--- 推定ヘッダー行: 行{header_idx + 1} ({len(header)}列) ---")
    print("検証②: クライアント主張『3行目にヘッダー』 → "
          f"{'✓ 一致' if header_idx == 2 else f'✗ 実際は行{header_idx + 1}'}\n")

    # --- 各列を列文字付きで一覧 ---
    print("--- 全列一覧 (列文字 | 列名 | 現行コードで読める?) ---")
    for i, name in enumerate(header):
        nm = name.strip()
        known = "○読める" if nm in KNOWN_COLS else "×未対応"
        mark = ""
        if nm in ("出荷日", "発送日"):
            mark = "  ← 日付列"
        print(f"  {col_letter(i):>2} | {nm:<20} | {known}{mark}")
    print()

    # --- 検証③: 出荷日の位置 ---
    norm = [c.strip() for c in header]
    if "出荷日" in norm:
        pos = norm.index("出荷日")
        print(f"検証③: 『出荷日』列 → {col_letter(pos)}列 ({pos + 1}番目) "
              f"{'✓ R列で一致' if col_letter(pos) == 'R' else '✗ R列ではない'}")
    elif "発送日" in norm:
        pos = norm.index("発送日")
        print(f"検証③: 『発送日』列あり → {col_letter(pos)}列 (代替不要かも)")
    else:
        print("検証③: 出荷日・発送日 どちらも見つかりません ⚠")

    # --- 検証④: 最低限の商品情報＋日付 ---
    print("\n検証④: 必須項目の有無")
    for col in REQUIRED_INFO:
        print(f"  {'○' if col in norm else '×'} {col}")
    has_date = any(d in norm for d in DATE_CANDIDATES)
    print(f"  {'○' if has_date else '×'} 日付列 "
          f"({', '.join(d for d in DATE_CANDIDATES if d in norm) or 'なし'})")

    # --- 現行コードで完全に欠落する列 ---
    unknown = [c.strip() for c in header if c.strip() and c.strip() not in KNOWN_COLS]
    if unknown:
        print(f"\n⚠ 現行コードが無視する列 ({len(unknown)}): {', '.join(unknown)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
