"""Synthetic Data Generator for Hourly E-Commerce Stream."""

from datetime import datetime, timedelta, timezone
from typing import Dict, Tuple, Optional
import numpy as np
import pandas as pd

from .config import (
    BASE_ORDER_LAMBDA,
    CATEGORIES,
    CATEGORY_PRICE_PARAMS,
    CATEGORY_WEIGHTS,
    COUPON_MAX_DISCOUNT,
    COUPON_MIN_DISCOUNT,
    COUPON_PROBABILITY,
    DAILY_PROFILE,
    HOURS_PER_DAY,
    LAG_MEDIAN_MINUTES,
    LAG_SPREAD_MINUTES,
    LAMBDA_LOGNORMAL_SIGMA,
    PAYMENT_TYPES,
    PAYMENT_WEIGHTS,
    PROMO_DAYS,
    PROMO_VOLUME_MULTIPLIER,
    SIMULATION_START_TS,
    STATES,
    STATE_WEIGHTS,
    WEEKLY_PROFILE,
)

ORDER_STATUSES = ["delivered", "shipped", "invoiced"]
ORDER_STATUS_WEIGHTS = np.array([0.70, 0.20, 0.10], dtype=float)


def get_hour_rng(master_seed: int, batch_hour: int) -> np.random.Generator:
    """Derive a reproducible deterministic RNG for a specific batch hour."""
    # Combine master seed and batch hour into an unambiguous uint64 seed
    combined_seed = (int(master_seed) * 1_000_003 + int(batch_hour) * 997 + 42) & 0xFFFFFFFF
    return np.random.default_rng(combined_seed)


def calculate_hourly_lambda(batch_hour: int, rng: np.random.Generator, promo_multiplier_override: Optional[float] = None) -> float:
    """Calculate the expected order arrival rate lambda(h) for a given batch hour."""
    day = batch_hour // HOURS_PER_DAY
    hod = batch_hour % HOURS_PER_DAY
    dow = day % 7

    daily_factor = DAILY_PROFILE[hod]
    weekly_factor = WEEKLY_PROFILE[dow]
    lognormal_noise = np.exp(rng.normal(0.0, LAMBDA_LOGNORMAL_SIGMA))

    promo_factor = 1.0
    if promo_multiplier_override is not None:
        promo_factor = promo_multiplier_override
    elif day in PROMO_DAYS:
        promo_factor = PROMO_VOLUME_MULTIPLIER

    lam = BASE_ORDER_LAMBDA * daily_factor * weekly_factor * lognormal_noise * promo_factor
    return max(lam, 5.0)


