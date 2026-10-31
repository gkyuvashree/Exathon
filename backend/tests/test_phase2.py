"""Comprehensive Unit and Integration Tests for Phase 2 Observer and Metric Store."""

import time
import numpy as np
import pandas as pd
import pytest

from app.observer.metrics import (
    compute_metrics,
    get_metric_to_group_map,
    load_metrics_catalog,
)
from app.sim.config import HOURS_PER_DAY
from app.sim.pipeline import PipelineEngine
from app.store.metric_store import MetricStore


# ==============================================================================
# 1. BATCH VS SINGLE-HOUR EQUIVALENCE TEST
# ==============================================================================

def test_batch_vs_single_hour_equivalence():
    """
    Verify that compute_metrics([h]) returns the exact same metric values
    as row h of a multi-hour batch compute pass compute_metrics(range(N)).
    """
    engine = PipelineEngine(":memory:", master_seed=42)
    test_hours = 24
    engine.ingest_range(0, test_hours, chunk_size=24)

    # 1. Run multi-hour batch computation
    batch_metrics = compute_metrics(engine.con, range(test_hours))
    assert not batch_metrics.empty

    # 2. Test single-hour computation for representative sample hours
    sample_hours = [0, 5, 12, 18, 23]
    for h in sample_hours:
        single_metrics = compute_metrics(engine.con, [h])
        assert not single_metrics.empty

        # Filter the batch result for this specific hour
        batch_slice = batch_metrics[batch_metrics["hour_ts"] == h].copy()

        # Sort both by node, metric, segment to align identically
        sort_cols = ["node", "metric", "segment"]
        single_sorted = single_metrics.sort_values(by=sort_cols).reset_index(drop=True)
        batch_sorted = batch_slice.sort_values(by=sort_cols).reset_index(drop=True)

        assert len(single_sorted) == len(batch_sorted), f"Mismatch in metric row counts for hour {h}"
        assert (single_sorted["metric"] == batch_sorted["metric"]).all()
        assert (single_sorted["segment"] == batch_sorted["segment"]).all()

        # Values must match within floating point precision
        diff = np.abs(single_sorted["value"].values - batch_sorted["value"].values)
        max_diff = np.max(diff)
        assert max_diff < 1e-4, f"Hour {h} values differ by up to {max_diff}"

    engine.close()


# ==============================================================================
# 2. NO NAN / INF IN CLEAN HISTORY & EMPTY-HOUR FALLBACKS
# ==============================================================================

def test_no_nan_inf_in_clean_history_and_fallbacks():
    """
    Verify that compute_metrics never outputs NaN or Inf for populated or empty hours.
    Documented fallbacks must ensure completely finite outputs.
    """
    engine = PipelineEngine(":memory:", master_seed=42)
    # Ingest 12 hours of populated clean data
    engine.ingest_range(0, 12, chunk_size=12)

    # Compute metrics for hours 0..11 PLUS an empty hour (hour 999 where no data was ingested)
    hours_to_test = list(range(12)) + [999]
    metrics = compute_metrics(engine.con, hours_to_test)

    # 1. Check finiteness
    assert not np.isnan(metrics["value"]).any(), "NaN found in computed metrics"
    assert not np.isinf(metrics["value"]).any(), "Inf found in computed metrics"

    # 2. Check empty hour fallbacks
    empty_slice = metrics[metrics["hour_ts"] == 999]
    assert not empty_slice.empty
    # Ratios on empty hour should safely fall back to 0.0 or 1.0, not crash or produce NaN
    assert not np.isnan(empty_slice["value"]).any()
    assert not np.isinf(empty_slice["value"]).any()

    engine.close()


# ==============================================================================
# 3. METRIC CATALOG & GROUP MEMBERSHIP TESTS
# ==============================================================================

