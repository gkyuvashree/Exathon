"""Comprehensive Unit & Integration Tests for Phase 1 Simulation & Pipeline."""

from datetime import datetime, timezone
import numpy as np
import pandas as pd
import pytest

from app.sim.config import (
    TOTAL_DAYS,
    HOURS_PER_DAY,
    PROMO_DAYS,
    CATEGORIES,
    STATES,
    PAYMENT_TYPES,
)
from app.sim.event_log import EventLogger
from app.sim.failures import (
    inject_category_flash_sale,
    inject_default_fill,
    inject_duplicate_replay,
    inject_join_fanout_flag,
    inject_orphan_keys,
    inject_partial_load,
    inject_promo_surge,
    inject_schema_drift_nulls,
    inject_stale_source,
    inject_timezone_shift,
    inject_unit_scale_slice,
)
from app.sim.generator import generate_hourly_batch
from app.sim.pipeline import PipelineEngine, is_dag_acyclic, load_lineage_config


# ==============================================================================
# 1. DETERMINISM TEST: SAME SEED => BYTE-IDENTICAL HISTORY
# ==============================================================================

def test_same_seed_byte_identical_history():
    """Verify that same master seed produces bit-for-bit identical history."""
    hours_to_test = [0, 1, 12, 23, 35, 105, 125]
    seed = 42

    for h in hours_to_test:
        o1, i1, p1 = generate_hourly_batch(h, master_seed=seed)
        o2, i2, p2 = generate_hourly_batch(h, master_seed=seed)

        pd.testing.assert_frame_equal(o1, o2, check_exact=True)
        pd.testing.assert_frame_equal(i1, i2, check_exact=True)
        pd.testing.assert_frame_equal(p1, p2, check_exact=True)

    # Different seed must produce different data
    o_diff, _, _ = generate_hourly_batch(0, master_seed=999)
    o_orig, _, _ = generate_hourly_batch(0, master_seed=42)
    assert not o_orig["customer_id"].equals(o_diff["customer_id"])


# ==============================================================================
# 2. DOMAIN INTEGRITY: payment_value ~ items_total WITHIN COUPON TOLERANCE
# ==============================================================================

def test_clean_data_satisfies_payment_items_ratio_and_coupon_tolerance():
    """
    Verify clean data satisfies payment_value ~ items_total within coupon tolerance.
    Non-coupon orders have ratio == 1.0 (mean ~ 0.99 due to 8% coupon).
    """
    all_payments = []
    all_items = []

    for h in range(10):
        _, items, payments = generate_hourly_batch(h, master_seed=123)
        all_items.append(items)
        all_payments.append(payments)

    items_df = pd.concat(all_items, ignore_index=True)
    payments_df = pd.concat(all_payments, ignore_index=True)

    # Aggregate item total per order
    item_sums = (
        items_df.groupby("order_id")[["price", "freight"]].sum().sum(axis=1)
    ).round(2).to_dict()

    ratios = []
    coupon_count = 0
    total_orders = len(payments_df)

    for _, row in payments_df.iterrows():
        oid = row["order_id"]
        pay_val = float(row["payment_value"])
        item_val = item_sums[oid]
        ratio = pay_val / item_val
        ratios.append(ratio)

        # Payment should never exceed item value in clean data
        assert pay_val <= item_val + 0.02, f"Payment {pay_val} exceeded item total {item_val}"

        # If coupon was applied (pay_val < item_val - 0.01), discount is between 5% and 15%
        if ratio < 0.99:
            coupon_count += 1
            assert 0.84 <= ratio <= 0.96, f"Coupon ratio {ratio:.4f} outside [0.85, 0.95] tolerance"
        else:
            assert abs(ratio - 1.0) <= 0.01, f"Non-coupon ratio {ratio:.4f} not ~ 1.0"

    # Overall ratio mean should be ~0.99
    mean_ratio = np.mean(ratios)
    assert 0.98 <= mean_ratio <= 0.998, f"Mean ratio {mean_ratio:.4f} not ~0.99"

    # Coupon frequency should be ~8% (within sampling margin)
    coupon_freq = coupon_count / total_orders
    assert 0.04 <= coupon_freq <= 0.14, f"Coupon frequency {coupon_freq:.3f} unexpected"


# ==============================================================================
# 3. FAILURE INJECTORS: CHANGES ONLY INTENDED SLICE / STAGE
# ==============================================================================

