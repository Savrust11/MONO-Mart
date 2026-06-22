"""
Local demo server — no dependencies, pure Python stdlib.
Serves mock 分析表 data and the dashboard HTML.

Run:  python local_demo/server.py
Open: http://localhost:8888
"""
import json
import math
import os
import random
import sys
import uuid
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

# ── Mock data generation ─────────────────────────────────────────────────────
# Based on the actual 分析表イメージ.pdf sample data + extended with more products

PRODUCTS = [
    {"product_code": "ABC1234", "product_name": "スラックスパンツ"},
    {"product_code": "DEF5678", "product_name": "テーパードパンツ"},
    {"product_code": "GHI9012", "product_name": "ワイドレッグパンツ"},
]

COLORS = {
    "ABC1234": [
        {"color_code": "IVORY",  "color_name": "アイボリー",   "maker_color_code": "ｱｲﾎﾞﾘｰ"},
        {"color_code": "BLACK",  "color_name": "ブラック",     "maker_color_code": "ﾌﾞﾗｯｸ"},
        {"color_code": "LGRAY",  "color_name": "ライトグレー", "maker_color_code": "ﾗｲﾄｸﾞﾚｰ"},
        {"color_code": "GRAY",   "color_name": "グレー",       "maker_color_code": "ｸﾞﾚｰ"},
    ],
    "DEF5678": [
        {"color_code": "BEIGE",  "color_name": "ベージュ",     "maker_color_code": "ﾍﾞｰｼﾞｭ"},
        {"color_code": "NAVY",   "color_name": "ネイビー",     "maker_color_code": "ﾈｲﾋﾞｰ"},
        {"color_code": "KHAKI",  "color_name": "カーキ",       "maker_color_code": "ｶｰｷ"},
    ],
    "GHI9012": [
        {"color_code": "WHITE",  "color_name": "ホワイト",     "maker_color_code": "ﾎﾜｲﾄ"},
        {"color_code": "BLACK",  "color_name": "ブラック",     "maker_color_code": "ﾌﾞﾗｯｸ"},
        {"color_code": "BROWN",  "color_name": "ブラウン",     "maker_color_code": "ﾌﾞﾗｳﾝ"},
    ],
}

SIZES = ["S", "M", "L"]

# Real values from PDF for ABC1234
REAL_PDF_DATA = {
    ("ABC1234", "IVORY",  "S"): {"inventory": 108,  "sales_7d": 32,  "sales_30d": 57,  "incoming": 0,  "favorites": 205},
    ("ABC1234", "IVORY",  "M"): {"inventory": 184,  "sales_7d": 16,  "sales_30d": 41,  "incoming": 0,  "favorites": 164},
    ("ABC1234", "IVORY",  "L"): {"inventory": 120,  "sales_7d": 8,   "sales_30d": 20,  "incoming": 0,  "favorites": 80},
    ("ABC1234", "BLACK",  "S"): {"inventory": 268,  "sales_7d": 93,  "sales_30d": 240, "incoming": 0,  "favorites": 491},
    ("ABC1234", "BLACK",  "M"): {"inventory": 462,  "sales_7d": 90,  "sales_30d": 224, "incoming": 0,  "favorites": 523},
    ("ABC1234", "BLACK",  "L"): {"inventory": 297,  "sales_7d": 73,  "sales_30d": 157, "incoming": 0,  "favorites": 270},
    ("ABC1234", "LGRAY",  "S"): {"inventory": 54,   "sales_7d": 62,  "sales_30d": 196, "incoming": 0,  "favorites": 597},
    ("ABC1234", "LGRAY",  "M"): {"inventory": 164,  "sales_7d": 105, "sales_30d": 220, "incoming": 0,  "favorites": 579},
    ("ABC1234", "LGRAY",  "L"): {"inventory": 135,  "sales_7d": 38,  "sales_30d": 98,  "incoming": 0,  "favorites": 255},
    ("ABC1234", "GRAY",   "S"): {"inventory": 606,  "sales_7d": 59,  "sales_30d": 133, "incoming": 0,  "favorites": 284},
    ("ABC1234", "GRAY",   "M"): {"inventory": 936,  "sales_7d": 56,  "sales_30d": 135, "incoming": 0,  "favorites": 305},
    ("ABC1234", "GRAY",   "L"): {"inventory": 601,  "sales_7d": 22,  "sales_30d": 53,  "incoming": 0,  "favorites": 139},
}