def generate_hourly_batch(
    batch_hour: int,
    master_seed: int = 42,
    lambda_override: Optional[float] = None,
    category_weights_override: Optional[np.ndarray] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Generate clean synthetic hourly data for orders, order_items, and payments.
    Returns (orders_df, items_df, payments_df).
    """
    rng = get_hour_rng(master_seed, batch_hour)

    if lambda_override is not None:
        lam = lambda_override
    else:
        lam = calculate_hourly_lambda(batch_hour, rng)

    n_orders = int(rng.poisson(lam))
    n_orders = max(n_orders, 1)  # Ensure at least 1 order per batch

    batch_start_ts = SIMULATION_START_TS + timedelta(hours=batch_hour)
    batch_end_ts = batch_start_ts + timedelta(hours=1)

    # 1. GENERATE ORDERS
    order_ids = [f"ord_{batch_hour:05d}_{i:04d}" for i in range(n_orders)]
    customer_ids = [f"cust_{rng.integers(1, 50000):06d}" for _ in range(n_orders)]
    order_states = rng.choice(STATES, size=n_orders, p=STATE_WEIGHTS)
    order_statuses = rng.choice(ORDER_STATUSES, size=n_orders, p=ORDER_STATUS_WEIGHTS)

    # Event timestamps distributed uniformly within batch hour
    event_seconds = rng.uniform(0, 3599, size=n_orders)
    event_timestamps = [batch_start_ts + timedelta(seconds=float(s)) for s in event_seconds]

    # Landing lag: median ~20 min, spread ~10 min
    # We use normal distribution truncated to >= 1 min
    lags_minutes = np.maximum(rng.normal(LAG_MEDIAN_MINUTES, LAG_SPREAD_MINUTES, size=n_orders), 1.0)
    landed_timestamps = [batch_end_ts + timedelta(minutes=float(lag)) for lag in lags_minutes]

    orders_df = pd.DataFrame({
        "order_id": order_ids,
        "customer_id": customer_ids,
        "state": order_states,
        "status": order_statuses,
        "event_ts": pd.to_datetime(event_timestamps),
        "landed_ts": pd.to_datetime(landed_timestamps),
        "batch_hour": np.full(n_orders, batch_hour, dtype=np.int32),
    })

    # 2. GENERATE ORDER ITEMS
    # Items per order: discrete uniform 1..4
    items_per_order = rng.integers(1, 5, size=n_orders)
    total_items = int(np.sum(items_per_order))

    # Repeat order attributes per item
    item_order_ids = np.repeat(order_ids, items_per_order)
    item_event_ts = np.repeat(event_timestamps, items_per_order)
    item_landed_ts = np.repeat(landed_timestamps, items_per_order)

    # Sequential item_ids within order: e.g. item_1, item_2
    item_seqs = np.concatenate([np.arange(1, count + 1) for count in items_per_order])
    item_ids = [f"{oid}_item_{seq}" for oid, seq in zip(item_order_ids, item_seqs)]

    # Category selection
    cat_weights = category_weights_override if category_weights_override is not None else CATEGORY_WEIGHTS
    item_categories = rng.choice(CATEGORIES, size=total_items, p=cat_weights)

    # Prices lognormal per category
    item_prices = np.empty(total_items, dtype=float)
    for cat, (mu, sigma) in CATEGORY_PRICE_PARAMS.items():
        mask = (item_categories == cat)
        count = int(np.sum(mask))
        if count > 0:
            prices = np.exp(rng.normal(mu, sigma, size=count))
            item_prices[mask] = np.round(prices, 2)

    # Freight = f(price) + noise, f(price) = 5.0 + 0.05 * price + |noise|
    freight_noise = np.abs(rng.normal(0.0, 2.0, size=total_items))
    item_freights = np.round(np.maximum(5.0 + 0.05 * item_prices + freight_noise, 2.50), 2)

    items_df = pd.DataFrame({
        "order_id": item_order_ids,
        "item_id": item_ids,
        "category": item_categories,
        "price": item_prices,
        "freight": item_freights,
        "event_ts": pd.to_datetime(item_event_ts),
        "landed_ts": pd.to_datetime(item_landed_ts),
        "batch_hour": np.full(total_items, batch_hour, dtype=np.int32),
    })

    # 3. GENERATE PAYMENTS (ONE payment row per order)
    payment_types = rng.choice(PAYMENT_TYPES, size=n_orders, p=PAYMENT_WEIGHTS)

    # Aggregate item price + freight per order
    # Using order_id mapping for robust group sums
    order_item_totals = items_df.groupby("order_id")[["price", "freight"]].sum()
    order_totals_map = (order_item_totals["price"] + order_item_totals["freight"]).to_dict()

    raw_payment_values = np.array([order_totals_map[oid] for oid in order_ids], dtype=float)

    # 8% of orders get coupon reducing it by 5-15%
    has_coupon = rng.uniform(0.0, 1.0, size=n_orders) < COUPON_PROBABILITY
    coupon_discounts = rng.uniform(COUPON_MIN_DISCOUNT, COUPON_MAX_DISCOUNT, size=n_orders)
    discount_multipliers = np.where(has_coupon, 1.0 - coupon_discounts, 1.0)

    final_payment_values = np.round(raw_payment_values * discount_multipliers, 2)

    payments_df = pd.DataFrame({
        "order_id": order_ids,
        "payment_type": payment_types,
        "payment_value": final_payment_values,
        "event_ts": pd.to_datetime(event_timestamps),
        "landed_ts": pd.to_datetime(landed_timestamps),
        "batch_hour": np.full(n_orders, batch_hour, dtype=np.int32),
    })

    return orders_df, items_df, payments_df