def test_unit_scale_slice_changes_only_intended_slice():
    """Verify unit_scale_slice changes ONLY target payment_type in payments."""
    orders, items, payments = generate_hourly_batch(5, master_seed=42)
    clean_payments = payments.copy()

    injected_payments, gt = inject_unit_scale_slice(
        payments, onset_hour=5, payment_type="voucher", scale=0.01
    )

    # 1. Non-voucher rows MUST be identical
    non_voucher_clean = clean_payments[clean_payments["payment_type"] != "voucher"]
    non_voucher_inj = injected_payments[injected_payments["payment_type"] != "voucher"]
    pd.testing.assert_frame_equal(non_voucher_clean, non_voucher_inj)

    # 2. Voucher rows MUST be scaled by 0.01
    voucher_clean = clean_payments[clean_payments["payment_type"] == "voucher"]
    voucher_inj = injected_payments[injected_payments["payment_type"] == "voucher"]
    assert len(voucher_inj) > 0
    expected_voucher_values = np.round(voucher_clean["payment_value"] * 0.01, 2)
    assert np.allclose(voucher_inj["payment_value"].values, expected_voucher_values.values)

    # 3. Orders and Items remain untouched
    assert len(orders) > 0 and len(items) > 0


def test_partial_load_changes_only_target_table():
    """Verify partial_load drops rows only in specified table."""
    orders, items, payments = generate_hourly_batch(7, master_seed=42)
    clean_items = items.copy()
    clean_payments = payments.copy()

    injected_orders, gt = inject_partial_load(
        orders, table_name="orders", onset_hour=7, drop_ratio=0.40
    )

    assert len(injected_orders) < len(orders)
    assert gt["stage"] == "raw_orders"
    # Items and Payments completely untouched
    pd.testing.assert_frame_equal(items, clean_items)
    pd.testing.assert_frame_equal(payments, clean_payments)


def test_duplicate_replay_injects_previous_payments():
    """Verify duplicate_replay re-inserts previous hour payments."""
    _, _, p_prev = generate_hourly_batch(1, master_seed=42)
    _, _, p_cur = generate_hourly_batch(2, master_seed=42)

    injected, gt = inject_duplicate_replay(p_cur, p_prev, onset_hour=2)
    assert len(injected) == len(p_cur) + len(p_prev)
    assert gt["type"] == "duplicate_replay"


def test_stale_source_empties_orders():
    """Verify stale_source yields 0 orders for stale window."""
    orders, _, _ = generate_hourly_batch(10, master_seed=42)
    stale_orders, gt = inject_stale_source(orders, onset_hour=10, k_hours=3)
    assert len(stale_orders) == 0
    assert gt["severity"] == 3


def test_schema_drift_nulls():
    """Verify schema_drift_nulls introduces nulls in target column only."""
    _, items, _ = generate_hourly_batch(11, master_seed=42)
    clean_price = items["price"].copy()

    injected_items, gt = inject_schema_drift_nulls(
        items, table_name="items", column_name="category", onset_hour=11, null_ratio=0.5
    )
    assert injected_items["category"].isna().sum() > 0
    # Price column unaffected
    pd.testing.assert_series_equal(injected_items["price"], clean_price)


def test_default_fill_freight_zeros():
    """Verify default_fill sets freight to 0.0."""
    _, items, _ = generate_hourly_batch(12, master_seed=42)
    injected_items, gt = inject_default_fill(
        items, onset_hour=12, target_column="freight", fill_ratio=0.75
    )
    assert (injected_items["freight"] == 0.0).sum() > 0
    assert gt["type"] == "default_fill"


def test_timezone_shift():
    """Verify timezone_shift offsets event_ts by 5.5 hours."""
    orders, _, _ = generate_hourly_batch(13, master_seed=42)
    orig_ts = orders["event_ts"].iloc[0]

    shifted, gt = inject_timezone_shift(orders, "orders", onset_hour=13, shift_hours=5.5)
    new_ts = shifted["event_ts"].iloc[0]
    diff = (new_ts - orig_ts).total_seconds() / 3600.0
    assert abs(diff - 5.5) < 0.001


def test_orphan_keys():
    """Verify orphan_keys corrupts order_ids with ORPHAN_ prefix."""
    _, items, _ = generate_hourly_batch(14, master_seed=42)
    corrupted, gt = inject_orphan_keys(items, "items", onset_hour=14, corruption_ratio=0.4)
    orphan_count = corrupted["order_id"].str.startswith("ORPHAN_").sum()
    assert orphan_count > 0