def _classify_urgency(stock_days):
    if stock_days is None:
        return "OK"
    if stock_days <= 0:
        return "CRITICAL"
    if stock_days <= 14:
        return "WARNING"
    if stock_days >= 90:
        return "OVERSTOCK"
    return "OK"


def _gen_daily_sales(sales_30d, n=30):
    if sales_30d == 0:
        return [{"sale_date": str(date.today() - timedelta(days=i)), "qty": 0} for i in range(n)]
    avg = sales_30d / 30
    result = []
    for i in range(n):
        d = date.today() - timedelta(days=i)
        qty = max(0, int(avg * random.uniform(0.3, 1.8)))
        result.append({"sale_date": str(d), "qty": qty})
    return result


def generate_rows(target_date_str=None):
    if target_date_str is None:
        target_date_str = str(date.today())

    random.seed(42)  # deterministic for demo
    rows = []

    for prod in PRODUCTS:
        pc = prod["product_code"]
        pn = prod["product_name"]
        size_idx = {"S": 1, "M": 2, "L": 3}

        for color in COLORS[pc]:
            cc = color["color_code"]
            for sz in SIZES:
                sku_code = f"{cc[0]}{size_idx[sz]}"

                # Use real PDF data if available, else generate
                key = (pc, cc, sz)
                if key in REAL_PDF_DATA:
                    d = REAL_PDF_DATA[key]
                    inventory    = d["inventory"]
                    sales_7d     = d["sales_7d"]
                    sales_30d    = d["sales_30d"]
                    incoming     = d["incoming"]
                    favorites    = d["favorites"]
                    reserved_qty = 0
                    reservations_pending = 0
                else:
                    base = {"S": 100, "M": 200, "L": 80}[sz]
                    inventory    = random.randint(0, base * 4)
                    sales_7d     = random.randint(0, 80)
                    sales_30d    = random.randint(sales_7d, sales_7d * 5)
                    incoming     = random.choice([0, 0, 0, 50, 100, 200])
                    favorites    = random.randint(50, 500)
                    reserved_qty = 0
                    reservations_pending = random.choice([0, 0, 0, 5, 10])

                free_inv   = inventory - reserved_qty - reservations_pending
                vel_7d     = sales_7d / 7 if sales_7d else 0
                vel_30d    = sales_30d / 30 if sales_30d else 0
                stock_days = (free_inv / vel_7d) if vel_7d > 0 else (999 if free_inv > 0 else None)
                trend      = min(2.0, max(0.5, vel_7d / vel_30d)) if vel_30d > 0 else 1.0
                monthly_gap = free_inv - sales_30d
                urgency    = _classify_urgency(stock_days)

                # Recommended order
                if vel_30d > 0:
                    target = 8 * 7 * vel_30d * trend
                    rec_qty = max(0, math.ceil(target - free_inv - incoming))
                else:
                    rec_qty = 0

                # Cost (mock)
                cost_price   = random.choice([3500, 4800, 6200, 7500])
                retail_price = cost_price * random.uniform(2.2, 2.8)
                margin = (retail_price - cost_price) / retail_price

                rows.append({
                    "analysis_date":      target_date_str,
                    "product_code":       pc,
                    "product_name":       pn,
                    "color_code":         cc,
                    "color_name":         color["color_name"],
                    "size":               sz,
                    "sku_code":           sku_code,
                    "maker_color_code":   color["maker_color_code"],
                    "shelf_type":         "通常",
                    "inventory":          inventory,
                    "incoming_stock":     incoming,
                    "reserved_quantity":  reserved_qty,
                    "reservations_pending": reservations_pending,
                    "free_inventory":     free_inv,
                    "sales_cumulative":   sales_30d * random.randint(3, 8),
                    "favorites_total":    favorites,
                    "sales_7d":           sales_7d,
                    "sales_30d":          sales_30d,
                    "sales_2w":           int(sales_30d * 0.6),
                    "sales_ytd":          sales_30d * random.randint(6, 12),
                    "daily_velocity_7d":  round(vel_7d, 2),
                    "daily_velocity_30d": round(vel_30d, 2),
                    "stock_days_7d":      round(stock_days, 1) if stock_days is not None else None,
                    "monthly_gap":        monthly_gap,
                    "trend_coefficient":  round(trend, 2),
                    "cost_price":         cost_price,
                    "retail_price":       round(retail_price),
                    "gross_margin_pct":   round(margin, 3),
                    "recommended_order_qty": rec_qty,
                    "order_urgency":      urgency,
                    "days_to_stockout":   round(stock_days, 1) if stock_days is not None and stock_days <= 90 else None,
                    "daily_sales_30d":    _gen_daily_sales(sales_30d),
                    "monthly_sales":      [
                        {"month": "2025-09", "qty": int(sales_30d * 0.9)},
                        {"month": "2025-10", "qty": int(sales_30d * 1.1)},
                        {"month": "2025-11", "qty": sales_30d},
                    ],
                    "computed_at": target_date_str + "T02:00:00Z",
                })

    # Sort: CRITICAL first, then WARNING, then OK, then OVERSTOCK
    urgency_order = {"CRITICAL": 0, "WARNING": 1, "OK": 2, "OVERSTOCK": 3}
    rows.sort(key=lambda r: (urgency_order[r["order_urgency"]], r["days_to_stockout"] or 999, r["product_code"]))
    return rows


