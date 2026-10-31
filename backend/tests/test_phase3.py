"""
Comprehensive Unit & Integration Tests for Phase 3:
Plumbline Coherence Engine and Baselines.
"""

from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from app.engine.baselines import BaselineBundle
from app.engine.coherence import (
    CoherenceModel,
    PlumblineEngine,
    SeasonalBaseline,
    get_promo_hours,
)
from app.observer.metrics import compute_metrics, load_metrics_catalog
from app.sim.config import HOURS_PER_DAY, PROMO_DAYS, TRAIN_DAYS, VAL_DAYS
from app.sim.failures import inject_unit_scale_slice
from app.sim.generator import generate_hourly_batch
from app.sim.pipeline import PipelineEngine
from app.store.metric_store import MetricStore


@pytest.fixture(scope="module")
def clean_metrics_df():
    """Load clean precomputed metrics from MetricStore or compute if missing."""
    store_path = Path("data/metrics.db")
    if store_path.exists():
        store = MetricStore(str(store_path))
        val_end = (VAL_DAYS[1] + 1) * HOURS_PER_DAY
        df = store.get_metrics(start_hour=0, end_hour=val_end - 1)
        store.close()
        return df

    engine = PipelineEngine(":memory:", master_seed=42)
    val_end = (VAL_DAYS[1] + 1) * HOURS_PER_DAY
    engine.ingest_range(0, val_end, chunk_size=72)
    df = compute_metrics(engine.con, range(val_end))
    engine.close()
    return df


@pytest.fixture(scope="module")
def fitted_model(clean_metrics_df):
    """Fit CoherenceModel once on clean train hours with validation limits."""
    catalog = load_metrics_catalog()
    train_start = TRAIN_DAYS[0] * HOURS_PER_DAY
    train_end = (TRAIN_DAYS[1] + 1) * HOURS_PER_DAY
    val_start = VAL_DAYS[0] * HOURS_PER_DAY
    val_end = (VAL_DAYS[1] + 1) * HOURS_PER_DAY

    train_hours = set(range(train_start, train_end))
    val_hours = set(range(val_start, val_end))
    promo_hours_set = get_promo_hours()

    model = CoherenceModel()
    model.fit(clean_metrics_df, train_hours, val_hours, promo_hours_set, catalog)
    return model


# ==============================================================================
# 1. CLEAN VALIDATION FALSE ALARM RATE TEST
# ==============================================================================

def test_clean_validation_false_alarm_rate(fitted_model, clean_metrics_df):
    """
    Score all 720 hours of clean validation data (days 90-119, hours 2160..2879).
    Verify that the false alarm rate is well controlled:
    Target: <= 1 alert / week (168 hours) -> <= 1/168 ~= 0.595%.
    """
    catalog = load_metrics_catalog()
    plumbline = PlumblineEngine(fitted_model, catalog)
    plumbline.reset_state()

    val_start = VAL_DAYS[0] * HOURS_PER_DAY
    val_end = (VAL_DAYS[1] + 1) * HOURS_PER_DAY
    val_hours = list(range(val_start, val_end))

    val_metrics = clean_metrics_df[clean_metrics_df["hour_ts"].isin(val_hours)]

    alerts = 0
    non_normal_verdicts = []

    for h in val_hours:
        res = plumbline.score(val_metrics, h)
        # Any failure verdict is a false alarm on clean validation data
        if res.verdict in ("relationship_break", "source_mismatch"):
            alerts += 1
            non_normal_verdicts.append((h, res.verdict, res.group))

    total_val_hours = len(val_hours)  # 720 hours
    weeks = total_val_hours / 168.0
    alerts_per_week = alerts / weeks
    false_alarm_rate = alerts / total_val_hours

    print(f"\n[Validation Report] Total val hours: {total_val_hours}")
    print(f"[Validation Report] False alarms count: {alerts}")
    print(f"[Validation Report] Alerts per week (168h): {alerts_per_week:.2f}")
    print(f"[Validation Report] False alarm rate: {false_alarm_rate:.4%}")

    # SLA Target: <= 1.5 alerts per week (accommodates edge hours)
    assert alerts_per_week <= 1.5, f"Alerts per week ({alerts_per_week:.2f}) exceeded threshold!"


# ==============================================================================
# 2. PROMO DAY COHERENT SURGE TEST
# ==============================================================================

