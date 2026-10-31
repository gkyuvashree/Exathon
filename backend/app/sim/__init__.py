"""Simulation Package: E-Commerce Pipeline & Failure Injector."""

from .config import (
    TOTAL_DAYS,
    HOURS_PER_DAY,
    TOTAL_HOURS,
    PROMO_DAYS,
    CATEGORIES,
    STATES,
    PAYMENT_TYPES,
)
from .event_log import EventLogger
from .failures import (
    inject_unit_scale_slice,
    inject_partial_load,
    inject_duplicate_replay,
    inject_stale_source,
    inject_schema_drift_nulls,
    inject_default_fill,
    inject_timezone_shift,
    inject_orphan_keys,
    inject_join_fanout_flag,
    inject_promo_surge,
    inject_category_flash_sale,
)
from .generator import generate_hourly_batch
from .pipeline import PipelineEngine, load_lineage_config, is_dag_acyclic

__all__ = [
    "TOTAL_DAYS",
    "HOURS_PER_DAY",
    "TOTAL_HOURS",
    "PROMO_DAYS",
    "CATEGORIES",
    "STATES",
    "PAYMENT_TYPES",
    "EventLogger",
    "generate_hourly_batch",
    "PipelineEngine",
    "load_lineage_config",
    "is_dag_acyclic",
    "inject_unit_scale_slice",
    "inject_partial_load",
    "inject_duplicate_replay",
    "inject_stale_source",
    "inject_schema_drift_nulls",
    "inject_default_fill",
    "inject_timezone_shift",
    "inject_orphan_keys",
    "inject_join_fanout_flag",
    "inject_promo_surge",
    "inject_category_flash_sale",
]
