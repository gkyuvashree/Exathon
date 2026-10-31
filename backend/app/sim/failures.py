"""Failure Injectors and Hard Negatives for Simulated E-Commerce Pipeline."""

import uuid
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd


def make_ground_truth_record(
    failure_type: str,
    stage: str,
    onset_hour: int,
    end_hour: int,
    slice_info: Any,
    severity: Any,
    custom_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a standardized ground-truth record."""
    record_id = custom_id or f"{failure_type}_{onset_hour}_{uuid.uuid4().hex[:6]}"
    return {
        "id": record_id,
        "type": failure_type,
        "stage": stage,
        "onset_hour": onset_hour,
        "end_hour": end_hour,
        "slice": slice_info,
        "severity": severity,
    }


# ==============================================================================
# 9 FAILURE INJECTORS
# ==============================================================================

def inject_unit_scale_slice(
    payments_df: pd.DataFrame,
    onset_hour: int,
    end_hour: Optional[int] = None,
    payment_type: str = "voucher",
    scale: float = 0.01,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    1. unit_scale_slice: In raw_payments, payment_value x0.01 for a payment_type.
    """
    df = payments_df.copy()
    end = end_hour if end_hour is not None else onset_hour
    mask = df["payment_type"] == payment_type
    df.loc[mask, "payment_value"] = np.round(df.loc[mask, "payment_value"] * scale, 2)

    gt = make_ground_truth_record(
        failure_type="unit_scale_slice",
        stage="raw_payments",
        onset_hour=onset_hour,
        end_hour=end,
        slice_info={"payment_type": payment_type, "scale": scale},
        severity=scale,
    )
    return df, gt


def inject_partial_load(
    target_df: pd.DataFrame,
    table_name: str,
    onset_hour: int,
    end_hour: Optional[int] = None,
    drop_ratio: float = 0.35,
    seed: int = 101,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    2. partial_load: Drop X% of rows in one raw table.
    """
    df = target_df.copy()
    end = end_hour if end_hour is not None else onset_hour
    if len(df) > 0 and drop_ratio > 0.0:
        rng = np.random.default_rng(seed + onset_hour)
        keep_mask = rng.uniform(0.0, 1.0, size=len(df)) >= drop_ratio
        df = df[keep_mask].reset_index(drop=True)

    gt = make_ground_truth_record(
        failure_type="partial_load",
        stage=f"raw_{table_name}" if not table_name.startswith("raw_") else table_name,
        onset_hour=onset_hour,
        end_hour=end,
        slice_info={"table": table_name, "drop_ratio": drop_ratio},
        severity=drop_ratio,
    )
    return df, gt


def inject_duplicate_replay(
    current_payments_df: pd.DataFrame,
    previous_payments_df: pd.DataFrame,
    onset_hour: int,
    end_hour: Optional[int] = None,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    3. duplicate_replay: Re-insert previous hour's payments into current hour.
    """
    end = end_hour if end_hour is not None else onset_hour
    replayed = previous_payments_df.copy()
    replayed["batch_hour"] = onset_hour
    df = pd.concat([current_payments_df, replayed], ignore_index=True)

    gt = make_ground_truth_record(
        failure_type="duplicate_replay",
        stage="raw_payments",
        onset_hour=onset_hour,
        end_hour=end,
        slice_info={"table": "raw_payments", "replayed_count": len(replayed)},
        severity=float(len(replayed)) / max(len(current_payments_df), 1),
    )
    return df, gt


def inject_stale_source(
    orders_df: pd.DataFrame,
    onset_hour: int,
    k_hours: int = 2,
    current_hour: Optional[int] = None,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    4. stale_source: raw_orders gets no new rows for k hours.
    """
    cur = current_hour if current_hour is not None else onset_hour
    end = onset_hour + k_hours - 1
    # Returns empty dataframe for orders during the stale window
    df = orders_df.iloc[0:0].copy()

    gt = make_ground_truth_record(
        failure_type="stale_source",
        stage="raw_orders",
        onset_hour=onset_hour,
        end_hour=end,
        slice_info={"table": "raw_orders", "duration_hours": k_hours},
        severity=k_hours,
    )
    return df, gt


def inject_schema_drift_nulls(
    target_df: pd.DataFrame,
    table_name: str,
    column_name: str,
    onset_hour: int,
    end_hour: Optional[int] = None,
    null_ratio: float = 0.50,
    seed: int = 202,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    5. schema_drift_nulls: A column becomes null for X% of rows.
    """
    df = target_df.copy()
    end = end_hour if end_hour is not None else onset_hour
    if column_name in df.columns and len(df) > 0:
        rng = np.random.default_rng(seed + onset_hour)
        null_mask = rng.uniform(0.0, 1.0, size=len(df)) < null_ratio
        df.loc[null_mask, column_name] = None

    gt = make_ground_truth_record(
        failure_type="schema_drift_nulls",
        stage=f"raw_{table_name}" if not table_name.startswith("raw_") else table_name,
        onset_hour=onset_hour,
        end_hour=end,
        slice_info={"table": table_name, "column": column_name, "null_ratio": null_ratio},
        severity=null_ratio,
    )
    return df, gt


def inject_default_fill(
    items_df: pd.DataFrame,
    onset_hour: int,
    end_hour: Optional[int] = None,
    target_column: str = "freight",
    fill_ratio: float = 0.60,
    seed: int = 303,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    6. default_fill: Nulls -> 0.0 in freight (or default 0-fill replacing values).
    """
    df = items_df.copy()
    end = end_hour if end_hour is not None else onset_hour
    if target_column in df.columns and len(df) > 0:
        rng = np.random.default_rng(seed + onset_hour)
        zero_mask = rng.uniform(0.0, 1.0, size=len(df)) < fill_ratio
        df.loc[zero_mask, target_column] = 0.0

    gt = make_ground_truth_record(
        failure_type="default_fill",
        stage="raw_items",
        onset_hour=onset_hour,
        end_hour=end,
        slice_info={"table": "raw_items", "column": target_column, "default_value": 0.0, "fill_ratio": fill_ratio},
        severity=fill_ratio,
    )
    return df, gt


def inject_timezone_shift(
    target_df: pd.DataFrame,
    table_name: str,
    onset_hour: int,
    end_hour: Optional[int] = None,
    shift_hours: float = 5.5,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    7. timezone_shift: event_ts shifted by +5.5 hours.
    """
    df = target_df.copy()
    end = end_hour if end_hour is not None else onset_hour
    if "event_ts" in df.columns:
        df["event_ts"] = pd.to_datetime(df["event_ts"]) + pd.Timedelta(hours=shift_hours)

    gt = make_ground_truth_record(
        failure_type="timezone_shift",
        stage=f"raw_{table_name}" if not table_name.startswith("raw_") else table_name,
        onset_hour=onset_hour,
        end_hour=end,
        slice_info={"table": table_name, "shift_hours": shift_hours},
        severity=shift_hours,
    )
    return df, gt


def inject_orphan_keys(
    target_df: pd.DataFrame,
    table_name: str,
    onset_hour: int,
    end_hour: Optional[int] = None,
    corruption_ratio: float = 0.30,
    seed: int = 404,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    8. orphan_keys: order_ids in items or payments corrupted so they don't match orders.
    """
    df = target_df.copy()
    end = end_hour if end_hour is not None else onset_hour
    if "order_id" in df.columns and len(df) > 0:
        rng = np.random.default_rng(seed + onset_hour)
        corrupt_mask = rng.uniform(0.0, 1.0, size=len(df)) < corruption_ratio
        df.loc[corrupt_mask, "order_id"] = [
            f"ORPHAN_{uuid.UUID(int=int(rng.integers(0, 2**63))).hex[:10]}"
            for _ in range(int(np.sum(corrupt_mask)))
        ]

    gt = make_ground_truth_record(
        failure_type="orphan_keys",
        stage=f"raw_{table_name}" if not table_name.startswith("raw_") else table_name,
        onset_hour=onset_hour,
        end_hour=end,
        slice_info={"table": table_name, "corruption_ratio": corruption_ratio},
        severity=corruption_ratio,
    )
    return df, gt


def inject_join_fanout_flag(
    onset_hour: int,
    end_hour: Optional[int] = None,
) -> Dict[str, Any]:
    """
    9. join_fanout: TRANSFORM-level bug at int_order_totals joining unaggregated items.
    Returns the ground truth descriptor to pass to pipeline ingestion.
    """
    end = end_hour if end_hour is not None else onset_hour
    return make_ground_truth_record(
        failure_type="join_fanout",
        stage="int_order_totals",
        onset_hour=onset_hour,
        end_hour=end,
        slice_info={"stage": "int_order_totals", "join_type": "unaggregated_items_fanout"},
        severity=1.0,
    )


# ==============================================================================
# HARD NEGATIVES (Legitimate Business Changes, NOT Pipeline Failures)
# ==============================================================================

def inject_promo_surge(
    onset_hour: int,
    end_hour: Optional[int] = None,
    multiplier: float = 2.5,
) -> Dict[str, Any]:
    """
    Hard Negative 1: promo_surge (x2.5 all volume, coherent).
    """
    end = end_hour if end_hour is not None else onset_hour
    return make_ground_truth_record(
        failure_type="promo_surge",
        stage="domain_generation",
        onset_hour=onset_hour,
        end_hour=end,
        slice_info={"all_volume_multiplier": multiplier},
        severity=multiplier,
    )


def inject_category_flash_sale(
    onset_hour: int,
    end_hour: Optional[int] = None,
    category: str = "electronics",
    multiplier: float = 3.0,
) -> Dict[str, Any]:
    """
    Hard Negative 2: category_flash_sale (one category x3, coherent).
    """
    end = end_hour if end_hour is not None else onset_hour
    return make_ground_truth_record(
        failure_type="category_flash_sale",
        stage="domain_generation",
        onset_hour=onset_hour,
        end_hour=end,
        slice_info={"category": category, "multiplier": multiplier},
        severity=multiplier,
    )
