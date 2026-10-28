"""Statistical computation and explicit regression rules.

Numbers are computed here, never by the LLM.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from .models import Metric
from .tools import parse_timestamp

# Explicit, reviewable business rules.
MIN_SAMPLES_PER_WINDOW = 30
LATENCY_REGRESSION_PCT = 20.0  # p95 increase that counts as a regression
ERROR_RATE_REGRESSION_PP = 1.0  # error-rate increase, in percentage points


class InsufficientData(ValueError):
    pass


def percentile(values: Sequence[float], q: int) -> float:
    """q-th percentile (1..99) using linear interpolation between samples."""
    if not 1 <= q <= 99:
        raise ValueError("q must be between 1 and 99")
    return statistics.quantiles(values, n=100, method="inclusive")[q - 1]


def _window_stats(samples: Sequence[dict[str, Any]]) -> dict[str, float]:
    latencies = [float(s["latency_ms"]) for s in samples]
    errors = sum(1 for s in samples if int(s["status"]) >= 500)
    return {
        "n": len(samples),
        "p50_ms": round(percentile(latencies, 50), 1),
        "p95_ms": round(percentile(latencies, 95), 1),
        "error_rate_pct": round(100.0 * errors / len(samples), 2),
    }


def compare_windows(samples: Sequence[dict[str, Any]], split: datetime) -> dict[str, float]:
    """Compare request samples before and after ``split`` (e.g. a deploy time)."""
    before = [s for s in samples if parse_timestamp(s["timestamp"]) < split]
    after = [s for s in samples if parse_timestamp(s["timestamp"]) >= split]
    if min(len(before), len(after)) < MIN_SAMPLES_PER_WINDOW:
        raise InsufficientData(
            f"need >= {MIN_SAMPLES_PER_WINDOW} samples per window, "
            f"got {len(before)} before and {len(after)} after"
        )
    b, a = _window_stats(before), _window_stats(after)
    return {
        "samples_before": b["n"],
        "samples_after": a["n"],
        "p50_before_ms": b["p50_ms"],
        "p50_after_ms": a["p50_ms"],
        "p95_before_ms": b["p95_ms"],
        "p95_after_ms": a["p95_ms"],
        "p95_change_pct": round(100.0 * (a["p95_ms"] - b["p95_ms"]) / b["p95_ms"], 1),
        "error_rate_before_pct": b["error_rate_pct"],
        "error_rate_after_pct": a["error_rate_pct"],
        "error_rate_change_pp": round(a["error_rate_pct"] - b["error_rate_pct"], 2),
    }


def is_regression(comparison: dict[str, float], metric: Metric) -> bool:
    if metric is Metric.LATENCY:
        return comparison["p95_change_pct"] >= LATENCY_REGRESSION_PCT
    return comparison["error_rate_change_pp"] >= ERROR_RATE_REGRESSION_PP
