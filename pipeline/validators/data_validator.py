"""
Data quality validation — runs after each extraction step.
Checks null rates, value ranges, duplicates, and day-over-day anomalies.
Results are stored in BigQuery monitoring.data_quality_checks.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class CheckResult:
    check_name: str
    passed: bool
    value: float | int | None
    threshold: float | int | None
    message: str


@dataclass
class ValidationReport:
    dataset: str          # e.g. "zozo_sales", "zozo_inventory"
    run_date: str
    row_count: int
    checks: list[CheckResult] = field(default_factory=list)
    passed: bool = True
    validated_at: str = ""

    def __post_init__(self):
        self.validated_at = datetime.now(timezone.utc).isoformat()

    def add(self, result: CheckResult) -> None:
        self.checks.append(result)
        if not result.passed:
            self.passed = False

    def summary(self) -> dict[str, Any]:
        failed = [c for c in self.checks if not c.passed]
        return {
            "dataset":      self.dataset,
            "run_date":     self.run_date,
            "row_count":    self.row_count,
            "total_checks": len(self.checks),
            "passed_checks": len(self.checks) - len(failed),
            "failed_checks": len(failed),
            "passed":        self.passed,
            "validated_at":  self.validated_at,
            "failures":      [asdict(c) for c in failed],
            "all_checks":    [asdict(c) for c in self.checks],
        }


# ── Validator ─────────────────────────────────────────────────────────────────

class DataValidator:
    """Runs a suite of quality checks on extracted records."""

    # Maximum acceptable null rate for required fields
    NULL_RATE_THRESHOLD = 0.05      # 5%
    # Minimum row count to be considered a valid extraction
    MIN_ROW_COUNT = 1
    # Maximum day-over-day row count change (fraction)
    DOD_CHANGE_THRESHOLD = 0.50     # 50%
    # Maximum acceptable negative-value rate for quantity fields
    NEG_RATE_THRESHOLD = 0.02       # 2%

    def validate_sales(
        self,
        records: list[dict],
        run_date: str,
        prev_row_count: int | None = None,
    ) -> ValidationReport:
        report = ValidationReport("zozo_sales", run_date, len(records))

        # 1. Minimum row count
        report.add(self._check_min_rows(records, self.MIN_ROW_COUNT))

        # 2. Required fields null check
        for field_name in ["sku_code", "sale_date", "sales_quantity"]:
            report.add(self._check_null_rate(records, field_name))

        # 3. Non-negative quantities
        report.add(self._check_non_negative(records, "sales_quantity"))

        # 4. Date range — all records should match run_date
        report.add(self._check_date_field(records, "sale_date", run_date))

        # 5. Duplicate SKUs
        report.add(self._check_duplicates(records, ["sku_code", "sale_date"]))

        # 6. Day-over-day row count anomaly
        if prev_row_count is not None:
            report.add(self._check_dod_change(len(records), prev_row_count, "sales"))

        self._log_report(report)
        return report

    def validate_inventory(
        self,
        records: list[dict],
        run_date: str,
        prev_row_count: int | None = None,
    ) -> ValidationReport:
        report = ValidationReport("zozo_inventory", run_date, len(records))

        report.add(self._check_min_rows(records, self.MIN_ROW_COUNT))

        for field_name in ["sku_code", "stock_quantity"]:
            report.add(self._check_null_rate(records, field_name))

        # stock_quantity should be >= 0 (already floor'd in cleansing SQL, but check here)
        report.add(self._check_non_negative(records, "stock_quantity"))
        report.add(self._check_duplicates(records, ["sku_code"]))

        if prev_row_count is not None:
            report.add(self._check_dod_change(len(records), prev_row_count, "inventory"))

        self._log_report(report)
        return report

    def validate_reservations(
        self,
        records: list[dict],
        run_date: str,
    ) -> ValidationReport:
        report = ValidationReport("sheets_reservations", run_date, len(records))

        # Reservations can be zero (no pending orders) — only check structure
        for field_name in ["product_code", "quantity", "status"]:
            report.add(self._check_null_rate(records, field_name))

        if records:
            report.add(self._check_non_negative(records, "quantity"))
            report.add(self._check_enum(
                records, "status", {"pending", "confirmed", "cancelled"}
            ))

        self._log_report(report)
        return report

    def validate_cost_master(
        self,
        records: list[dict],
        run_date: str,
    ) -> ValidationReport:
        report = ValidationReport("excel_cost_master", run_date, len(records))

        report.add(self._check_min_rows(records, self.MIN_ROW_COUNT))

        for field_name in ["product_code", "cost_price", "retail_price"]:
            report.add(self._check_null_rate(records, field_name))

        report.add(self._check_non_negative(records, "cost_price"))
        report.add(self._check_non_negative(records, "retail_price"))

        # Retail price should always exceed cost price
        report.add(self._check_margin_positive(records))

        self._log_report(report)
        return report

    # ── Individual checks ─────────────────────────────────────────────────────

    def _check_min_rows(self, records: list[dict], minimum: int) -> CheckResult:
        n = len(records)
        passed = n >= minimum
        return CheckResult(
            check_name="min_row_count",
            passed=passed,
            value=n,
            threshold=minimum,
            message=f"{n} rows (min {minimum})" if passed else f"Only {n} rows — possible extraction failure",
        )

    def _check_null_rate(self, records: list[dict], field_name: str) -> CheckResult:
        if not records:
            return CheckResult(
                check_name=f"null_rate:{field_name}", passed=True,
                value=None, threshold=self.NULL_RATE_THRESHOLD,
                message="No records to check",
            )
        null_count = sum(1 for r in records if r.get(field_name) is None or r.get(field_name) == "")
        rate = null_count / len(records)
        passed = rate <= self.NULL_RATE_THRESHOLD
        return CheckResult(
            check_name=f"null_rate:{field_name}",
            passed=passed,
            value=round(rate, 4),
            threshold=self.NULL_RATE_THRESHOLD,
            message=f"{field_name} null rate {rate*100:.1f}% ({null_count}/{len(records)})" + ("" if passed else " — EXCEEDS THRESHOLD"),
        )

    def _check_non_negative(self, records: list[dict], field_name: str) -> CheckResult:
        if not records:
            return CheckResult(
                check_name=f"non_negative:{field_name}", passed=True,
                value=None, threshold=self.NEG_RATE_THRESHOLD, message="No records",
            )
        neg_count = sum(1 for r in records if isinstance(r.get(field_name), (int, float)) and r[field_name] < 0)
        rate = neg_count / len(records)
        passed = rate <= self.NEG_RATE_THRESHOLD
        return CheckResult(
            check_name=f"non_negative:{field_name}",
            passed=passed,
            value=round(rate, 4),
            threshold=self.NEG_RATE_THRESHOLD,
            message=f"{field_name}: {neg_count} negative values ({rate*100:.1f}%)" + ("" if passed else " — EXCEEDS THRESHOLD"),
        )

    def _check_duplicates(self, records: list[dict], key_fields: list[str]) -> CheckResult:
        if not records:
            return CheckResult(
                check_name=f"duplicates:{'+'.join(key_fields)}", passed=True,
                value=0, threshold=0, message="No records",
            )
        keys = [tuple(r.get(f) for f in key_fields) for r in records]
        dup_count = len(keys) - len(set(keys))
        passed = dup_count == 0
        return CheckResult(
            check_name=f"duplicates:{'+'.join(key_fields)}",
            passed=passed,
            value=dup_count,
            threshold=0,
            message=f"{dup_count} duplicate key combinations" + ("" if passed else " — DEDUPLICATION REQUIRED"),
        )

    def _check_date_field(self, records: list[dict], field_name: str, expected_date: str) -> CheckResult:
        if not records:
            return CheckResult(
                check_name=f"date_match:{field_name}", passed=True,
                value=None, threshold=None, message="No records",
            )
        mismatch = sum(1 for r in records if str(r.get(field_name, ""))[:10] != expected_date)
        passed = mismatch == 0
        return CheckResult(
            check_name=f"date_match:{field_name}",
            passed=passed,
            value=mismatch,
            threshold=0,
            message=f"{mismatch} records with date != {expected_date}" + ("" if passed else " — DATE MISMATCH"),
        )

    def _check_dod_change(self, current: int, previous: int, label: str) -> CheckResult:
        if previous == 0:
            return CheckResult(
                check_name=f"dod_change:{label}", passed=True,
                value=None, threshold=self.DOD_CHANGE_THRESHOLD,
                message="No previous day count to compare",
            )
        change = abs(current - previous) / previous
        passed = change <= self.DOD_CHANGE_THRESHOLD
        direction = "▲" if current > previous else "▼"
        return CheckResult(
            check_name=f"dod_change:{label}",
            passed=passed,
            value=round(change, 4),
            threshold=self.DOD_CHANGE_THRESHOLD,
            message=f"{direction} {change*100:.1f}% change vs previous day ({previous} → {current})" + ("" if passed else " — ANOMALY DETECTED"),
        )

    def _check_enum(self, records: list[dict], field_name: str, valid_values: set) -> CheckResult:
        invalid = [r.get(field_name) for r in records if r.get(field_name) not in valid_values]
        passed = len(invalid) == 0
        return CheckResult(
            check_name=f"enum:{field_name}",
            passed=passed,
            value=len(invalid),
            threshold=0,
            message=f"{field_name}: {len(invalid)} invalid values" + (f" (e.g. {list(set(invalid))[:3]})" if invalid else ""),
        )

    def _check_margin_positive(self, records: list[dict]) -> CheckResult:
        bad = sum(
            1 for r in records
            if isinstance(r.get("cost_price"), (int, float))
            and isinstance(r.get("retail_price"), (int, float))
            and r["retail_price"] <= r["cost_price"]
        )
        passed = bad == 0
        return CheckResult(
            check_name="margin_positive",
            passed=passed,
            value=bad,
            threshold=0,
            message=f"{bad} SKUs where retail_price <= cost_price" + ("" if passed else " — PRICING ERROR"),
        )

    def _log_report(self, report: ValidationReport) -> None:
        status = "PASSED" if report.passed else "FAILED"
        failed = [c for c in report.checks if not c.passed]
        logger.info(
            "[DataValidator] %s %s — %d rows, %d/%d checks passed",
            report.dataset, status, report.row_count,
            len(report.checks) - len(failed), len(report.checks),
        )
        for c in failed:
            logger.warning("[DataValidator] FAIL %s: %s", c.check_name, c.message)


# ── BigQuery writer ───────────────────────────────────────────────────────────

def write_quality_report(bq_client, project: str, report: ValidationReport) -> None:
    """Persist the validation report to monitoring.data_quality_checks."""
    table = f"{project}.monitoring.data_quality_checks"
    summary = report.summary()
    rows = [{
        "run_date":      summary["run_date"],
        "dataset":       summary["dataset"],
        "row_count":     summary["row_count"],
        "total_checks":  summary["total_checks"],
        "passed_checks": summary["passed_checks"],
        "failed_checks": summary["failed_checks"],
        "passed":        summary["passed"],
        "validated_at":  summary["validated_at"],
        "failures_json": str(summary["failures"]),
        "all_checks_json": str(summary["all_checks"]),
    }]
    try:
        errors = bq_client.insert_rows_json(table, rows)
        if errors:
            logger.warning("Failed to write quality report: %s", errors)
    except Exception as exc:
        logger.warning("Quality report write error (non-fatal): %s", exc)