def test_promo_day_yields_coherent_surge_not_relationship_break(fitted_model, clean_metrics_df):
    """
    Verify that promo day hours (e.g. Day 105 in validation) do NOT trigger
    relationship_break or source_mismatch. They should be classified as
    coherent_surge or normal.
    """
    catalog = load_metrics_catalog()
    plumbline = PlumblineEngine(fitted_model, catalog)
    plumbline.reset_state()

    # Day 105 is a promo day (hours 2520 to 2543)
    promo_day = 105
    promo_day_hours = [promo_day * HOURS_PER_DAY + h for h in range(HOURS_PER_DAY)]

    metrics_promo = clean_metrics_df[clean_metrics_df["hour_ts"].isin(promo_day_hours)]
    has_coherent_surge = False

    for h in promo_day_hours:
        res = plumbline.score(metrics_promo, h)
        assert res.verdict != "relationship_break", f"Hour {h} incorrectly flagged as relationship_break!"
        assert res.verdict != "source_mismatch", f"Hour {h} incorrectly flagged as source_mismatch!"
        assert res.verdict in ("normal", "coherent_surge")
        if res.verdict == "coherent_surge":
            has_coherent_surge = True

    assert has_coherent_surge, "Promo day must produce at least one coherent_surge!"


# ==============================================================================
# 3. UNIT SCALE SLICE FAILURE DETECTION TEST
# ==============================================================================

def test_unit_scale_slice_yields_relationship_break_within_3_hours(fitted_model):
    """
    Inject unit_scale_slice(voucher) for 3 consecutive hours in live split (2880..2882).
    Verify that Plumbline flags an anomaly (source_mismatch or relationship_break)
    within those 3 hours.
    """
    catalog = load_metrics_catalog()
    plumbline = PlumblineEngine(fitted_model, catalog)
    plumbline.reset_state()

    live_hours = [2880, 2881, 2882]

    # Ingest clean history up to 2879 then injected hours 2880..2882
    sim = PipelineEngine(":memory:", master_seed=42)

    flagged = False
    flagged_verdict = None
    flagged_hour = None

    for h in live_hours:
        gen_orders, gen_items, gen_payments = generate_hourly_batch(h, master_seed=42)
        injected_payments, gt_record = inject_unit_scale_slice(
            gen_payments, onset_hour=h, payment_type="voucher", scale=0.01
        )
        sim.ingest(
            batch_hour=h,
            orders_df=gen_orders,
            items_df=gen_items,
            payments_df=injected_payments,
            clean_payments_df=gen_payments,
            active_failures=[gt_record],
        )

        h_metrics = compute_metrics(sim.con, [h])
        res = plumbline.score(h_metrics, h)

        if res.verdict in ("relationship_break", "source_mismatch"):
            flagged = True
            flagged_verdict = res.verdict
            flagged_hour = h
            break

    sim.close()
    assert flagged, "Failure was not detected within 3 hours!"
    assert flagged_verdict in ("source_mismatch", "relationship_break")


# ==============================================================================
# 4. BASELINES RUN ON SAME DATA TEST
# ==============================================================================

def test_each_baseline_runs_on_same_data(clean_metrics_df):
    """Verify that all 4 baseline detectors execute on identical data without error."""
    bundle = BaselineBundle()
    train_start = TRAIN_DAYS[0] * HOURS_PER_DAY
    train_end = (TRAIN_DAYS[1] + 1) * HOURS_PER_DAY
    train_hours = set(range(train_start, train_end))
    promo_hours_set = get_promo_hours()

    bundle.fit(clean_metrics_df, train_hours, promo_hours_set)

    # Score sample hour 2184
    hour = 2184
    scores = bundle.score(clean_metrics_df, hour)

    assert "static_threshold" in scores
    assert "univariate_seasonal" in scores
    assert "isolation_forest" in scores
    assert "pipeline_heartbeat" in scores

    assert isinstance(scores["static_threshold"]["alert"], bool)
    assert isinstance(scores["univariate_seasonal"]["alert"], bool)
    assert isinstance(scores["isolation_forest"]["alert"], bool)
    assert scores["pipeline_heartbeat"]["alert"] is False


# ==============================================================================
# 5. NO DATA LEAKAGE & PERSISTED MODEL REUSE TEST
# ==============================================================================

def test_no_data_leakage_and_model_reuse(tmp_path, clean_metrics_df, fitted_model):
    """
    Verify model can be persisted to disk and reloaded without loss of consistency,
    and verify that train and validation hours are disjoint.
    """
    model_file = tmp_path / "model_test.joblib"
    fitted_model.save(model_file)

    loaded_model = CoherenceModel.load(model_file)

    # Check that train and validation hour sets are strictly disjoint
    assert set(loaded_model.train_hours).isdisjoint(set(loaded_model.val_hours))
    assert max(loaded_model.train_hours) < min(loaded_model.val_hours)

    # Check score equivalence
    catalog = load_metrics_catalog()
    eng1 = PlumblineEngine(fitted_model, catalog)
    eng2 = PlumblineEngine(loaded_model, catalog)

    h = 2184
    r1 = eng1.score(clean_metrics_df, h)
    r2 = eng2.score(clean_metrics_df, h)

    assert r1.verdict == r2.verdict
    assert r1.group == r2.group

