"""Simulation Configuration and Domain Parameters."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Set, Tuple
import numpy as np

# Simulation Time Horizon
TOTAL_DAYS = 150
HOURS_PER_DAY = 24
TOTAL_HOURS = TOTAL_DAYS * HOURS_PER_DAY  # 3600 hours

TRAIN_DAYS: Tuple[int, int] = (0, 89)       # Days 0-89
VAL_DAYS: Tuple[int, int] = (90, 119)       # Days 90-119 (Clean)
LIVE_DAYS: Tuple[int, int] = (120, 149)     # Days 120-149

PROMO_DAYS: Set[int] = {35, 70, 105, 125}
PROMO_VOLUME_MULTIPLIER = 2.5

BASE_ORDER_LAMBDA = 150.0  # Orders per hour base
LAMBDA_LOGNORMAL_SIGMA = 0.05

SIMULATION_START_TS = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

# 24-hour normalized profile (mean = 1.0)
_RAW_DAILY_PROFILE = np.array([
    0.35, 0.25, 0.20, 0.18, 0.22, 0.35,
    0.60, 0.85, 1.05, 1.20, 1.25, 1.30,
    1.35, 1.30, 1.25, 1.20, 1.25, 1.35,
    1.45, 1.50, 1.40, 1.25, 0.95, 0.65
], dtype=float)
DAILY_PROFILE = _RAW_DAILY_PROFILE / _RAW_DAILY_PROFILE.mean()

# 7-day weekly profile (0=Monday ... 6=Sunday, mean = 1.0)
_RAW_WEEKLY_PROFILE = np.array([0.95, 0.98, 1.00, 1.02, 1.08, 1.12, 1.05], dtype=float)
WEEKLY_PROFILE = _RAW_WEEKLY_PROFILE / _RAW_WEEKLY_PROFILE.mean()

# Categories and their lognormal price parameters (mu, sigma)
CATEGORIES: List[str] = [
    "electronics",
    "apparel",
    "home_kitchen",
    "beauty",
    "books",
    "sports"
]
CATEGORY_WEIGHTS: np.ndarray = np.array([0.20, 0.25, 0.20, 0.15, 0.10, 0.10], dtype=float)
CATEGORY_PRICE_PARAMS: Dict[str, Tuple[float, float]] = {
    "electronics": (4.5, 0.5),    # Mean ~ $100
    "apparel": (3.5, 0.4),        # Mean ~ $35
    "home_kitchen": (3.8, 0.4),   # Mean ~ $48
    "beauty": (3.2, 0.35),        # Mean ~ $26
    "books": (2.7, 0.3),          # Mean ~ $16
    "sports": (3.7, 0.45),        # Mean ~ $45
}

# 8 States with weights
STATES: List[str] = ["CA", "NY", "TX", "FL", "IL", "PA", "OH", "WA"]
STATE_WEIGHTS: np.ndarray = np.array([0.22, 0.18, 0.16, 0.14, 0.09, 0.08, 0.07, 0.06], dtype=float)

# Payment types and weights
PAYMENT_TYPES: List[str] = ["credit_card", "debit_card", "voucher", "wallet"]
PAYMENT_WEIGHTS: np.ndarray = np.array([0.62, 0.14, 0.12, 0.12], dtype=float)

# Coupon parameters
COUPON_PROBABILITY = 0.08
COUPON_MIN_DISCOUNT = 0.05
COUPON_MAX_DISCOUNT = 0.15

# Landing lag parameters (minutes)
LAG_MEDIAN_MINUTES = 20.0
LAG_SPREAD_MINUTES = 10.0
