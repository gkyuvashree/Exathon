"""History Precomputation Script for 120 Days of Clean Observability Metrics."""

import os
import sys
import time
from pathlib import Path
from typing import Dict, List
import numpy as np
import pandas as pd

from app.observer.metrics import compute_metrics, get_metric_to_group_map, load_metrics_catalog
from app.sim.config import HOURS_PER_DAY
from app.sim.pipeline import PipelineEngine
from app.store.metric_store import MetricStore

DEFAULT_HISTORY_DAYS = 120
DEFAULT_HISTORY_HOURS = DEFAULT_HISTORY_DAYS * HOURS_PER_DAY  # 2880 hours
DEFAULT_DB_PATH = "data/metrics.db"


def build_history(
    num_days: int = DEFAULT_HISTORY_DAYS,
    db_path: str = DEFAULT_DB_PATH,
    master_seed: int = 42,
) -> int:
    """
    Ingests clean history for 120 days (2,880 hours), computes metrics in a single pass,
    persists them to SQLite MetricStore, and prints a summary table.
    """
    start_time = time.perf_counter()
    num_hours = num_days * HOURS_PER_DAY
    print("=" * 80)
    print(f"       EXATHON OBSERVER: 120-DAY HISTORY METRIC PRECOMPUTATION")
    print("=" * 80)
    print(f"[*] Target horizon: {num_days} days ({num_hours} hourly batches)")
    print(f"[*] Storage target: SQLite `{db_path}` -> table `metrics_ts`")

    # 1. Ingest clean data into DuckDB
    print("\n[1/3] Generating and ingesting clean pipeline data in DuckDB...")
    ingest_start = time.perf_counter()
    engine = PipelineEngine(":memory:", master_seed=master_seed)
    engine.ingest_range(0, num_hours, chunk_size=72)
    ingest_time = time.perf_counter() - ingest_start
    print(f"      -> Ingested {num_hours} hours across all DAG layers in {ingest_time:.2f}s")

    # 2. Compute metrics for all 2,880 hours in one pass
    print("\n[2/3] Computing vectorized metrics via DuckDB (compute_metrics)...")
    comp_start = time.perf_counter()
    metrics_df = compute_metrics(engine.con, range(num_hours))
    comp_time = time.perf_counter() - comp_start
    print(f"      -> Computed {len(metrics_df):,} metric data points in {comp_time:.2f}s")

    # Verify no NaN or Inf
    nan_count = int(metrics_df["value"].isna().sum())
    inf_count = int(np.isinf(metrics_df["value"].values).sum())
    if nan_count > 0 or inf_count > 0:
        raise ValueError(f"Found {nan_count} NaNs and {inf_count} Infs in computed metrics!")

    # 3. Write metrics to SQLite MetricStore
    print("\n[3/3] Writing metrics to SQLite MetricStore (metrics_ts)...")
    write_start = time.perf_counter()
    store = MetricStore(db_path)
    store.write_metrics(metrics_df)
    write_time = time.perf_counter() - write_start
    print(f"      -> Persisted {store.count():,} rows with indices in {write_time:.2f}s")

    total_time = time.perf_counter() - start_time

    # 4. Generate Metric Group Summary Table
    group_map = get_metric_to_group_map()
    metrics_df["group"] = metrics_df["metric"].map(lambda m: group_map.get(m, "totals"))

    group_summary = []
    for grp in ["orders", "items", "payments", "totals", "mart"]:
        grp_data = metrics_df[metrics_df["group"] == grp]
        distinct_metrics = grp_data["metric"].nunique()
        total_rows = len(grp_data)
        min_val = float(grp_data["value"].min()) if total_rows > 0 else 0.0
        max_val = float(grp_data["value"].max()) if total_rows > 0 else 0.0
        group_summary.append({
            "group": grp,
            "distinct_metrics": distinct_metrics,
            "rows_written": total_rows,
            "val_min": min_val,
            "val_max": max_val,
        })

    # Print summary table
    print("\n" + "=" * 80)
    print("                      METRIC GROUP SUMMARY REPORT")
    print("=" * 80)
    col_w_g = 14
    col_w_m = 18
    col_w_r = 16
    col_w_v = 24

    sep = "+" + "-" * (col_w_g + 2) + "+" + "-" * (col_w_m + 2) + "+" + "-" * (col_w_r + 2) + "+" + "-" * (col_w_v + 2) + "+"
    hdr = f"| {'Metric Group':<{col_w_g}} | {'Distinct Metrics':<{col_w_m}} | {'Rows Written':<{col_w_r}} | {'Value Range [min, max]':<{col_w_v}} |"
    print(sep)
    print(hdr)
    print(sep)

    for gs in group_summary:
        range_str = f"[{gs['val_min']:.2f}, {gs['val_max']:.2f}]"
        print(f"| {gs['group']:<{col_w_g}} | {gs['distinct_metrics']:<{col_w_m}} | {gs['rows_written']:<{col_w_r},} | {range_str:<{col_w_v}} |")
    print(sep)

    print(f"\nTotal Metrics Written   : {len(metrics_df):,}")
    print(f"Distinct Hours Computed : {metrics_df['hour_ts'].nunique():,}")
    print(f"NaN / Inf Anomalies     : 0 (ALL CLEAN)")
    print(f"Total Execution Time    : {total_time:.2f} seconds (< 90s SLA target: PASS)")
    print("=" * 80 + "\n")

    engine.close()
    store.close()

    assert total_time < 90.0, f"History build took {total_time:.2f}s, exceeding 90s SLA limit!"
    return 0


if __name__ == "__main__":
    sys.exit(build_history())
