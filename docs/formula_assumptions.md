# Business Logic Formula Assumptions

> **Status**: Needs verification with client before production go-live.
> These formulas were reverse-engineered from the sample PDF (分析表イメージ.pdf).
> The PDF image resolution was low — exact formula semantics must be confirmed.

---

## 1. フリー在庫 (Free Inventory)

### Current implementation
```
free_inventory = inventory - reserved_quantity - reservations_pending
```

Where:
- `inventory` = 在庫 (total warehouse stock from ZOZO)
- `reserved_quantity` = 引当済み数 (ZOZO-side allocation to confirmed orders)
- `reservations_pending` = 予約未処理数 (Google Sheets pending reservations not yet in ZOZO)

### From PDF sample data
| SKU | 在庫 | フリー在庫 | 予約未処理 | Difference |
|-----|------|-----------|-----------|-----------|
| Ivory/S | 108 | -148 | 0 | -256 |
| Black/S | 268 | -476 | 0 | -744 |
| Gray/S  | 606 | 134  | 0 | +472 |

⚠️ **Discrepancy**: In the PDF sample, 予約未処理数=0 for all rows, yet フリー在庫 ≠ 在庫.
This suggests フリー在庫 in the original Excel incorporates additional logic not visible in the PDF.

**Possible explanations (verify with client):**
1. A "committed to production orders" column that the PDF doesn't show separately
2. フリー在庫 = 在庫 - 発注数(lot reference) where the 発注数 column is the production lot total
3. There is a hidden "引当" column that the PDF rendering collapsed

**Action required**: Access the actual Excel file to see the formula bar for the フリー在庫 column.

---

## 2. 発注数 Column (PDF column 6)

### From PDF sample data
| SKU | 在庫 | 発注数 |
|-----|------|--------|
| Ivory/S | 108 | 408 |
| Ivory/M | 184 | 384 |
| Black/S | 268 | 1568 |
| Gray/S  | 606 | **606** |
| Gray/M  | 936 | **936** |

**Observation**: For Gray color SKUs, 発注数 = 在庫 exactly. This pattern is consistent for all 3 Gray sizes.

**Most likely interpretation**: 発注数 = **total production lot quantity ordered** (not remaining order quantity).
- For Gray: No pending incoming stock → 発注数 = 在庫 (all produced units are in warehouse)
- For Ivory/Black: Difference (408-108=300 for Ivory/S) = 入荷残 (units still in transit)

**Our system handles this as**: `production_lot_size` in cost_master — a reference column only.
The system computes its own `recommended_order_qty` independently.

---

## 3. 7日間分 (Stock Days at 7-Day Velocity)

### Current implementation
```
stock_days_7d = free_inventory / daily_velocity_7d
             = free_inventory / (sales_7d / 7)
```

### From PDF sample data
| SKU | フリー在庫 | 7日間 | Expected days | PDF shows |
|-----|-----------|-------|---------------|-----------|
| Ivory/S | -148 | 32 | -32.4 | -6 |
| Black/S | -476 | 93 | -35.8 | -212 |
| Gray/S  | 134  | 59 | +15.9 | 340 |

⚠️ **Significant discrepancy**: Our formula doesn't match the PDF values.

**Alternative hypotheses:**
1. 7日間分 = free_inventory - (sales in next 7 days based on forecast)
2. 7日間分 = monthly_gap scaled differently
3. Different field ordering in the PDF — what we think is "7日間分" might be another metric

**Note**: Despite the discrepancy in absolute values, the **sign** is consistent:
- Negative in PDF → negative in our calc → stockout signal
- Positive in PDF → positive in our calc → surplus signal

Our urgency classification (`CRITICAL`/`WARNING`/`OK`/`OVERSTOCK`) is derived from `stock_days_7d`
and is directionally correct even if the magnitude needs calibration.

**Action required**: View formula bar in Excel for the 7日間分 column.

---

## 4. 1ヶ月差分 (Monthly Gap)

### Current implementation
```
monthly_gap = free_inventory - sales_30d
```

### From PDF sample data
All rows show `1ヶ月差分 = 0` — but this is suspicious as free_inventory ≠ sales_30d for any row.

**Most likely**: The `0` values in the PDF for this column are due to PDF rendering — the column
might show zeros for a different reason (perhaps it's a conditional column only shown for reorder items,
or those zeros represent something else).

**Action required**: Verify which column is actually "1ヶ月差分" in the Excel.

---

## 5. 推奨発注数 (Recommended Order Quantity)

### Current implementation
```
recommended_order_qty = MAX(0, CEIL(
  coverage_weeks × 7 × daily_velocity_30d × trend_coefficient
  - free_inventory
  - incoming_stock
))
```

Default: `coverage_weeks = 8` (8 weeks = 56 days of coverage target)

**Configurable parameters** (adjust via environment variables or config table in BigQuery):
- `TARGET_COVERAGE_WEEKS` (default: 8)
- `TREND_COEFF_MIN` (default: 0.5) — prevents over-ordering on declining items
- `TREND_COEFF_MAX` (default: 2.0) — prevents extreme over-ordering on viral items

**Example** (Ivory/S from PDF, using our formula):
- daily_velocity_30d = 57/30 = 1.9 units/day
- trend_coefficient = (32/7) / (57/30) = 4.57 / 1.9 = 2.4 → clamped to 2.0
- target_stock = 56 × 1.9 × 2.0 = 212.8 ≈ 213 units
- recommended = MAX(0, 213 - (-148) - 0) = 361 units

This is a reasonable reorder recommendation. Adjust `coverage_weeks` to calibrate.

---

## 6. トレンド係数 (Trend Coefficient)

### Current implementation
```
trend_coefficient = daily_velocity_7d / daily_velocity_30d
                  = (sales_7d / 7) / (sales_30d / 30)
                  CLAMPED to [0.5, 2.0]
```

**Interpretation**:
- `> 1.0`: Sales accelerating recently (order more)
- `< 1.0`: Sales decelerating (order less)
- `= 1.0`: Stable trend

**From PDF**: Ivory/S has trend = (32/7)/(57/30) ≈ 2.4 (clamped to 2.0) — strong upward trend.
This makes sense for a popular color near its selling peak.

---

## 7. 緊急度 Classification

```
CRITICAL  = stock_days_7d ≤ 0    (stockout now — free_inventory negative)
WARNING   = stock_days_7d ≤ 14   (less than 2 weeks of stock)
OVERSTOCK = stock_days_7d > 90   (more than 3 months of stock)
OK        = everything else
```

Thresholds are configurable via environment variables.

---

## Items to Confirm with Client (Priority Order)

1. **Access the actual Excel file** — view formula bar for フリー在庫, 7日間分, 発注数 columns
2. **Confirm 発注数 column meaning** — production lot reference vs computed recommendation
3. **Confirm target coverage weeks** — currently defaulting to 8 weeks
4. **Confirm ZOZO API field names** — adjust `zozo_extractor.py` `_normalize_*` methods
5. **Confirm Sheets tab name and column layout** — adjust `COLUMN_MAP` in `sheets_extractor.py`
6. **Confirm cost Excel column headers** — adjust `COST_COLUMN_MAP` in `excel_extractor.py`
