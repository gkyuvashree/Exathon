"""
Scenario Generator for Seeded 48-Hour Evaluation Scenarios.

Generates 48-hour scenarios across:
  - Clean operation
  - 2 Hard negatives (promo_surge, category_flash_sale)
  - 9 Injected failure types
Using parameters from config/eval_ranges.yaml.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
import yaml

from app.sim.config import CATEGORIES, HOURS_PER_DAY, PAYMENT_TYPES, STATES
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


def load_eval_ranges_config() -> Dict[str, Any]:
    """Load config/eval_ranges.yaml."""
    candidates = [
        Path("config/eval_ranges.yaml"),
        Path("backend/config/eval_ranges.yaml"),
        Path(__file__).resolve().parent.parent.parent.parent / "config" / "eval_ranges.yaml",
        Path(__file__).resolve().parent.parent.parent / "config" / "eval_ranges.yaml",
    ]
    for c in candidates:
        if c.exists():
            with open(c, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
    raise FileNotFoundError("Could not find config/eval_ranges.yaml")


class ScenarioGenerator:
    """Generates deterministic 48-hour batches with optional failure injection."""
    def __init__(self, split: str = "dev"):
        self.split = split.lower()
        self.config = load_eval_ranges_config()
        self.split_cfg = self.config[self.split]
        self.ranges = self.split_cfg["ranges"]
        self.duration_hours = self.config.get("scenario_duration_hours", 48)
        self.warmup_hours = self.config.get("warmup_hours", 12)
        self.failure_duration = self.config.get("failure_duration_hours", 12)

    def generate_scenario(
        self,
        scenario_type: str,
        seed: int,
    ) -> Dict[str, Any]:
        """
        Generates 48 hours of orders, items, payments with deterministic seed.
        Returns scenario metadata, ground truth records, and hourly batches.
        """
        rng = np.random.default_rng(seed)
        scenario_id = f"{self.split}_{scenario_type}_seed{seed}"

        is_failure = scenario_type in self.config["failure_types"]
        is_hard_negative = scenario_type in self.config["hard_negatives"]

        onset_hour = self.warmup_hours if (is_failure or is_hard_negative) else None
        end_hour = (self.warmup_hours + self.failure_duration - 1) if (is_failure or is_hard_negative) else None

        hourly_data: List[Dict[str, Any]] = []
        gt_record: Optional[Dict[str, Any]] = None

        # Sample scenario parameters
        param_dict: Dict[str, Any] = {}
        if scenario_type == "unit_scale_slice":
            cfg = self.ranges["unit_scale_slice"]
            ptype = str(rng.choice(cfg["payment_types"]))
            scale = float(rng.uniform(cfg["scale"][0], cfg["scale"][1]))
            param_dict = {"payment_type": ptype, "scale": scale}

        elif scenario_type == "partial_load":
            cfg = self.ranges["partial_load"]
            table = str(rng.choice(cfg["tables"]))
            drop = float(rng.uniform(cfg["drop_ratio"][0], cfg["drop_ratio"][1]))
            param_dict = {"table": table, "drop_ratio": drop}

        elif scenario_type == "duplicate_replay":
            param_dict = {"table": "payments"}

        elif scenario_type == "stale_source":
            cfg = self.ranges["stale_source"]
            k_hrs = int(rng.integers(cfg["k_hours"][0], cfg["k_hours"][1] + 1))
            param_dict = {"k_hours": k_hrs}
            end_hour = self.warmup_hours + k_hrs - 1

        elif scenario_type == "schema_drift_nulls":
            cfg = self.ranges["schema_drift_nulls"]
            tbl = str(rng.choice(list(cfg["columns"].keys())))
            col = str(rng.choice(cfg["columns"][tbl]))
            n_ratio = float(rng.uniform(cfg["null_ratio"][0], cfg["null_ratio"][1]))
            param_dict = {"table": tbl, "column": col, "null_ratio": n_ratio}

        elif scenario_type == "default_fill":
            cfg = self.ranges["default_fill"]
            fill_r = float(rng.uniform(cfg["fill_ratio"][0], cfg["fill_ratio"][1]))
            param_dict = {"target_column": cfg["target_column"], "fill_ratio": fill_r}

        elif scenario_type == "timezone_shift":
            cfg = self.ranges["timezone_shift"]
            tbl = str(rng.choice(cfg["tables"]))
            shift = float(rng.uniform(cfg["shift_hours"][0], cfg["shift_hours"][1]))
            param_dict = {"table": tbl, "shift_hours": shift}

        elif scenario_type == "orphan_keys":
            cfg = self.ranges["orphan_keys"]
            tbl = str(rng.choice(cfg["tables"]))
            corr = float(rng.uniform(cfg["corruption_ratio"][0], cfg["corruption_ratio"][1]))
            param_dict = {"table": tbl, "corruption_ratio": corr}

        elif scenario_type == "join_fanout":
            param_dict = {"severity": 1.0}

        elif scenario_type == "promo_surge":
            cfg = self.ranges["promo_surge"]
            mult = float(rng.uniform(cfg["multiplier"][0], cfg["multiplier"][1]))
            param_dict = {"multiplier": mult}

        elif scenario_type == "category_flash_sale":
            cfg = self.ranges["category_flash_sale"]
            cat = str(rng.choice(cfg["categories"]))
            mult = float(rng.uniform(cfg["multiplier"][0], cfg["multiplier"][1]))
            param_dict = {"category": cat, "multiplier": mult}

        # Generate each hour across 0..47
        prev_payments = None
        for h in range(self.duration_hours):
            # Base generation with master seed
            # In live evaluation, offset base hour to live range (e.g. 2880 + h)
            eval_hour_ts = 2880 + h
            orders_df, items_df, payments_df = generate_hourly_batch(eval_hour_ts, master_seed=seed)

            # Store clean copies
            c_orders = orders_df.copy()
            c_items = items_df.copy()
            c_payments = payments_df.copy()
            active_failures: List[Dict[str, Any]] = []

            # Check if hour is within the failure / hard-negative active window
            in_window = (onset_hour is not None and end_hour is not None and onset_hour <= h <= end_hour)

            if in_window:
                if scenario_type == "unit_scale_slice":
                    payments_df, gt = inject_unit_scale_slice(
                        payments_df, onset_hour=onset_hour, end_hour=end_hour,
                        payment_type=param_dict["payment_type"], scale=param_dict["scale"]
                    )
                    active_failures.append(gt)

                elif scenario_type == "partial_load":
                    target_tbl = param_dict["table"]
                    if target_tbl == "orders":
                        orders_df, gt = inject_partial_load(orders_df, "orders", onset_hour, end_hour, param_dict["drop_ratio"], seed=seed)
                    elif target_tbl == "items":
                        items_df, gt = inject_partial_load(items_df, "items", onset_hour, end_hour, param_dict["drop_ratio"], seed=seed)
                    else:
                        payments_df, gt = inject_partial_load(payments_df, "payments", onset_hour, end_hour, param_dict["drop_ratio"], seed=seed)
                    active_failures.append(gt)

                elif scenario_type == "duplicate_replay":
                    if prev_payments is not None:
                        payments_df, gt = inject_duplicate_replay(payments_df, prev_payments, onset_hour, end_hour)
                        active_failures.append(gt)

                elif scenario_type == "stale_source":
                    orders_df, gt = inject_stale_source(orders_df, onset_hour=onset_hour, k_hours=param_dict["k_hours"], current_hour=h)
                    active_failures.append(gt)

                elif scenario_type == "schema_drift_nulls":
                    tbl = param_dict["table"]
                    col = param_dict["column"]
                    nr = param_dict["null_ratio"]
                    if tbl == "orders":
                        orders_df, gt = inject_schema_drift_nulls(orders_df, tbl, col, onset_hour, end_hour, nr, seed=seed)
                    elif tbl == "items":
                        items_df, gt = inject_schema_drift_nulls(items_df, tbl, col, onset_hour, end_hour, nr, seed=seed)
                    else:
                        payments_df, gt = inject_schema_drift_nulls(payments_df, tbl, col, onset_hour, end_hour, nr, seed=seed)
                    active_failures.append(gt)

                elif scenario_type == "default_fill":
                    items_df, gt = inject_default_fill(items_df, target_column=param_dict["target_column"], onset_hour=onset_hour, end_hour=end_hour, fill_ratio=param_dict["fill_ratio"], seed=seed)
                    active_failures.append(gt)

                elif scenario_type == "timezone_shift":
                    tbl = param_dict["table"]
                    shift = param_dict["shift_hours"]
                    if tbl == "orders":
                        orders_df, gt = inject_timezone_shift(orders_df, tbl, onset_hour, end_hour, shift)
                    elif tbl == "items":
                        items_df, gt = inject_timezone_shift(items_df, tbl, onset_hour, end_hour, shift)
                    else:
                        payments_df, gt = inject_timezone_shift(payments_df, tbl, onset_hour, end_hour, shift)
                    active_failures.append(gt)

                elif scenario_type == "orphan_keys":
                    tbl = param_dict["table"]
                    corr = param_dict["corruption_ratio"]
                    if tbl == "items":
                        items_df, gt = inject_orphan_keys(items_df, tbl, onset_hour, end_hour, corr, seed=seed)
                    else:
                        payments_df, gt = inject_orphan_keys(payments_df, tbl, onset_hour, end_hour, corr, seed=seed)
                    active_failures.append(gt)

                elif scenario_type == "join_fanout":
                    gt = inject_join_fanout_flag(onset_hour, end_hour)
                    active_failures.append(gt)

                elif scenario_type == "promo_surge":
                    gt = inject_promo_surge(onset_hour, end_hour, param_dict["multiplier"])
                    active_failures.append(gt)
                    # Multiply volume coherently
                    mult = param_dict["multiplier"]
                    # Add extra synthetic rows proportional to mult
                    extra_orders, extra_items, extra_payments = generate_hourly_batch(eval_hour_ts + 10000, master_seed=seed + h)
                    n_extra = int(len(orders_df) * (mult - 1.0))
                    orders_df = pd.concat([orders_df, extra_orders.iloc[:n_extra]], ignore_index=True)
                    items_df = pd.concat([items_df, extra_items.iloc[:int(len(items_df) * (mult - 1.0))]], ignore_index=True)
                    payments_df = pd.concat([payments_df, extra_payments.iloc[:int(len(payments_df) * (mult - 1.0))]], ignore_index=True)

                elif scenario_type == "category_flash_sale":
                    cat = param_dict["category"]
                    mult = param_dict["multiplier"]
                    gt = inject_category_flash_sale(onset_hour, end_hour, cat, mult)
                    active_failures.append(gt)
                    # Scale price or count for this category
                    mask = items_df["category"] == cat
                    if mask.any():
                        extra_items = items_df[mask].sample(frac=mult - 1.0, replace=True, random_state=seed + h)
                        items_df = pd.concat([items_df, extra_items], ignore_index=True)

            prev_payments = payments_df.copy()

            hourly_data.append({
                "hour_idx": h,
                "hour_ts": eval_hour_ts,
                "orders_df": orders_df,
                "items_df": items_df,
                "payments_df": payments_df,
                "clean_orders_df": c_orders,
                "clean_items_df": c_items,
                "clean_payments_df": c_payments,
                "active_failures": active_failures,
            })

        return {
            "scenario_id": scenario_id,
            "scenario_type": scenario_type,
            "seed": seed,
            "is_failure": is_failure,
            "is_hard_negative": is_hard_negative,
            "onset_hour": onset_hour,
            "end_hour": end_hour,
            "params": param_dict,
            "hourly_data": hourly_data,
        }