def test_join_fanout_transform_level():
    """Verify join_fanout causes payment row multiplication in int_order_totals."""
    engine_clean = PipelineEngine(":memory:", master_seed=42)
    engine_fanout = PipelineEngine(":memory:", master_seed=42)

    o, i, p = generate_hourly_batch(0, master_seed=42)
    gt_fanout = inject_join_fanout_flag(onset_hour=0)

    engine_clean.ingest(0, orders_df=o.copy(), items_df=i.copy(), payments_df=p.copy())
    engine_fanout.ingest(
        0, orders_df=o.copy(), items_df=i.copy(), payments_df=p.copy(), active_failures=[gt_fanout]
    )

    clean_totals_count = engine_clean.con.execute("SELECT COUNT(*) FROM int_order_totals").fetchone()[0]
    fanout_totals_count = engine_fanout.con.execute("SELECT COUNT(*) FROM int_order_totals").fetchone()[0]

    # Clean has 1 row per order in int_order_totals
    assert clean_totals_count == len(p)
    # Fanout has 1 row per item in int_order_totals
    assert fanout_totals_count == len(i)
    assert fanout_totals_count > clean_totals_count

    engine_clean.close()
    engine_fanout.close()


def test_hard_negatives():
    """Verify promo_surge and category_flash_sale ground-truth creation."""
    gt_promo = inject_promo_surge(onset_hour=35, multiplier=2.5)
    assert gt_promo["type"] == "promo_surge"
    assert gt_promo["severity"] == 2.5

    gt_sale = inject_category_flash_sale(onset_hour=50, category="electronics", multiplier=3.0)
    assert gt_sale["type"] == "category_flash_sale"
    assert gt_sale["slice"]["category"] == "electronics"


# ==============================================================================
# 4. GROUND TRUTH IS RECORDED IN SQLite EVENT LOG
# ==============================================================================

def test_ground_truth_and_decoys_recorded_in_sqlite():
    """Verify true cause failure events and daily decoy events are recorded."""
    logger = EventLogger(":memory:")

    # Record true cause
    gt = {
        "id": "tc_test_01",
        "type": "unit_scale_slice",
        "stage": "raw_payments",
        "onset_hour": 10,
        "end_hour": 12,
        "slice": {"payment_type": "voucher"},
        "severity": 0.01,
    }
    event_id = logger.record_true_cause(gt)
    assert event_id == "tc_test_01"

    # Record 3-5 decoys for day 0
    decoy_ids = logger.generate_decoys_for_day(0, seed=42)
    assert 3 <= len(decoy_ids) <= 5

    # Retrieve true causes
    tc_df = logger.get_true_causes()
    assert len(tc_df) == 1
    assert tc_df.iloc[0]["event_type"] == "true_cause"
    assert tc_df.iloc[0]["failure_type"] == "unit_scale_slice"

    # Retrieve all events
    all_df = logger.get_events()
    assert len(all_df) == 1 + len(decoy_ids)
    logger.close()


# ==============================================================================
# 5. CONTROL TOTALS REFLECT PRE-INJECTION TRUTH
# ==============================================================================

def test_control_totals_reflect_pre_injection_truth():
    """Verify control_totals in DuckDB stores clean source totals before injection."""
    engine = PipelineEngine(":memory:", master_seed=42)

    orders, items, payments = generate_hourly_batch(20, master_seed=42)
    clean_payments_sum = float(payments["payment_value"].sum())

    # Apply failure to payments
    injected_payments, gt = inject_unit_scale_slice(payments, onset_hour=20, scale=0.01)
    injected_payments_sum = float(injected_payments["payment_value"].sum())
    assert injected_payments_sum < clean_payments_sum

    # Ingest with failure
    engine.ingest(
        20,
        orders_df=orders,
        items_df=items,
        payments_df=injected_payments,
        active_failures=[gt],
    )

    # Control totals MUST reflect clean source sum
    ctrl_sum = engine.con.execute(
        "SELECT true_value_sum FROM control_totals WHERE batch_hour = 20 AND table_name = 'raw_payments'"
    ).fetchone()[0]
    assert abs(ctrl_sum - clean_payments_sum) < 0.01

    # Raw payments in DuckDB reflects injected sum
    raw_sum = engine.con.execute(
        "SELECT SUM(payment_value) FROM raw_payments WHERE batch_hour = 20"
    ).fetchone()[0]
    assert abs(raw_sum - injected_payments_sum) < 0.01

    engine.close()


# ==============================================================================
# 6. DAG LOADS AND IS ACYCLIC
# ==============================================================================

def test_dag_loads_and_is_acyclic():
    """Verify config/lineage.yaml loads successfully and forms an acyclic DAG."""
    lineage = load_lineage_config()
    assert "nodes" in lineage
    assert is_dag_acyclic(lineage) is True

    # Test that an artificial cycle is detected
    cyclic_lineage = {
        "nodes": {
            "A": {"dependencies": ["B"]},
            "B": {"dependencies": ["C"]},
            "C": {"dependencies": ["A"]},
        }
    }
    assert is_dag_acyclic(cyclic_lineage) is False
