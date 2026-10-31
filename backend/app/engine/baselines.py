"""
Baseline Detectors for Pipeline Observability.

Four independent baseline detectors running alongside Plumbline:
  1. StaticThreshold: orders row_count +-30% of rolling 168-hour median.
  2. UnivariateSeasonal: per-metric robust seasonal z-score > 4 on orders row_count.
  3. IsolationForestBaseline: multi-metric Isolation Forest trained only on clean train data.
  4. PipelineHeartbeat: always-green pipeline status monitor.
"""

from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from app.engine.coherence import HOW_OF_WEEK, SeasonalBaseline


class StaticThreshold:
    """
    Static Threshold Detector: alerts if raw_orders row count falls outside
    +-30% of the historical median across training.
    """
    def __init__(self, tolerance: float = 0.30):
        self.tolerance = tolerance
        self.median_val: float = 0.0

    def fit(self, values: pd.Series):
        vals = np.array(values, dtype=float)
        self.median_val = float(np.median(vals)) if len(vals) > 0 else 100.0

    def score(self, value: float) -> Dict[str, Any]:
        lower = self.median_val * (1.0 - self.tolerance)
        upper = self.median_val * (1.0 + self.tolerance)
        alert = bool(value < lower or value > upper)
        return {
            "alert": alert,
            "value": float(value),
            "lower_bound": lower,
            "upper_bound": upper,
            "reason": f"Value {value:.1f} out of bounds [{lower:.1f}, {upper:.1f}]" if alert else "ok",
        }


class UnivariateSeasonal:
    """
    Univariate Seasonal Detector: uses SeasonalBaseline on raw_orders row_count,
    alerting when absolute z-score > 4.0.
    """
    def __init__(self, threshold: float = 4.0):
        self.threshold = threshold
        self.baseline = SeasonalBaseline(kind="volume")

    def fit(self, values_by_how: Dict[int, List[float]]):
        self.baseline.fit(values_by_how)

    def score(self, value: float, hour: int) -> Dict[str, Any]:
        z, unclipped = self.baseline.score(value, hour)
        alert = bool(abs(z) > self.threshold)
        return {
            "alert": alert,
            "z": float(z),
            "unclipped": unclipped,
            "reason": f"Z-score {z:.2f} exceeds threshold {self.threshold}" if alert else "ok",
        }


class IsolationForestBaseline:
    """
    Isolation Forest Detector trained on standardized multi-metric vectors
    from clean training hours with fixed seed and contamination.
    """
    def __init__(self, contamination: float = 0.05, seed: int = 42):
        self.contamination = contamination
        self.seed = seed
        self.model: Optional[IsolationForest] = None
        self.mu: np.ndarray = np.array([])
        self.sigma: np.ndarray = np.array([])

    def fit(self, matrix_train: np.ndarray):
        n_samples, n_features = matrix_train.shape
        if n_samples == 0 or n_features == 0:
            return

        self.mu = np.mean(matrix_train, axis=0)
        self.sigma = np.std(matrix_train, axis=0)
        self.sigma[self.sigma < 1e-6] = 1.0

        x_std = (matrix_train - self.mu) / self.sigma

        self.model = IsolationForest(
            contamination=self.contamination,
            random_state=self.seed,
            n_estimators=100,
        )
        self.model.fit(x_std)

    def score(self, vector: np.ndarray) -> Dict[str, Any]:
        if self.model is None:
            return {"alert": False, "score": 0.0, "reason": "unfitted"}

        x_std = (vector.reshape(1, -1) - self.mu) / self.sigma
        pred = self.model.predict(x_std)[0]  # -1 for anomaly, 1 for inlier
        raw_score = float(self.model.score_samples(x_std)[0])
        alert = bool(pred == -1)
        return {
            "alert": alert,
            "score": raw_score,
            "reason": "Isolation Forest anomaly" if alert else "ok",
        }


class PipelineHeartbeat:
    """Always-green pipeline heartbeat monitor."""
    def score(self, hour: int) -> Dict[str, Any]:
        return {
            "alert": False,
            "status": "pipeline_succeeded",
            "reason": "Heartbeat OK",
        }


class BaselineBundle:
    """Bundle containing all 4 baseline detectors."""
    def __init__(self):
        self.static_thresh = StaticThreshold()
        self.univariate = UnivariateSeasonal()
        self.iso_forest = IsolationForestBaseline()
        self.heartbeat = PipelineHeartbeat()
        self.metric_keys: List[Tuple[str, str]] = []

    def fit(
        self,
        metrics_df: pd.DataFrame,
        train_hours: Iterable[int],
        promo_hours_set: Set[int],
    ):
        train_set = set(train_hours)
        train_df = metrics_df[metrics_df["hour_ts"].isin(train_set)]

        # 1. Fit StaticThreshold on orders_row_count (ALL)
        orders_rc = train_df[
            (train_df["metric"] == "orders_row_count") & (train_df["segment"] == "ALL")
        ]["value"]
        self.static_thresh.fit(orders_rc)

        # 2. Fit UnivariateSeasonal on orders_row_count excluding promo hours
        orders_non_promo = train_df[
            (train_df["metric"] == "orders_row_count") &
            (train_df["segment"] == "ALL") &
            (~train_df["hour_ts"].isin(promo_hours_set))
        ].copy()
        orders_non_promo["how"] = orders_non_promo["hour_ts"] % HOW_OF_WEEK

        by_how: Dict[int, List[float]] = {}
        for how, grp in orders_non_promo.groupby("how"):
            by_how[int(how)] = grp["value"].tolist()
        self.univariate.fit(by_how)

        # 3. Fit IsolationForest on core metrics
        core_metrics = [
            ("orders_row_count", "ALL"),
            ("items_row_count", "ALL"),
            ("payments_row_count", "ALL"),
            ("mart_hourly_revenue", "ALL"),
            ("payments_to_items_ratio", "ALL"),
            ("items_per_order", "ALL"),
        ]
        self.metric_keys = core_metrics

        train_hours_sorted = sorted(list(train_set))
        train_mat = np.zeros((len(train_hours_sorted), len(core_metrics)), dtype=float)

        val_dict = {}
        for row in train_df.itertuples(index=False):
            val_dict[(row.hour_ts, row.metric, row.segment)] = float(row.value)

        for i, h in enumerate(train_hours_sorted):
            for j, (m, seg) in enumerate(core_metrics):
                train_mat[i, j] = val_dict.get((h, m, seg), 0.0)

        self.iso_forest.fit(train_mat)

    def score(self, metrics_df_or_hour_df: pd.DataFrame, hour: int) -> Dict[str, Any]:
        df = metrics_df_or_hour_df[metrics_df_or_hour_df["hour_ts"] == hour]
        val_map = {(r.metric, r.segment): float(r.value) for r in df.itertuples(index=False)}

        orders_rc = val_map.get(("orders_row_count", "ALL"), 0.0)

        res_static = self.static_thresh.score(orders_rc)
        res_univ = self.univariate.score(orders_rc, hour)

        vec = np.array([val_map.get(k, 0.0) for k in self.metric_keys], dtype=float)
        res_iso = self.iso_forest.score(vec)
        res_hb = self.heartbeat.score(hour)

        return {
            "static_threshold": res_static,
            "univariate_seasonal": res_univ,
            "isolation_forest": res_iso,
            "pipeline_heartbeat": res_hb,
        }