def test_metric_catalog_and_group_assignment():
    """
    Verify that every metric in the catalog belongs to exactly ONE of the 5 groups:
    [orders, items, payments, totals, mart] and has valid kind attributes.
    """
    catalog = load_metrics_catalog()
    assert len(catalog) > 0

    valid_groups = {"orders", "items", "payments", "totals", "mart"}
    valid_kinds = {"volume", "ratio", "lag", "share"}

    metric_names = set()
    for m in catalog:
        assert m["name"] not in metric_names, f"Duplicate metric name: {m['name']}"
        metric_names.add(m["name"])
        assert m["group"] in valid_groups, f"Invalid group {m['group']} for {m['name']}"
        assert m["kind"] in valid_kinds, f"Invalid kind {m['kind']} for {m['name']}"
        assert "node" in m

    group_map = get_metric_to_group_map()
    assert len(group_map) == len(catalog)


def test_metric_count_per_group_logged():
    """Verify all 5 metric groups produce positive counts during metric computation."""
    engine = PipelineEngine(":memory:", master_seed=42)
    engine.ingest_range(0, 6, chunk_size=6)

    metrics_df = compute_metrics(engine.con, range(6))
    group_map = get_metric_to_group_map()
    metrics_df["group"] = metrics_df["metric"].map(lambda m: group_map.get(m, "totals"))

    counts_by_group = metrics_df.groupby("group")["metric"].nunique().to_dict()

    expected_groups = ["orders", "items", "payments", "totals", "mart"]
    for grp in expected_groups:
        assert grp in counts_by_group, f"Group {grp} missing from computed metrics"
        assert counts_by_group[grp] > 0, f"Group {grp} has 0 metrics"

    engine.close()


# ==============================================================================
# 4. METRIC STORE CRUD & INDEXING TESTS
# ==============================================================================

def test_metric_store_crud():
    """Verify SQLite MetricStore write, read, filter, and primary key idempotency."""
    store = MetricStore(":memory:")

    records = [
        {"node": "raw_orders", "metric": "orders_row_count", "segment": "ALL", "hour_ts": 1, "value": 150.0},
        {"node": "raw_orders", "metric": "orders_row_count", "segment": "ALL", "hour_ts": 2, "value": 165.0},
        {"node": "raw_payments", "metric": "payments_type_sum", "segment": "voucher", "hour_ts": 1, "value": 500.0},
        {"node": "raw_payments", "metric": "payments_type_sum", "segment": "wallet", "hour_ts": 1, "value": 450.0},
    ]

    store.write_metrics(records)
    assert store.count() == 4
    assert store.get_distinct_hours() == [1, 2]

    # Test filtering
    df_filtered = store.get_metrics(node="raw_orders")
    assert len(df_filtered) == 2

    df_seg = store.get_metrics(segment="voucher")
    assert len(df_seg) == 1
    assert df_seg.iloc[0]["value"] == 500.0

    # Test idempotency (INSERT OR REPLACE)
    update_records = [
        {"node": "raw_orders", "metric": "orders_row_count", "segment": "ALL", "hour_ts": 1, "value": 155.0},
    ]
    store.write_metrics(update_records)
    assert store.count() == 4  # Count must remain 4, value updated
    df_updated = store.get_metrics(node="raw_orders", hour_ts=1)
    assert df_updated.iloc[0]["value"] == 155.0

    store.close()


# ==============================================================================
# 5. 120-DAY HISTORY PRECOMPUTE PERFORMANCE SLA (< 90 s)
# ==============================================================================

def test_120_day_precompute_performance_sla():
    """
    Verify that 120 days (2,880 hours) of data ingestion and metric computation
    completes comfortably within the 90-second SLA limit.
    """
    start_time = time.perf_counter()
    num_hours = 120 * HOURS_PER_DAY  # 2880 hours

    engine = PipelineEngine(":memory:", master_seed=42)
    engine.ingest_range(0, num_hours, chunk_size=72)
    metrics_df = compute_metrics(engine.con, range(num_hours))

    store = MetricStore(":memory:")
    store.write_metrics(metrics_df)

    elapsed = time.perf_counter() - start_time

    assert len(metrics_df) > 200_000, f"Expected >200,000 metric rows, got {len(metrics_df)}"
    assert store.count() == len(metrics_df)
    assert elapsed < 90.0, f"History precompute took {elapsed:.2f}s, exceeding 90s SLA limit!"

    engine.close()
    store.close()
