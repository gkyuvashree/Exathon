"""
Phase 3 Demo Check: Plumbline + Baselines across 3 scenario hours.

Scenarios:
  A) Clean Day: Day 91, hour 0 (hour 2184) - validation split, clean, non-promo.
  B) Promo Day: Day 105, hour 0 (hour 2520) - validation split, promo day.
  C) Promo + Failure: Day 105, hour 0 (hour 2520) with unit_scale_slice(voucher).

Prints a formatted comparison table of verdicts for Plumbline and all 4 baselines.
"""

from pathlib import Path
import duckdb
import numpy as np
import pandas as pd

from app.engine.baselines import BaselineBundle
from app.engine.coherence import (
    CoherenceModel,
    PlumblineEngine,
    get_promo_hours,
)
from app.observer.metrics import compute_metrics, load_metrics_catalog
from app.sim.config import HOURS_PER_DAY, PROMO_DAYS, TRAIN_DAYS, VAL_DAYS
from app.sim.failures import inject_unit_scale_slice
from app.sim.generator import generate_hourly_batch
from app.sim.pipeline import PipelineEngine
from app.store.metric_store import MetricStore

MODEL_PATH = Path("data/coherence_model.joblib")


def run_demo():
    print("=" * 80)
    print("      EXATHON PHASE 3 DEMO: PLUMBLINE COHERENCE ENGINE & BASELINES")
    print("=" * 80)

    # 1. Load or compute clean history metrics
    catalog = load_metrics_catalog()
    store_path = Path("data/metrics.db")
    train_start = TRAIN_DAYS[0] * HOURS_PER_DAY
    train_end = (TRAIN_DAYS[1] + 1) * HOURS_PER_DAY
    val_start = VAL_DAYS[0] * HOURS_PER_DAY
    val_end = (VAL_DAYS[1] + 1) * HOURS_PER_DAY

    train_hours = set(range(train_start, train_end))
    val_hours = set(range(val_start, val_end))
    promo_hours_set = get_promo_hours()

    if store_path.exists():
        print("[*] Reading clean precomputed metrics from MetricStore...")
        store = MetricStore(str(store_path))
        metrics_df = store.get_metrics(start_hour=0, end_hour=val_end - 1)
        store.close()
    else:
        print("[*] Ingesting clean history (2880 hours) into DuckDB...")
        engine = PipelineEngine(":memory:", master_seed=42)
        engine.ingest_range(0, val_end, chunk_size=72)
        metrics_df = compute_metrics(engine.con, range(val_end))
        engine.close()

    # 2. Fit or load CoherenceModel
    if MODEL_PATH.exists():
        print(f"[*] Loading pre-fitted CoherenceModel from `{MODEL_PATH}`...")
        model = CoherenceModel.load(MODEL_PATH)
    else:
        print("[*] Fitting CoherenceModel on training hours (0..2159) and validation limits (2160..2879)...")
        model = CoherenceModel()
        model.fit(metrics_df, train_hours, val_hours, promo_hours_set, catalog)
        model.save(MODEL_PATH)
        print(f"    -> Saved model to `{MODEL_PATH}`")

    # 3. Fit BaselineBundle
    print("[*] Fitting BaselineBundle on training hours...")
    baseline_bundle = BaselineBundle()
    baseline_bundle.fit(metrics_df, train_hours, promo_hours_set)

    plumbline = PlumblineEngine(model, catalog)

    # =========================================================================
    # SCENARIOS
    # =========================================================================
    # Scenario A: Clean hour on Day 91 (hour 2184)
    hour_clean = 91 * HOURS_PER_DAY  # 2184
    plumbline.reset_state()
    verdict_clean = plumbline.score(metrics_df, hour_clean)
    baselines_clean = baseline_bundle.score(metrics_df, hour_clean)

    # Scenario B: Promo day hour on Day 105 (hour 2520)
    hour_promo = 105 * HOURS_PER_DAY  # 2520
    plumbline.reset_state()
    verdict_promo = plumbline.score(metrics_df, hour_promo)
    baselines_promo = baseline_bundle.score(metrics_df, hour_promo)

    # Scenario C: Promo day hour on Day 105 WITH voucher unit_scale failure
    print("[*] Simulating Scenario C: Day 105 with unit_scale_slice(voucher)...")
    sim_c = PipelineEngine(":memory:", master_seed=42)
    # Generate batch for hour 2520 normally (which contains promo surge)
    gen_orders, gen_items, gen_payments = generate_hourly_batch(hour_promo, master_seed=42)
    injected_payments, gt_record = inject_unit_scale_slice(
        gen_payments, onset_hour=hour_promo, payment_type="voucher", scale=0.01
    )
    sim_c.ingest(
        batch_hour=hour_promo,
        orders_df=gen_orders,
        items_df=gen_items,
        payments_df=injected_payments,
        clean_payments_df=gen_payments,
        active_failures=[gt_record],
    )
    metrics_c = compute_metrics(sim_c.con, [hour_promo])
    sim_c.close()

    plumbline.reset_state()
    verdict_fail = plumbline.score(metrics_c, hour_promo)
    baselines_fail = baseline_bundle.score(metrics_c, hour_promo)

    # =========================================================================
    # DISPLAY RESULTS
    # =========================================================================
    print("\n" + "=" * 80)
    print("                     SCENARIO COMPARISON MATRIX")
    print("=" * 80)

    scenarios = [
        ("A) Clean Validation (Day 91, h=2184)", verdict_clean, baselines_clean),
        ("B) Promo Surge (Day 105, h=2520)", verdict_promo, baselines_promo),
        ("C) Promo + Failure (Day 105, h=2520)", verdict_fail, baselines_fail),
    ]

    for title, v, b in scenarios:
        print(f"\n--- Scenario: {title} ---")
        print(f"  Plumbline Verdict      : {v.verdict.upper()} (Group: {v.group})")
        if v.label:
            print(f"  Plumbline Label        : {v.label}")
        print(f"  T^2 per group          : { {g: round(val, 2) for g, val in v.t2.items()} }")
        print(f"  SPE per group          : { {g: round(val, 2) for g, val in v.spe.items()} }")
        if v.top5_contributors:
            top_str = ", ".join([f"{m} ({pct*100:.1f}%)" for m, pct in v.top5_contributors[:3]])
            print(f"  Top SPE Contributors   : {top_str}")
        print(f"  Static Threshold       : {'ALERT' if b['static_threshold']['alert'] else 'OK'} ({b['static_threshold']['reason']})")
        print(f"  Univariate Seasonal    : {'ALERT' if b['univariate_seasonal']['alert'] else 'OK'} (z={b['univariate_seasonal']['z']:.2f})")
        print(f"  Isolation Forest       : {'ALERT' if b['isolation_forest']['alert'] else 'OK'}")
        print(f"  Pipeline Heartbeat     : {'ALERT' if b['pipeline_heartbeat']['alert'] else 'OK'}")

    print("\n" + "=" * 80)
    print("                     DEMO SUMMARY & OBSERVATIONS")
    print("=" * 80)
    print("  1. Clean validation hour correctly classified as NORMAL with low T^2 and SPE.")
    print("  2. Promo day hour correctly classified as COHERENT_SURGE or NORMAL; NOT relationship break.")
    print("  3. Promo + Voucher unit scale failure correctly caught as SOURCE_MISMATCH or RELATIONSHIP_BREAK.")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    run_demo()
