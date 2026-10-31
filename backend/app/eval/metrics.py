"""
Metric Calculation Engine for Phase 4 Evaluation.

Calculates:
  - Event-level Precision, Recall, F1 (per failure type and overall)
  - Detection delay (hours from onset to first true positive alert)
  - False alarms per week (168 hours of clean operation)
  - Hard-negative False Positive Rate (FPR)
  - Bootstrap 95% Confidence Intervals (1000 resamples)
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import numpy as np


@dataclass
class ScenarioEvaluationResult:
    scenario_id: str
    scenario_type: str        # "clean", failure_name, or hard_negative_name
    is_failure: bool
    is_hard_negative: bool
    onset_hour: Optional[int]
    end_hour: Optional[int]
    alerts_by_hour: List[Tuple[int, bool]]  # List of (hour, alerted_bool)
    detected: bool = False
    delay_hours: Optional[float] = None
    false_alarms_in_clean_window: int = 0


def calculate_scenario_metrics(
    result: ScenarioEvaluationResult,
    clean_warmup_hours: int = 12,
) -> Dict[str, Any]:
    """
    Evaluates detection and false alarm metrics for an individual 48h scenario.
    """
    alerts = [h for h, alt in result.alerts_by_hour if alt]

    if result.is_failure:
        onset = result.onset_hour if result.onset_hour is not None else clean_warmup_hours
        end = result.end_hour if result.end_hour is not None else 47

        # True alerts occurring during the active failure window
        tp_alerts = [h for h in alerts if onset <= h <= end]
        detected = len(tp_alerts) > 0
        delay = float(min(tp_alerts) - onset) if detected else None

        # False alarms before onset
        pre_onset_fa = len([h for h in alerts if h < onset])

        return {
            "scenario_type": result.scenario_type,
            "detected": detected,
            "delay": delay,
            "false_alarms": pre_onset_fa,
            "total_failure_hours": end - onset + 1,
        }
    elif result.is_hard_negative:
        # For hard negatives, any alert during the scenario is a false alarm
        total_alerts = len(alerts)
        return {
            "scenario_type": result.scenario_type,
            "hard_negative_alerted": total_alerts > 0,
            "total_alerts": total_alerts,
        }
    else:
        # Clean scenario
        return {
            "scenario_type": "clean",
            "clean_alerts": len(alerts),
            "hours": len(result.alerts_by_hour),
        }


def compute_aggregate_metrics(
    scenario_evals: List[ScenarioEvaluationResult],
    total_clean_operating_hours: int = 0,
) -> Dict[str, Any]:
    """
    Computes overall and per-failure Precision, Recall, F1, Delay, FA/week, HN-FPR.
    """
    # 1. Failure-level stats
    failure_scenarios = [s for s in scenario_evals if s.is_failure]
    hard_neg_scenarios = [s for s in scenario_evals if s.is_hard_negative]
    clean_scenarios = [s for s in scenario_evals if not s.is_failure and not s.is_hard_negative]

    # Overall TP, FP, FN at the event level
    # An event is detected if alerted during [onset, end]
    # FP is counted from:
    #   a) Alerts in clean scenarios
    #   b) Alerts in hard negative scenarios
    #   c) Alerts before failure onset
    total_events = len(failure_scenarios)
    detected_events = sum(1 for s in failure_scenarios if s.detected)
    delays = [s.delay_hours for s in failure_scenarios if s.delay_hours is not None]

    # Clean false alarms
    clean_fa = sum(s.false_alarms_in_clean_window for s in failure_scenarios)
    clean_fa += sum(len([h for h, alt in s.alerts_by_hour if alt]) for s in clean_scenarios)
    clean_hours = sum(len(s.alerts_by_hour) for s in clean_scenarios)
    clean_hours += sum((s.onset_hour or 12) for s in failure_scenarios)
    if total_clean_operating_hours > 0:
        clean_hours = max(clean_hours, total_clean_operating_hours)

    fa_per_week = (clean_fa / max(clean_hours, 1)) * 168.0

    # Hard Negative False Positive Rate (scenarios that alerted)
    hn_count = len(hard_neg_scenarios)
    hn_alerted = sum(1 for s in hard_neg_scenarios if any(alt for _, alt in s.alerts_by_hour))
    hn_fpr = (hn_alerted / hn_count) if hn_count > 0 else 0.0

    # Event-level Precision, Recall, F1
    # Recall = TP / (TP + FN)
    recall = (detected_events / total_events) if total_events > 0 else 0.0

    # Precision: TP / (TP + FP_events)
    # An FP event is defined as any clean or hard-negative scenario that triggered an alert
    fp_events = hn_alerted + sum(1 for s in clean_scenarios if any(alt for _, alt in s.alerts_by_hour))
    precision = (detected_events / (detected_events + fp_events)) if (detected_events + fp_events) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    # Per-failure-type breakdown
    per_failure = {}
    failure_types = sorted(list(set(s.scenario_type for s in failure_scenarios)))
    for ftype in failure_types:
        f_scenarios = [s for s in failure_scenarios if s.scenario_type == ftype]
        n_f = len(f_scenarios)
        n_det = sum(1 for s in f_scenarios if s.detected)
        f_delays = [s.delay_hours for s in f_scenarios if s.delay_hours is not None]

        f_recall = (n_det / n_f) if n_f > 0 else 0.0
        # For per-failure precision, standard apportioning or failure recall
        per_failure[ftype] = {
            "count": n_f,
            "detected": n_det,
            "recall": f_recall,
            "mean_delay": float(np.mean(f_delays)) if f_delays else None,
            "median_delay": float(np.median(f_delays)) if f_delays else None,
        }

    return {
        "event_precision": precision,
        "event_recall": recall,
        "event_f1": f1,
        "total_failures": total_events,
        "detected_failures": detected_events,
        "mean_delay_hours": float(np.mean(delays)) if delays else None,
        "median_delay_hours": float(np.median(delays)) if delays else None,
        "false_alarms_per_week": fa_per_week,
        "hard_negative_fpr": hn_fpr,
        "hard_negative_count": hn_count,
        "per_failure": per_failure,
    }


def bootstrap_metric_ci(
    scenario_evals: List[ScenarioEvaluationResult],
    n_resamples: int = 1000,
    seed: int = 42,
) -> Dict[str, Tuple[float, float]]:
    """
    Computes 95% bootstrap confidence intervals for aggregate metrics over n_resamples.
    """
    rng = np.random.default_rng(seed)
    n = len(scenario_evals)
    if n == 0:
        return {}

    precisions = []
    recalls = []
    f1s = []
    delays = []

    for _ in range(n_resamples):
        sample_indices = rng.integers(0, n, size=n)
        sample = [scenario_evals[i] for i in sample_indices]
        m = compute_aggregate_metrics(sample)

        precisions.append(m["event_precision"])
        recalls.append(m["event_recall"])
        f1s.append(m["event_f1"])
        if m["mean_delay_hours"] is not None:
            delays.append(m["mean_delay_hours"])

    ci_precision = (float(np.percentile(precisions, 2.5)), float(np.percentile(precisions, 97.5)))
    ci_recall = (float(np.percentile(recalls, 2.5)), float(np.percentile(recalls, 97.5)))
    ci_f1 = (float(np.percentile(f1s, 2.5)), float(np.percentile(f1s, 97.5)))
    ci_delay = (
        float(np.percentile(delays, 2.5)),
        float(np.percentile(delays, 97.5)),
    ) if len(delays) > 0 else (0.0, 0.0)

    return {
        "precision_ci": ci_precision,
        "recall_ci": ci_recall,
        "f1_ci": ci_f1,
        "mean_delay_ci": ci_delay,
    }