# ── Mock pipeline status data ─────────────────────────────────────────────────

PIPELINE_STEPS = [
    ("extract_zozo_sales",        "ZOZO 販売データ取得"),
    ("extract_zozo_inventory",    "ZOZO 在庫データ取得"),
    ("extract_sheets_reservations","Sheets 予約データ取得"),
    ("extract_cost_excel",        "原価マスター取得"),
    ("sync_product_master",       "商品マスター同期"),
    ("rebuild_kpi_mart",          "KPI マート再構築"),
]

QUALITY_DATASETS = [
    ("zozo_sales",         "ZOZO 販売", ["sku_code","sale_date","sales_quantity"]),
    ("zozo_inventory",     "ZOZO 在庫", ["sku_code","stock_quantity"]),
    ("sheets_reservations","Sheets 予約", ["product_code","quantity","status"]),
    ("excel_cost_master",  "原価マスター", ["product_code","cost_price","retail_price"]),
]

TABLE_SNAPSHOTS = [
    ("raw_layer",       "zozo_sales_raw"),
    ("raw_layer",       "zozo_inventory_raw"),
    ("raw_layer",       "sheets_reservations_raw"),
    ("analytics_layer", "sales_daily"),
    ("analytics_layer", "inventory_snapshot"),
    ("analytics_layer", "reservations"),
    ("analytics_layer", "cost_master"),
    ("mart_layer",      "order_analysis"),
    ("mart_layer",      "reorder_alerts"),
]

