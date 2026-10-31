"""
Plumbline Coherence Engine for Pipeline Observability.

Implements robust seasonal Z-score baselines -> per-group PCA (T^2 + SPE)
anomaly detection -> priority-ordered verdict assignment.

Formula Reference:
  - Seasonal baseline: median/MAD robust estimator with log1p for volume metrics
  - Z-score: z = (x - median) / scale, clipped to [-15, +15]
  - Scale: scale = max(1.4826 * MAD, 1e-3 * abs(median), 1e-6)
  - T^2 (Hotelling): T^2 = sum(t_i^2 / lambda_i), where t_i are PCA scores, lambda_i are eigenvalues
  - SPE (Q-statistic): SPE = ||z - z_hat||^2, residual from PCA reconstruction
  - Limits: 99.5th percentile of T^2 and SPE on clean validation data
  - Persistence: 2 consecutive hours above limit, or 1 hour if SPE > 3x limit
  - Priority verdict:
      1. source_mismatch: control total gap exceeds threshold
      2. relationship_break: SPE alert
      3. coherent_surge: T^2 alert with normal SPE
      4. normal: otherwise
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple, Union
import joblib
import numpy as np
import pandas as pd
from sklearn.decomposition import PCA

from app.observer.metrics import compute_metrics, load_metrics_catalog
from app.sim.config import HOURS_PER_DAY, PROMO_DAYS, TRAIN_DAYS, VAL_DAYS

logger = logging.getLogger(__name__)

HOW_OF_WEEK = 168  # 7 * 24 hour-of-week slots
VOLUME_KINDS = frozenset({"volume"})
CONTROL_TOTAL_METRICS = frozenset({
    "control_total_gap_rows_orders",
    "control_total_gap_rows_items",
    "control_total_gap_value_items",
    "control_total_gap_rows_payments",
    "control_total_gap_value_payments",
})

CONSECUTIVE_HOURS_FOR_ALERT = 2
SPE_IMMEDIATE_MULTIPLIER = 3.0
SOURCE_MISMATCH_Z_THRESHOLD = 4.0


def get_promo_hours() -> Set[int]:
    """Return set of all hours falling on promotional days across the simulation horizon."""
    return {d * HOURS_PER_DAY + h for d in PROMO_DAYS for h in range(HOURS_PER_DAY)}


@dataclass
class SeasonalBaseline:
    """
    Robust seasonal baseline fitting per hour-of-week (0..167).
    Uses median and MAD with log1p transformation for volume metrics.
    """
    kind: str
    medians: np.ndarray = field(default_factory=lambda: np.zeros(HOW_OF_WEEK, dtype=float))
    scales: np.ndarray = field(default_factory=lambda: np.ones(HOW_OF_WEEK, dtype=float))

    def fit(self, values_by_how: Dict[int, Sequence[float]]):
        """Fit median and robust scale per hour-of-week."""
        is_vol = self.kind in VOLUME_KINDS
        self.medians = np.zeros(HOW_OF_WEEK, dtype=float)
        self.scales = np.ones(HOW_OF_WEEK, dtype=float)

        for how in range(HOW_OF_WEEK):
            vals = np.array(values_by_how.get(how, []), dtype=float)
            if len(vals) == 0:
                self.medians[how] = 0.0
                self.scales[how] = 1.0
                continue

            if is_vol:
                vals = np.log1p(np.maximum(vals, 0.0))

            med = float(np.median(vals))
            mad = float(np.median(np.abs(vals - med)))
            scale = max(1.4826 * mad, 1e-3 * abs(med), 1e-6)

            self.medians[how] = med
            self.scales[how] = scale

    def score(self, value: float, hour_of_week: int) -> Tuple[float, bool]:
        """
        Compute z-score clipped to [-15, 15] and return (z_clipped, unclipped_flag).
        """
        how = hour_of_week % HOW_OF_WEEK
        val = float(value)
        if self.kind in VOLUME_KINDS:
            val = np.log1p(max(val, 0.0))

        med = self.medians[how]
        scale = self.scales[how]

        z_raw = (val - med) / scale
        unclipped = bool(abs(z_raw) > 15.0)
        z_clipped = float(np.clip(z_raw, -15.0, 15.0))
        return z_clipped, unclipped


class GroupPCA:
    """
    Per-metric-group PCA with T^2 (Hotelling) and SPE (Q-statistic).
    Trained on training hours and limits calculated on validation data at 99.5th percentile.
    """
    def __init__(self, group_name: str, metric_keys: List[Tuple[str, str]]):
        self.group_name = group_name
        self.metric_keys = metric_keys  # List of (metric_name, segment)
        self.mu: np.ndarray = np.array([])
        self.sigma: np.ndarray = np.array([])
        self.pca: Optional[PCA] = None
        self.k: int = 1
        self.lambdas: np.ndarray = np.array([])
        self.t2_limit: float = 0.0
        self.spe_limit: float = 0.0

    def fit(self, z_matrix_train: np.ndarray, z_matrix_val: np.ndarray):
        """
        Standardize on training hours, fit PCA, compute limits from validation hours.
        """
        n_samples, n_features = z_matrix_train.shape
        if n_features == 0:
            return

        self.mu = np.mean(z_matrix_train, axis=0)
        self.sigma = np.std(z_matrix_train, axis=0)
        self.sigma[self.sigma < 1e-4] = 1.0

        z_std_train = (z_matrix_train - self.mu) / self.sigma

        max_comps = min(n_features, n_samples, 6)
        pca_full = PCA(n_components=max_comps)
        pca_full.fit(z_std_train)

        cum_var = np.cumsum(pca_full.explained_variance_ratio_)
        k = int(np.searchsorted(cum_var, 0.90) + 1)
        k = max(1, min(k, max_comps))

        self.k = k
        self.pca = PCA(n_components=self.k)
        self.pca.fit(z_std_train)
        self.lambdas = np.maximum(self.pca.explained_variance_, 1e-6)

        # Compute T2 and SPE on clean validation data
        t2_vals = []
        spe_vals = []
        for row in z_matrix_val:
            t2, spe, _, _ = self._score_internal(row)
            t2_vals.append(t2)
            spe_vals.append(spe)

        self.t2_limit = float(np.percentile(t2_vals, 99.5)) if len(t2_vals) > 0 else 10.0
        self.spe_limit = max(float(np.percentile(spe_vals, 99.5)), 1e-3) if len(spe_vals) > 0 else 1.0

    def _score_internal(self, z_vector: np.ndarray) -> Tuple[float, float, np.ndarray, np.ndarray]:
        """Calculates T^2, SPE, contributions, and reconstructed z."""
        if self.pca is None:
            return 0.0, 0.0, np.zeros_like(z_vector), z_vector

        z_std = (z_vector - self.mu) / self.sigma
        t = self.pca.transform(z_std.reshape(1, -1))[0]  # shape (k,)

        # Hotelling T2
        t2 = float(np.sum((t ** 2) / self.lambdas))

        # Reconstruction back to standardized space then original z space
        z_std_recon = self.pca.inverse_transform(t.reshape(1, -1))[0]
        z_recon = z_std_recon * self.sigma + self.mu

        diff = z_vector - z_recon
        spe = float(np.sum(diff ** 2))

        if spe > 1e-12:
            contributions = (diff ** 2) / spe
        else:
            contributions = np.zeros_like(diff)

        return t2, spe, contributions, z_recon

    def score(self, z_vector: np.ndarray) -> Tuple[float, float, List[Tuple[str, float]], np.ndarray]:
        t2, spe, contrib, z_recon = self._score_internal(z_vector)
        # Format contributions with metric labels
        contrib_list = []
        for i, (m, seg) in enumerate(self.metric_keys):
            name = m if seg == "ALL" else f"{m}[{seg}]"
            contrib_list.append((name, float(contrib[i])))
        contrib_list.sort(key=lambda x: x[1], reverse=True)
        return t2, spe, contrib_list, z_recon


@dataclass
class AlertState:
    """Tracks consecutive alert hours per group for persistence."""
    consecutive_t2: Dict[str, int] = field(default_factory=dict)
    consecutive_spe: Dict[str, int] = field(default_factory=dict)

    def update_and_check(
        self,
        group: str,
        t2_exceeded: bool,
        spe_exceeded: bool,
        spe_val: float,
        spe_limit: float,
    ) -> Tuple[bool, bool]:
        """
        Updates persistence state and returns (t2_alert, spe_alert).
        Rule: 2 consecutive hours, OR 1 hour if SPE > 3x limit.
        """
        if t2_exceeded:
            self.consecutive_t2[group] = self.consecutive_t2.get(group, 0) + 1
        else:
            self.consecutive_t2[group] = 0

        if spe_exceeded:
            self.consecutive_spe[group] = self.consecutive_spe.get(group, 0) + 1
        else:
            self.consecutive_spe[group] = 0

        t2_alert = self.consecutive_t2[group] >= CONSECUTIVE_HOURS_FOR_ALERT

        spe_alert = (
            self.consecutive_spe[group] >= CONSECUTIVE_HOURS_FOR_ALERT or
            (spe_exceeded and spe_val > SPE_IMMEDIATE_MULTIPLIER * spe_limit)
        )

        return t2_alert, spe_alert

    def reset(self):
        self.consecutive_t2.clear()
        self.consecutive_spe.clear()


@dataclass
class VerdictResult:
    verdict: str                  # "normal" | "coherent_surge" | "relationship_break" | "source_mismatch"
    group: str                    # most alerting group or "all"
    t2: Dict[str, float]
    spe: Dict[str, float]
    top5_contributors: List[Tuple[str, float]]
    label: Optional[str] = None   # e.g., "promo_day"
    alert_flags: Dict[str, Dict[str, bool]] = field(default_factory=dict)


class CoherenceModel:
    """
    Composite trained model container containing baselines and per-group PCAs.
    Never refits on live or test data; can be serialized via joblib.
    """
    def __init__(self):
        self.baselines: Dict[Tuple[str, str], SeasonalBaseline] = {}
        self.group_pcas: Dict[str, GroupPCA] = {}
        self.group_metric_keys: Dict[str, List[Tuple[str, str]]] = {}
        self.train_hours: List[int] = []
        self.val_hours: List[int] = []

    def fit(
        self,
        metrics_df: pd.DataFrame,
        train_hours: Iterable[int],
        val_hours: Iterable[int],
        promo_hours_set: Set[int],
        catalog: List[Dict[str, Any]],
    ):
        """Fit seasonal baselines and per-group PCAs."""
        train_set = set(train_hours)
        val_set = set(val_hours)
        self.train_hours = sorted(list(train_set))
        self.val_hours = sorted(list(val_set))

        # Build metric kind map
        metric_kinds = {m["name"]: m["kind"] for m in catalog}
        metric_groups = {m["name"]: m["group"] for m in catalog}

        # 1. Identify distinct (metric, segment) pairs
        distinct_pairs = (
            metrics_df[["metric", "segment"]]
            .drop_duplicates()
            .to_records(index=False)
        )
        pair_list = [(str(r[0]), str(r[1])) for r in distinct_pairs]

        # Organize by group
        self.group_metric_keys = {g: [] for g in ["orders", "items", "payments", "totals", "mart"]}
        for m, seg in pair_list:
            grp = metric_groups.get(m, "totals")
            if grp in self.group_metric_keys:
                self.group_metric_keys[grp].append((m, seg))

        # Sort keys deterministically
        for grp in self.group_metric_keys:
            self.group_metric_keys[grp].sort()

        # 2. Fit SeasonalBaselines per (metric, segment) excluding promo hours
        # Filter to train hours
        train_df = metrics_df[metrics_df["hour_ts"].isin(train_set)].copy()
        train_df_non_promo = train_df[~train_df["hour_ts"].isin(promo_hours_set)].copy()
        train_df_non_promo["how"] = train_df_non_promo["hour_ts"] % HOW_OF_WEEK

        logger.info("Fitting SeasonalBaselines...")
        for m, seg in pair_list:
            kind = metric_kinds.get(m, "volume")
            subset = train_df_non_promo[(train_df_non_promo["metric"] == m) & (train_df_non_promo["segment"] == seg)]
            values_by_how: Dict[int, List[float]] = {}
            for how, grp_data in subset.groupby("how"):
                values_by_how[int(how)] = grp_data["value"].tolist()

            sb = SeasonalBaseline(kind=kind)
            sb.fit(values_by_how)
            self.baselines[(m, seg)] = sb

        # 3. Compute z-scores across all train and val hours
        all_eval_hours = self.train_hours + self.val_hours
        z_dict: Dict[Tuple[int, str, str], float] = {}

        # Vectorized lookup for speed
        eval_metrics = metrics_df[metrics_df["hour_ts"].isin(all_eval_hours)]
        for row in eval_metrics.itertuples(index=False):
            key = (row.metric, row.segment)
            if key in self.baselines:
                sb = self.baselines[key]
                z, _ = sb.score(row.value, row.hour_ts)
                z_dict[(row.hour_ts, row.metric, row.segment)] = z

        # 4. For each group, construct train and val z matrices and fit GroupPCA
        for grp, keys in self.group_metric_keys.items():
            if not keys:
                continue

            z_mat_train = np.zeros((len(self.train_hours), len(keys)), dtype=float)
            for i, h in enumerate(self.train_hours):
                for j, (m, seg) in enumerate(keys):
                    z_mat_train[i, j] = z_dict.get((h, m, seg), 0.0)

            z_mat_val = np.zeros((len(self.val_hours), len(keys)), dtype=float)
            for i, h in enumerate(self.val_hours):
                for j, (m, seg) in enumerate(keys):
                    z_mat_val[i, j] = z_dict.get((h, m, seg), 0.0)

            gpca = GroupPCA(group_name=grp, metric_keys=keys)
            gpca.fit(z_mat_train, z_mat_val)
            self.group_pcas[grp] = gpca

    def save(self, path: Union[str, Path]):
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, str(p))

    @classmethod
    def load(cls, path: Union[str, Path]) -> "CoherenceModel":
        return joblib.load(str(path))


class PlumblineEngine:
    """
    Runtime Plumbline Coherence Engine.
    Evaluates new hours, manages alert persistence state, and issues verdicts.
    """
    def __init__(self, model: CoherenceModel, catalog: Optional[List[Dict[str, Any]]] = None):
        self.model = model
        self.catalog = catalog or load_metrics_catalog()
        self.alert_state = AlertState()
        self.promo_hours_set = get_promo_hours()

    def reset_state(self):
        """Resets the consecutive alert tracker."""
        self.alert_state.reset()

    def score(
        self,
        metrics_df_or_con: Any,
        hour: int,
        cal_events: Optional[Dict[str, Any]] = None,
    ) -> VerdictResult:
        """
        Score a single hour against the coherence model and return a VerdictResult.
        metrics_df_or_con can be a DataFrame containing metrics for this hour or a DuckDB connection.
        """
        if isinstance(metrics_df_or_con, pd.DataFrame):
            df_hour = metrics_df_or_con[metrics_df_or_con["hour_ts"] == hour]
        else:
            # Assume DuckDB connection
            df_hour = compute_metrics(metrics_df_or_con, [hour])

        # 1. Compute z-scores for all metrics in this hour
        z_scores: Dict[Tuple[str, str], float] = {}
        for row in df_hour.itertuples(index=False):
            key = (row.metric, row.segment)
            if key in self.model.baselines:
                sb = self.model.baselines[key]
                z, _ = sb.score(row.value, hour)
                z_scores[key] = z

        # 2. Check source_mismatch priority rule
        # If any control_total_gap metric has absolute z-score > 4.0
        source_mismatch_triggered = False
        mismatch_metric = None
        for m in CONTROL_TOTAL_METRICS:
            key = (m, "ALL")
            if abs(z_scores.get(key, 0.0)) > SOURCE_MISMATCH_Z_THRESHOLD:
                source_mismatch_triggered = True
                mismatch_metric = m
                break

        # 3. Score GroupPCAs
        t2_dict: Dict[str, float] = {}
        spe_dict: Dict[str, float] = {}
        all_contribs: List[Tuple[str, float]] = []
        alert_flags: Dict[str, Dict[str, bool]] = {}

        any_spe_alert = False
        any_t2_alert = False
        max_spe_ratio = 0.0
        worst_spe_group = "totals"

        for grp, gpca in self.model.group_pcas.items():
            keys = self.model.group_metric_keys.get(grp, [])
            if not keys:
                continue

            z_vec = np.array([z_scores.get(k, 0.0) for k in keys], dtype=float)
            t2, spe, contribs, _ = gpca.score(z_vec)

            t2_dict[grp] = t2
            spe_dict[grp] = spe

            t2_exc = t2 > gpca.t2_limit
            spe_exc = spe > gpca.spe_limit

            t2_alt, spe_alt = self.alert_state.update_and_check(
                grp, t2_exc, spe_exc, spe, gpca.spe_limit
            )

            alert_flags[grp] = {"t2": t2_alt, "spe": spe_alt}

            if spe_alt:
                any_spe_alert = True
                ratio = spe / max(gpca.spe_limit, 1e-6)
                if ratio > max_spe_ratio:
                    max_spe_ratio = ratio
                    worst_spe_group = grp

            if t2_alt:
                any_t2_alert = True

            all_contribs.extend(contribs)

        # Sort all contributions to identify top 5 SPE contributors
        all_contribs.sort(key=lambda x: x[1], reverse=True)
        top5 = all_contribs[:5]

        # 4. Determine Verdict by Priority
        # Priority 1: source_mismatch
        if source_mismatch_triggered:
            return VerdictResult(
                verdict="source_mismatch",
                group=worst_spe_group if any_spe_alert else "totals",
                t2=t2_dict,
                spe=spe_dict,
                top5_contributors=top5,
                label=f"gap_breach:{mismatch_metric}",
                alert_flags=alert_flags,
            )

        # Priority 2: relationship_break (SPE alert)
        if any_spe_alert:
            return VerdictResult(
                verdict="relationship_break",
                group=worst_spe_group,
                t2=t2_dict,
                spe=spe_dict,
                top5_contributors=top5,
                label=None,
                alert_flags=alert_flags,
            )

        # Priority 3: coherent_surge (T^2 alert with SPE normal)
        is_promo = hour in self.promo_hours_set or (cal_events and cal_events.get("promo_day"))
        if any_t2_alert and not any_spe_alert:
            label = "promo_day" if is_promo else "unlabeled_surge"
            return VerdictResult(
                verdict="coherent_surge",
                group="mart" if "mart" in t2_dict else "all",
                t2=t2_dict,
                spe=spe_dict,
                top5_contributors=top5,
                label=label,
                alert_flags=alert_flags,
            )

        # Priority 4: normal
        return VerdictResult(
            verdict="normal",
            group="all",
            t2=t2_dict,
            spe=spe_dict,
            top5_contributors=top5,
            label="promo_day" if is_promo else None,
            alert_flags=alert_flags,
        )
