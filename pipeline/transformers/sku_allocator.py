"""
SKU Balance Allocator — 繰り返し発注 (Repeat Order) SKU Quantity Distribution

Given a total order quantity for a product, distributes it across colors and sizes
using the method described in the MONO BACK OFFICE skill documentation:

    allocation_qty = (total_order_qty
                      × 直近30日構成比           # share of sales in last 30 days
                      × 在庫日数調整係数)        # inventory-day adjustment factor

在庫日数調整係数 (inventory day adjustment factor):
    stock_days == 0  →  × 1.5   (stockout, boost allocation)
    0 < stock_days ≤ 30  → × 1.0  (normal)
    30 < stock_days ≤ 60 → × 0.9  (slight excess)
    stock_days > 60  →  × 0.7   (overstock, reduce allocation)

The allocations are normalised so they sum to total_order_qty.

Usage:
    from pipeline.transformers.sku_allocator import allocate_sku_order

    skus = [
        {"sku_code": "A1", "color_code": "IVORY", "size": "S",
         "sales_30d": 57, "stock_days_7d": 25},
        ...
    ]
    result = allocate_sku_order("ABC1234", total_order_qty=500, skus=skus)
    for r in result:
        print(r["sku_code"], r["allocated_qty"])
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


# ── Constants ─────────────────────────────────────────────────────────────────

STOCK_DAY_COEFFICIENTS = [
    (0,    0,   1.5),   # stock_days == 0  (stockout)
    (0,    30,  1.0),   # 0  < days ≤ 30  (normal)
    (30,   60,  0.9),   # 30 < days ≤ 60  (mild excess)
    (60,   None, 0.7),  # days > 60        (overstock)
]


# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class SkuAllocation:
    sku_code:          str
    product_code:      str
    color_code:        str
    color_name:        str
    size:              str
    sales_30d:         int
    stock_days_7d:     float | None
    sales_share_30d:   float   # 直近30日構成比 (0.0–1.0)
    adj_coefficient:   float   # 在庫日数調整係数
    raw_qty:           float   # before normalisation & rounding
    allocated_qty:     int     # final allocation (integer)
    free_inventory:    int
    recommended_by_rule: int   # cross-check: our recommendation


@dataclass
class AllocationResult:
    product_code:  str
    total_order_qty: int
    total_sales_30d: int
    skus:          list[SkuAllocation] = field(default_factory=list)

    @property
    def allocated_total(self) -> int:
        return sum(s.allocated_qty for s in self.skus)

    @property
    def residual(self) -> int:
        """Rounding residual (should be 0 or ±1)."""
        return self.total_order_qty - self.allocated_total


# ── Core logic ────────────────────────────────────────────────────────────────

def _stock_day_coeff(stock_days: float | None) -> float:
    """Return the 在庫日数調整係数 for a given stock_days value."""
    if stock_days is None:
        return 1.0  # no velocity data → treat as normal
    for lo, hi, coeff in STOCK_DAY_COEFFICIENTS:
        if stock_days <= lo:         # exact == 0 case
            return coeff
        if hi is None or stock_days <= hi:
            return coeff
    return 0.7  # fallback: overstock


def allocate_sku_order(
    product_code: str,
    total_order_qty: int,
    skus: list[dict[str, Any]],
) -> AllocationResult:
    """
    Distribute total_order_qty across SKUs proportionally.

    Args:
        product_code:    The product to allocate for.
        total_order_qty: Total pieces to order across all SKUs.
        skus:            List of dicts, each must have:
                           sku_code, color_code, color_name, size,
                           sales_30d, stock_days_7d, free_inventory

    Returns:
        AllocationResult with one SkuAllocation per SKU.
    """
    if total_order_qty <= 0:
        return AllocationResult(
            product_code=product_code,
            total_order_qty=0,
            total_sales_30d=0,
            skus=[
                SkuAllocation(
                    sku_code=s.get("sku_code", ""),
                    product_code=product_code,
                    color_code=s.get("color_code", ""),
                    color_name=s.get("color_name", ""),
                    size=s.get("size", ""),
                    sales_30d=s.get("sales_30d", 0),
                    stock_days_7d=s.get("stock_days_7d"),
                    sales_share_30d=0,
                    adj_coefficient=1.0,
                    raw_qty=0,
                    allocated_qty=0,
                    free_inventory=s.get("free_inventory", 0),
                    recommended_by_rule=0,
                )
                for s in skus
            ],
        )

    total_sales_30d = sum(max(s.get("sales_30d", 0), 0) for s in skus)

    # Step 1: Calculate weighted share for each SKU
    # weight = sales_30d × adj_coefficient
    weights: list[float] = []
    for s in skus:
        sales  = max(s.get("sales_30d", 0), 0)
        days   = s.get("stock_days_7d")
        coeff  = _stock_day_coeff(days)
        weights.append(sales * coeff)

    total_weight = sum(weights)

    # Step 2: Raw allocation
    raw_allocs: list[float] = []
    if total_weight > 0:
        for w in weights:
            raw_allocs.append(total_order_qty * (w / total_weight))
    else:
        # Fallback: equal distribution
        per_sku = total_order_qty / len(skus)
        raw_allocs = [per_sku] * len(skus)

    # Step 3: Round-half-up and correct rounding residual
    int_allocs = [math.floor(r) for r in raw_allocs]
    remainders = [(raw_allocs[i] - int_allocs[i], i) for i in range(len(raw_allocs))]
    residual   = total_order_qty - sum(int_allocs)
    # Distribute residual to SKUs with highest fractional part
    remainders.sort(key=lambda x: -x[0])
    for j in range(residual):
        int_allocs[remainders[j][1]] += 1

    # Step 4: Build result
    alloc_skus: list[SkuAllocation] = []
    for i, s in enumerate(skus):
        sales_30d   = max(s.get("sales_30d", 0), 0)
        stock_days  = s.get("stock_days_7d")
        free_inv    = s.get("free_inventory", 0)
        coeff       = _stock_day_coeff(stock_days)
        share       = weights[i] / total_weight if total_weight > 0 else 1 / len(skus)

        # Cross-check with our recommendation formula (8-week coverage)
        vel_30d = sales_30d / 30
        trend   = s.get("trend_coefficient", 1.0) or 1.0
        trend   = min(2.0, max(0.5, trend))
        rec     = max(0, math.ceil(
            8 * 7 * vel_30d * trend - free_inv - s.get("incoming_stock", 0)
        ))

        alloc_skus.append(SkuAllocation(
            sku_code          = s.get("sku_code", ""),
            product_code      = product_code,
            color_code        = s.get("color_code", ""),
            color_name        = s.get("color_name", ""),
            size              = s.get("size", ""),
            sales_30d         = sales_30d,
            stock_days_7d     = stock_days,
            sales_share_30d   = round(share, 4),
            adj_coefficient   = coeff,
            raw_qty           = round(raw_allocs[i], 2),
            allocated_qty     = int_allocs[i],
            free_inventory    = free_inv,
            recommended_by_rule = rec,
        ))

    return AllocationResult(
        product_code    = product_code,
        total_order_qty = total_order_qty,
        total_sales_30d = total_sales_30d,
        skus            = alloc_skus,
    )


# ── Convenience: allocate from BigQuery order_analysis rows ──────────────────

def allocate_from_analysis_rows(
    rows: list[dict[str, Any]],
    total_qty_per_product: dict[str, int],
) -> dict[str, AllocationResult]:
    """
    Batch allocation for multiple products.

    Args:
        rows:                   All order_analysis rows (multiple products/SKUs)
        total_qty_per_product:  {product_code: total_order_qty}

    Returns:
        {product_code: AllocationResult}
    """
    # Group rows by product_code
    by_product: dict[str, list[dict]] = {}
    for row in rows:
        pc = row.get("product_code", "")
        by_product.setdefault(pc, []).append(row)

    results: dict[str, AllocationResult] = {}
    for product_code, product_rows in by_product.items():
        total_qty = total_qty_per_product.get(product_code, 0)
        results[product_code] = allocate_sku_order(
            product_code=product_code,
            total_order_qty=total_qty,
            skus=product_rows,
        )

    return results


# ── Format helpers ────────────────────────────────────────────────────────────

def allocation_to_dict(alloc: SkuAllocation) -> dict[str, Any]:
    return {
        "sku_code":          alloc.sku_code,
        "product_code":      alloc.product_code,
        "color_code":        alloc.color_code,
        "color_name":        alloc.color_name,
        "size":              alloc.size,
        "sales_30d":         alloc.sales_30d,
        "stock_days_7d":     alloc.stock_days_7d,
        "sales_share_30d":   alloc.sales_share_30d,
        "adj_coefficient":   alloc.adj_coefficient,
        "allocated_qty":     alloc.allocated_qty,
        "recommended_qty":   alloc.recommended_by_rule,
        "free_inventory":    alloc.free_inventory,
    }


def result_to_dict(result: AllocationResult) -> dict[str, Any]:
    return {
        "product_code":    result.product_code,
        "total_order_qty": result.total_order_qty,
        "total_sales_30d": result.total_sales_30d,
        "allocated_total": result.allocated_total,
        "residual":        result.residual,
        "skus":            [allocation_to_dict(s) for s in result.skus],
    }


# ── CLI test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    # Example matching PDF data: ABC1234 with Ivory/Black/LightGray/Gray × S/M/L
    test_skus = [
        {"sku_code":"I1","color_code":"IVORY","color_name":"アイボリー","size":"S",
         "sales_30d":57, "stock_days_7d":None,"free_inventory":108,"trend_coefficient":1.2},
        {"sku_code":"I2","color_code":"IVORY","color_name":"アイボリー","size":"M",
         "sales_30d":41, "stock_days_7d":50, "free_inventory":184,"trend_coefficient":0.9},
        {"sku_code":"I3","color_code":"IVORY","color_name":"アイボリー","size":"L",
         "sales_30d":20, "stock_days_7d":70, "free_inventory":120,"trend_coefficient":0.8},
        {"sku_code":"B1","color_code":"BLACK","color_name":"ブラック","size":"S",
         "sales_30d":240,"stock_days_7d":2,  "free_inventory":268,"trend_coefficient":1.5},
        {"sku_code":"B2","color_code":"BLACK","color_name":"ブラック","size":"M",
         "sales_30d":224,"stock_days_7d":3,  "free_inventory":462,"trend_coefficient":1.4},
        {"sku_code":"B3","color_code":"BLACK","color_name":"ブラック","size":"L",
         "sales_30d":157,"stock_days_7d":4,  "free_inventory":297,"trend_coefficient":1.3},
        {"sku_code":"G1","color_code":"LGRAY","color_name":"ライトグレー","size":"S",
         "sales_30d":196,"stock_days_7d":0,  "free_inventory":54, "trend_coefficient":1.8},
        {"sku_code":"G2","color_code":"LGRAY","color_name":"ライトグレー","size":"M",
         "sales_30d":220,"stock_days_7d":1,  "free_inventory":164,"trend_coefficient":1.7},
        {"sku_code":"G3","color_code":"LGRAY","color_name":"ライトグレー","size":"L",
         "sales_30d":98, "stock_days_7d":14, "free_inventory":135,"trend_coefficient":1.1},
    ]

    result = allocate_sku_order("ABC1234", total_order_qty=1000, skus=test_skus)
    print(f"Product: {result.product_code}")
    print(f"Total order: {result.total_order_qty}  Allocated: {result.allocated_total}  Residual: {result.residual}")
    print()
    print(f"{'SKU':<6} {'Color':<12} {'Size':<4} {'30d':<5} {'StockDays':<10} {'Coeff':<6} {'Share%':<8} {'Alloc':<6} {'Rec':<5}")
    print("-" * 80)
    for s in result.skus:
        print(
            f"{s.sku_code:<6} {s.color_name:<12} {s.size:<4} "
            f"{s.sales_30d:<5} {s.stock_days_7d!s:<10} "
            f"{s.adj_coefficient:<6.1f} {s.sales_share_30d*100:<8.1f} "
            f"{s.allocated_qty:<6} {s.recommended_by_rule:<5}"
        )