def _gen_pipeline_runs(n_days=7):
    """Generate mock pipeline run history for the last n_days."""
    random.seed(99)
    runs = []
    today = date.today()

    for day_offset in range(n_days):
        run_date = today - timedelta(days=day_offset)
        run_id = str(uuid.UUID(int=random.getrandbits(128)))
        # 02:05 JST run time (stored as UTC = 17:05 previous day)
        started_base = datetime(run_date.year, run_date.month, run_date.day, 17, 5, 0)

        # Simulate occasional failure on older runs
        force_fail_step = None
        if day_offset == 3:
            force_fail_step = "extract_sheets_reservations"

        steps = []
        cursor = started_base
        overall_ok = True

        for step_key, step_label in PIPELINE_STEPS:
            duration_ms = random.randint(8_000, 45_000)
            if step_key == "rebuild_kpi_mart":
                duration_ms = random.randint(60_000, 180_000)
            step_started = cursor
            step_finished = cursor + timedelta(milliseconds=duration_ms)
            cursor = step_finished

            failed = (step_key == force_fail_step)
            if failed:
                overall_ok = False

            rows = 0
            if not failed:
                if "sales" in step_key:       rows = random.randint(280, 320)
                elif "inventory" in step_key: rows = random.randint(280, 320)
                elif "reservations" in step_key: rows = random.randint(5, 30)
                elif "cost" in step_key:       rows = random.randint(50, 80)
                elif "product" in step_key:    rows = random.randint(40, 60)

            steps.append({
                "step":          step_key,
                "label":         step_label,
                "status":        "failed" if failed else "success",
                "rows":          rows,
                "duration_ms":   duration_ms if not failed else random.randint(1000, 5000),
                "started_at":    step_started.isoformat() + "Z",
                "finished_at":   step_finished.isoformat() + "Z",
                "error_message": "ConnectionError: sheets API timeout after 5s" if failed else None,
            })
            if failed:
                break  # pipeline aborts on failure

        total_ms = sum(s["duration_ms"] for s in steps)
        runs.append({
            "run_id":    run_id,
            "run_date":  str(run_date),
            "status":    "success" if overall_ok else "failed",
            "total_ms":  total_ms,
            "steps":     steps,
            "started_at": started_base.isoformat() + "Z",
        })

    return runs


def _gen_quality_report(run_date_str: str):
    """Generate mock data quality check results."""
    random.seed(hash(run_date_str) % 9999)
    reports = []

    for dataset_key, dataset_label, required_fields in QUALITY_DATASETS:
        base_rows = {
            "zozo_sales":         random.randint(290, 315),
            "zozo_inventory":     random.randint(290, 315),
            "sheets_reservations": random.randint(8, 25),
            "excel_cost_master":  random.randint(55, 72),
        }[dataset_key]

        checks = []
        all_pass = True

        # Min rows check
        checks.append({"check_name": "min_row_count", "passed": True,
                        "value": base_rows, "threshold": 1,
                        "message": f"{base_rows} rows (min 1)"})

        # Null rate checks
        for f in required_fields:
            null_rate = round(random.uniform(0, 0.01), 4)
            checks.append({"check_name": f"null_rate:{f}", "passed": True,
                            "value": null_rate, "threshold": 0.05,
                            "message": f"{f} null rate {null_rate*100:.1f}%"})

        # Non-negative
        neg_rate = 0.0
        checks.append({"check_name": "non_negative:quantity", "passed": True,
                        "value": neg_rate, "threshold": 0.02,
                        "message": "0 negative values (0.0%)"})

        # Duplicates
        checks.append({"check_name": "duplicates:sku_code", "passed": True,
                        "value": 0, "threshold": 0,
                        "message": "0 duplicate key combinations"})

        # DoD change
        dod = round(random.uniform(0, 0.08), 4)
        checks.append({"check_name": f"dod_change:{dataset_key}", "passed": True,
                        "value": dod, "threshold": 0.50,
                        "message": f"▲ {dod*100:.1f}% change vs previous day"})

        failed = [c for c in checks if not c["passed"]]
        reports.append({
            "dataset":       dataset_key,
            "label":         dataset_label,
            "run_date":      run_date_str,
            "row_count":     base_rows,
            "total_checks":  len(checks),
            "passed_checks": len(checks) - len(failed),
            "failed_checks": len(failed),
            "passed":        len(failed) == 0,
            "validated_at":  run_date_str + "T17:10:00Z",
            "checks":        checks,
        })

    return reports


