"""
Unit tests validating Phase 4 metric calculations.
Hand-built test verifying Precision, Recall, F1, Delay, and False Alarm rates.
"""

import pytest
from app.eval.metrics import (
    ScenarioEvaluationResult,
    bootstrap_metric_ci,
    calculate_scenario_metrics,
    compute_aggregate_metrics,
)


def test_handbuilt_scenario_metrics():
    """Verify precision, recall, F1, delay and FA on a deterministic hand-built scenario set."""
    # Scenario 1: True Positive (detected at hour 14 with onset 12 -> delay 2h)
    s1 = ScenarioEvaluationResult(
        scenario_id="s1",
        scenario_type="unit_scale_slice",
        is_failure=True,
        is_hard_negative=False,
        onset_hour=12,
        end_hour=23,
        alerts_by_hour=[(h, h == 14) for h in range(48)],
        detected=True,
        delay_hours=2.0,
        false_alarms_in_clean_window=0,
    )

    # Scenario 2: False Negative (failure at hour 12..23, never alerted)
    s2 = ScenarioEvaluationResult(
        scenario_id="s2",
        scenario_type="unit_scale_slice",
        is_failure=True,
        is_hard_negative=False,
        onset_hour=12,
        end_hour=23,
        alerts_by_hour=[(h, False) for h in range(48)],
        detected=False,
        delay_hours=None,
        false_alarms_in_clean_window=0,
    )

    # Scenario 3: Clean scenario with 0 alerts (True Negative)
    s3 = ScenarioEvaluationResult(
        scenario_id="s3",
        scenario_type="clean",
        is_failure=False,
        is_hard_negative=False,
        onset_hour=None,
        end_hour=None,
        alerts_by_hour=[(h, False) for h in range(48)],
        detected=False,
        delay_hours=None,
        false_alarms_in_clean_window=0,
    )

    # Scenario 4: Hard Negative with an alert (False Positive event)
    s4 = ScenarioEvaluationResult(
        scenario_id="s4",
        scenario_type="promo_surge",
        is_failure=False,
        is_hard_negative=True,
        onset_hour=12,
        end_hour=23,
        alerts_by_hour=[(h, h == 15) for h in range(48)],
        detected=False,
        delay_hours=None,
        false_alarms_in_clean_window=1,
    )

    scenarios = [s1, s2, s3, s4]
    metrics = compute_aggregate_metrics(scenarios)

    # TP = 1 (s1), FN = 1 (s2), FP = 1 (s4 alert)
    # Recall = TP / (TP + FN) = 1 / 2 = 0.50
    assert metrics["event_recall"] == 0.50
    assert metrics["total_failures"] == 2
    assert metrics["detected_failures"] == 1

    # Precision = TP / (TP + FP) = 1 / (1 + 1) = 0.50
    assert metrics["event_precision"] == 0.50

    # F1 = 2 * (0.5 * 0.5) / (0.5 + 0.5) = 0.50
    assert metrics["event_f1"] == 0.50

    # Detection delay for s1 is 2.0
    assert metrics["mean_delay_hours"] == 2.0
    assert metrics["median_delay_hours"] == 2.0

    # Hard-negative FPR = 1 alerted out of 1 hard negative = 1.0 (100%)
    assert metrics["hard_negative_fpr"] == 1.0


def test_bootstrap_ci_execution():
    """Verify bootstrap confidence interval computation executes and yields valid ranges."""
    s1 = ScenarioEvaluationResult(
        scenario_id="s1",
        scenario_type="partial_load",
        is_failure=True,
        is_hard_negative=False,
        onset_hour=12,
        end_hour=23,
        alerts_by_hour=[(h, h >= 13) for h in range(48)],
        detected=True,
        delay_hours=1.0,
        false_alarms_in_clean_window=0,
    )
    s2 = ScenarioEvaluationResult(
        scenario_id="s2",
        scenario_type="clean",
        is_failure=False,
        is_hard_negative=False,
        onset_hour=None,
        end_hour=None,
        alerts_by_hour=[(h, False) for h in range(48)],
        detected=False,
        delay_hours=None,
        false_alarms_in_clean_window=0,
    )

    ci = bootstrap_metric_ci([s1, s2], n_resamples=50, seed=42)
    assert "precision_ci" in ci
    assert "recall_ci" in ci
    assert "f1_ci" in ci
    assert ci["precision_ci"][0] <= ci["precision_ci"][1]
    assert ci["recall_ci"][0] <= ci["recall_ci"][1]