def _gen_table_counts():
    """Generate mock BigQuery table row counts."""
    random.seed(77)
    today = date.today()
    result = []
    for dataset, table in TABLE_SNAPSHOTS:
        base = {
            "zozo_sales_raw":        2100,
            "zozo_inventory_raw":    2100,
            "sheets_reservations_raw": 180,
            "sales_daily":           2100,
            "inventory_snapshot":    2100,
            "reservations":          180,
            "cost_master":           420,
            "order_analysis":        30,
            "reorder_alerts":        12,
        }.get(table, 100)
        result.append({
            "dataset":      dataset,
            "table":        table,
            "row_count":    base + random.randint(-20, 20),
            "last_updated": str(today),
        })
    return result


# Pre-generate status data
PIPELINE_RUNS   = _gen_pipeline_runs()
QUALITY_REPORTS = _gen_quality_report(str(date.today()))
TABLE_COUNTS    = _gen_table_counts()


# ── HTTP server ───────────────────────────────────────────────────────────────

ALL_ROWS = generate_rows()
DEMO_DIR = os.path.dirname(os.path.abspath(__file__))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"  {self.address_string()} {fmt % args}")

    def do_GET(self):
        parsed = urlparse(self.path)
        path   = parsed.path
        qs     = parse_qs(parsed.query)

        if path == "/" or path == "/index.html":
            self._serve_file("index.html", "text/html; charset=utf-8")
        elif path == "/api/products":
            self._serve_products(qs)
        elif path == "/api/alerts":
            self._serve_alerts(qs)
        elif path == "/api/export":
            self._serve_csv(qs)
        elif path == "/api/status":
            self._serve_status(qs)
        else:
            self._404()

    def do_POST(self):
        parsed = urlparse(self.path)
        path   = parsed.path

        length  = int(self.headers.get("Content-Length", 0))
        body    = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(body)
        except Exception:
            payload = {}

        if path == "/api/simulate":
            self._serve_simulate(payload)
        elif path == "/api/allocate":
            self._serve_allocate(payload)
        else:
            self._404()

    def do_OPTIONS(self):
        """CORS preflight support."""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    # ── API handlers ──────────────────────────────────────────────────────────

    def _serve_products(self, qs):
        urgency = qs.get("urgency", [None])[0]
        product = qs.get("product_code", [None])[0]
        rows = ALL_ROWS
        if urgency:
            rows = [r for r in rows if r["order_urgency"] == urgency]
        if product:
            rows = [r for r in rows if r["product_code"] == product]
        self._json({
            "data": rows,
            "total": len(rows),
            "date": str(date.today()),
            "generated_at": str(date.today()) + "T02:00:00Z",
        })

    def _serve_status(self, qs):
        run_date = qs.get("date", [str(date.today())])[0]
        self._json({
            "pipeline_runs":   PIPELINE_RUNS,
            "quality_reports": _gen_quality_report(run_date),
            "table_counts":    TABLE_COUNTS,
            "summary": {
                "last_run_date":   PIPELINE_RUNS[0]["run_date"] if PIPELINE_RUNS else None,
                "last_run_status": PIPELINE_RUNS[0]["status"]   if PIPELINE_RUNS else None,
                "runs_last_7d":    len(PIPELINE_RUNS),
                "failures_last_7d": sum(1 for r in PIPELINE_RUNS if r["status"] == "failed"),
                "total_skus":      len(ALL_ROWS),
                "generated_at":    str(date.today()) + "T17:05:00Z",
            },
        })

    def _serve_simulate(self, payload):
        sku_code  = payload.get("sku_code", "")
        order_qty = payload.get("order_qty", None)

        # Find the SKU in mock data
        sku = next((r for r in ALL_ROWS if r["sku_code"] == sku_code), None)
        if not sku:
            body = json.dumps({"error": f"SKU {sku_code} not found"}, ensure_ascii=False).encode()
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        vel  = sku["daily_velocity_30d"]
        trend = min(2.0, max(0.5, sku["trend_coefficient"] or 1.0))
        adj_vel = vel * trend  # adjusted daily demand
        free = sku["free_inventory"]
        rec  = sku["recommended_order_qty"]

        if order_qty is None:
            q_con = max(0, round(rec * 0.5))
            q_bal = rec
            q_agg = round(rec * 1.5)
        else:
            q_con = max(0, round(order_qty * 0.6))
            q_bal = order_qty
            q_agg = round(order_qty * 1.5)

        def make_scenario(label, qty, desc):
            start = free + qty
            stockout_wk = None
            if adj_vel > 0:
                weeks = start / (adj_vel * 7)
                stockout_wk = math.ceil(weeks) if weeks < 12 else None
            cost   = qty * sku["cost_price"]
            units  = min(start, adj_vel * 7 * 12) if adj_vel > 0 else 0
            rev    = units * sku["retail_price"]
            profit = rev - cost - (free * sku["cost_price"])
            margin = profit / rev if rev > 0 else None
            return {
                "label":         label,
                "order_qty":     qty,
                "target_days":   round(start / adj_vel) if adj_vel > 0 else 0,
                "stockout_week": stockout_wk,
                "total_cost":    round(cost),
                "total_revenue": round(rev),
                "gross_profit":  round(profit),
                "margin_pct":    margin,
                "description":   desc,
            }

        # 12-week projections (linear for demo — no seasonal adjustment)
        weekly = []
        for w in range(1, 13):
            depletion = round(adj_vel * 7 * w)
            weekly.append({
                "week":                w,
                "stock_without_order": free - depletion,
                "stock_conservative":  free + q_con - depletion,
                "stock_balanced":      free + q_bal - depletion,
                "stock_aggressive":    free + q_agg - depletion,
            })

        self._json({
            "sku_code":     sku["sku_code"],
            "product_code": sku["product_code"],
            "product_name": sku["product_name"],
            "color_name":   sku["color_name"],
            "size":         sku["size"],
            "date":         str(date.today()),
            "current": {
                "free_inventory":        free,
                "daily_velocity_30d":    vel,
                "trend_coefficient":     trend,
                "stock_days_7d":         sku["stock_days_7d"],
                "order_urgency":         sku["order_urgency"],
                "cost_price":            sku["cost_price"],
                "retail_price":          sku["retail_price"],
                "gross_margin_pct":      sku["gross_margin_pct"],
                "recommended_order_qty": rec,
            },
            "scenarios": {
                "conservative": make_scenario("安全発注", q_con, "最小限の補充。キャッシュフロー優先。"),
                "balanced":     make_scenario("推奨発注", q_bal, "8週間カバレッジ。標準発注量。"),
                "aggressive":   make_scenario("積極発注", q_agg, "12週間カバレッジ。欠品リスクゼロ優先。"),
            },
            "weekly_projections": weekly,
        })

    def _serve_allocate(self, payload):
        product_code    = payload.get("product_code", "")
        total_order_qty = int(payload.get("total_order_qty", 0))

        skus = [r for r in ALL_ROWS if r["product_code"] == product_code]
        if not skus:
            body = json.dumps({"error": f"product {product_code} not found"}).encode()
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        def coeff(stock_days):
            if stock_days is None: return 1.0
            if stock_days <= 0:    return 1.5
            if stock_days <= 30:   return 1.0
            if stock_days <= 60:   return 0.9
            return 0.7

        total_sales_30d = sum(max(s["sales_30d"], 0) for s in skus)
        weights = [max(s["sales_30d"], 0) * coeff(s["stock_days_7d"]) for s in skus]
        total_weight = sum(weights)

        if total_weight > 0:
            raw_allocs = [total_order_qty * (w / total_weight) for w in weights]
        else:
            raw_allocs = [total_order_qty / len(skus)] * len(skus)

        floored = [math.floor(r) for r in raw_allocs]
        residual = total_order_qty - sum(floored)
        remainders = sorted(enumerate(raw_allocs), key=lambda x: -(x[1] - math.floor(x[1])))
        for j in range(residual):
            floored[remainders[j][0]] += 1

        result_skus = []
        for i, s in enumerate(skus):
            sales = max(s["sales_30d"], 0)
            c = coeff(s["stock_days_7d"])
            share = weights[i] / total_weight if total_weight > 0 else 1/len(skus)
            result_skus.append({
                "sku_code":         s["sku_code"],
                "color_code":       s["color_code"],
                "color_name":       s["color_name"],
                "size":             s["size"],
                "sales_30d":        sales,
                "stock_days_7d":    s["stock_days_7d"],
                "order_urgency":    s["order_urgency"],
                "free_inventory":   s["free_inventory"],
                "recommended_qty":  s["recommended_order_qty"],
                "sales_share_pct":  round(sales / total_sales_30d * 100, 1) if total_sales_30d else 0,
                "adj_coefficient":  c,
                "weight_share_pct": round(share * 100, 1),
                "allocated_qty":    floored[i],
            })

        self._json({
            "product_code":    product_code,
            "total_order_qty": total_order_qty,
            "total_sales_30d": total_sales_30d,
            "allocated_total": sum(floored),
            "skus":            result_skus,
        })

    def _serve_alerts(self, qs):
        alerts = [r for r in ALL_ROWS if r["order_urgency"] in ("CRITICAL", "WARNING")]
        self._json({
            "data": alerts,
            "summary": {
                "critical": sum(1 for r in alerts if r["order_urgency"] == "CRITICAL"),
                "warning":  sum(1 for r in alerts if r["order_urgency"] == "WARNING"),
                "total":    len(alerts),
            },
            "date": str(date.today()),
        })

    def _serve_csv(self, qs):
        rows = ALL_ROWS
        lines = [
            "メーカーカラー名,品番,商品名,カラー,サイズ,CS品番,在庫,入荷残,フリー在庫,"
            "7日間,一ヶ月,7日間分(日),推奨発注数,緊急度,原価,売価,粗利率"
        ]
        for r in rows:
            lines.append(",".join(str(x) for x in [
                r["maker_color_code"], r["product_code"], r["product_name"],
                r["color_name"], r["size"], r["sku_code"],
                r["inventory"], r["incoming_stock"], r["free_inventory"],
                r["sales_7d"], r["sales_30d"],
                r["stock_days_7d"] if r["stock_days_7d"] is not None else "",
                r["recommended_order_qty"], r["order_urgency"],
                r["cost_price"], r["retail_price"],
                f"{r['gross_margin_pct']*100:.1f}%",
            ]))
        csv_body = "\ufeff" + "\r\n".join(lines)  # BOM for Excel
        body = csv_body.encode("utf-8")
        today = str(date.today())
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="order_analysis_{today}.csv"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _json(self, data):
        body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, filename, content_type):
        filepath = os.path.join(DEMO_DIR, filename)
        if not os.path.exists(filepath):
            self._404()
            return
        with open(filepath, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _404(self):
        body = b"Not found"
        self.send_response(404)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8888
    server = HTTPServer(("0.0.0.0", port), Handler)
    today = str(date.today())
    total = len(ALL_ROWS)
    critical = sum(1 for r in ALL_ROWS if r["order_urgency"] == "CRITICAL")
    warning  = sum(1 for r in ALL_ROWS if r["order_urgency"] == "WARNING")
    print("=" * 55)
    print("  Order Decision Support System - Local Demo")
    print("=" * 55)
    print(f"  Date:     {today}")
    print(f"  SKUs:     {total} rows loaded")
    print(f"  CRITICAL: {critical}  WARNING: {warning}")
    print(f"  URL:      http://localhost:{port}")
    print("=" * 55)
    print("  Press Ctrl+C to stop")
    sys.stdout.flush()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
