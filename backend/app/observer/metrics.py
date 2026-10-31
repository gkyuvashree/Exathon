"""DuckDB Vectorized Metric Engine for Computing Observability Metrics."""

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Union
import duckdb
import numpy as np
import pandas as pd
import yaml

from app.sim.config import CATEGORIES, PAYMENT_TYPES, STATES


def find_metrics_yaml() -> Path:
    """Find metrics.yaml configuration file."""
    candidates = [
        Path("config/metrics.yaml"),
        Path("backend/config/metrics.yaml"),
        Path(__file__).resolve().parent.parent.parent.parent / "config" / "metrics.yaml",
        Path(__file__).resolve().parent.parent.parent / "config" / "metrics.yaml",
    ]
    for c in candidates:
        if c.exists():
            return c
    raise FileNotFoundError("Could not find config/metrics.yaml")


def load_metrics_catalog(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Load the metrics catalog configuration."""
    p = path or find_metrics_yaml()
    with open(p, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("metrics", [])


def get_metric_to_group_map() -> Dict[str, str]:
    """Return dictionary mapping metric_name -> group."""
    catalog = load_metrics_catalog()
    return {m["name"]: m["group"] for m in catalog}


def compute_metrics(
    con: duckdb.DuckDBPyConnection,
    window_hours: Union[Sequence[int], Iterable[int]],
) -> pd.DataFrame:
    """
    Computes all observability metrics for any window of hours in a single pass.
    The exact same function operates on a 120-day history or a single live hour.
    Guarantees no NaN or inf values by using documented zero/identity fallbacks.
    Returns DataFrame with columns: [node, metric, segment, hour_ts, value].
    """
    hours_list = [int(h) for h in window_hours]
    if not hours_list:
        return pd.DataFrame(columns=["node", "metric", "segment", "hour_ts", "value"])

    # Register target hours table in DuckDB for efficient grouping and filtering
    hours_df = pd.DataFrame({"batch_hour": hours_list})
    con.register("tgt_hours", hours_df)

    rows: List[tuple] = []

    # ==========================================================================
    # 1. RAW ORDERS METRICS (Group: orders)
    # ==========================================================================
    orders_overall_sql = """
        SELECT
            h.batch_hour AS hour_ts,
            COALESCE(COUNT(o.order_id), 0) AS row_count,
            COALESCE(COUNT(DISTINCT o.order_id) / NULLIF(COUNT(o.order_id), 0), 1.0) AS distinct_key_ratio,
            COALESCE(COUNT(CASE WHEN o.customer_id IS NULL THEN 1 END) / NULLIF(COUNT(o.order_id), 0), 0.0) AS null_rate_customer_id,
            COALESCE(COUNT(CASE WHEN o.state IS NULL THEN 1 END) / NULLIF(COUNT(o.order_id), 0), 0.0) AS null_rate_state,
            COALESCE(COUNT(CASE WHEN o.status IS NULL THEN 1 END) / NULLIF(COUNT(o.order_id), 0), 0.0) AS null_rate_status,
            COALESCE(quantile_cont(epoch(o.landed_ts) - epoch(o.event_ts), 0.5) / 60.0, 0.0) AS arrival_lag_p50
        FROM tgt_hours h
        LEFT JOIN raw_orders o ON h.batch_hour = o.batch_hour
        GROUP BY h.batch_hour
        ORDER BY h.batch_hour
    """
    res_orders = con.execute(orders_overall_sql).fetchall()
    for h_ts, rc, dkr, nc, n_st, n_stat, lag in res_orders:
        rows.append(("raw_orders", "orders_row_count", "ALL", h_ts, float(rc)))
        rows.append(("raw_orders", "orders_distinct_key_ratio", "ALL", h_ts, float(dkr)))
        rows.append(("raw_orders", "orders_null_rate_customer_id", "ALL", h_ts, float(nc)))
        rows.append(("raw_orders", "orders_null_rate_state", "ALL", h_ts, float(n_st)))
        rows.append(("raw_orders", "orders_null_rate_status", "ALL", h_ts, float(n_stat)))
        rows.append(("raw_orders", "orders_arrival_lag_p50", "ALL", h_ts, float(lag)))

    # Orders Segment Metrics: state
    orders_state_sql = """
        WITH state_grid AS (
            SELECT h.batch_hour, s.state
            FROM tgt_hours h
            CROSS JOIN (SELECT unnest($states) AS state) s
        ),
        counts AS (
            SELECT
                h.batch_hour,
                o.state,
                COUNT(*) AS cnt
            FROM tgt_hours h
            JOIN raw_orders o ON h.batch_hour = o.batch_hour
            WHERE o.state IS NOT NULL
            GROUP BY h.batch_hour, o.state
        ),
        totals AS (
            SELECT h.batch_hour, COUNT(*) AS tot_orders
            FROM tgt_hours h
            JOIN raw_orders o ON h.batch_hour = o.batch_hour
            GROUP BY h.batch_hour
        )
        SELECT
            g.batch_hour AS hour_ts,
            g.state,
            COALESCE(c.cnt, 0) AS state_sum,
            COALESCE(CAST(c.cnt AS DOUBLE) / NULLIF(t.tot_orders, 0), 0.0) AS state_share
        FROM state_grid g
        LEFT JOIN counts c ON g.batch_hour = c.batch_hour AND g.state = c.state
        LEFT JOIN totals t ON g.batch_hour = t.batch_hour
        ORDER BY g.batch_hour, g.state
    """
    res_states = con.execute(orders_state_sql, {"states": STATES}).fetchall()
    for h_ts, st, s_sum, s_share in res_states:
        rows.append(("raw_orders", "orders_state_sum", str(st), h_ts, float(s_sum)))
        rows.append(("raw_orders", "orders_state_share", str(st), h_ts, float(s_share)))

    # ==========================================================================
    # 2. RAW ITEMS METRICS (Group: items)
    # ==========================================================================
    items_overall_sql = """
        SELECT
            h.batch_hour AS hour_ts,
            COALESCE(COUNT(i.item_id), 0) AS row_count,
            COALESCE(COUNT(DISTINCT i.item_id) / NULLIF(COUNT(i.item_id), 0), 1.0) AS distinct_key_ratio,
            COALESCE(COUNT(CASE WHEN i.category IS NULL THEN 1 END) / NULLIF(COUNT(i.item_id), 0), 0.0) AS null_rate_category,
            COALESCE(COUNT(CASE WHEN i.price IS NULL THEN 1 END) / NULLIF(COUNT(i.item_id), 0), 0.0) AS null_rate_price,
            COALESCE(COUNT(CASE WHEN i.freight IS NULL THEN 1 END) / NULLIF(COUNT(i.item_id), 0), 0.0) AS null_rate_freight,
            COALESCE(quantile_cont(epoch(i.landed_ts) - epoch(i.event_ts), 0.5) / 60.0, 0.0) AS arrival_lag_p50,
            COALESCE(AVG(i.price), 0.0) AS price_mean,
            COALESCE(quantile_cont(i.price, 0.5), 0.0) AS price_p50,
            COALESCE(quantile_cont(i.price, 0.95), 0.0) AS price_p95,
            COALESCE(AVG(i.freight), 0.0) AS freight_mean,
            COALESCE(quantile_cont(i.freight, 0.5), 0.0) AS freight_p50,
            COALESCE(quantile_cont(i.freight, 0.95), 0.0) AS freight_p95
        FROM tgt_hours h
        LEFT JOIN raw_items i ON h.batch_hour = i.batch_hour
        GROUP BY h.batch_hour
        ORDER BY h.batch_hour
    """
    res_items = con.execute(items_overall_sql).fetchall()
    for h_ts, rc, dkr, nc, np_r, nf_r, lag, pm, pp50, pp95, fm, fp50, fp95 in res_items:
        rows.append(("raw_items", "items_row_count", "ALL", h_ts, float(rc)))
        rows.append(("raw_items", "items_distinct_key_ratio", "ALL", h_ts, float(dkr)))
        rows.append(("raw_items", "items_null_rate_category", "ALL", h_ts, float(nc)))
        rows.append(("raw_items", "items_null_rate_price", "ALL", h_ts, float(np_r)))
        rows.append(("raw_items", "items_null_rate_freight", "ALL", h_ts, float(nf_r)))
        rows.append(("raw_items", "items_arrival_lag_p50", "ALL", h_ts, float(lag)))
        rows.append(("raw_items", "items_price_mean", "ALL", h_ts, float(pm)))
        rows.append(("raw_items", "items_price_p50", "ALL", h_ts, float(pp50)))
        rows.append(("raw_items", "items_price_p95", "ALL", h_ts, float(pp95)))
        rows.append(("raw_items", "items_freight_mean", "ALL", h_ts, float(fm)))
        rows.append(("raw_items", "items_freight_p50", "ALL", h_ts, float(fp50)))
        rows.append(("raw_items", "items_freight_p95", "ALL", h_ts, float(fp95)))

    # Items Segment Metrics: category
    items_category_sql = """
        WITH cat_grid AS (
            SELECT h.batch_hour, c.category
            FROM tgt_hours h
            CROSS JOIN (SELECT unnest($categories) AS category) c
        ),
        counts AS (
            SELECT
                h.batch_hour,
                i.category,
                COALESCE(SUM(i.price), 0.0) AS cat_sum,
                COUNT(*) AS cat_cnt
            FROM tgt_hours h
            JOIN raw_items i ON h.batch_hour = i.batch_hour
            WHERE i.category IS NOT NULL
            GROUP BY h.batch_hour, i.category
        ),
        totals AS (
            SELECT h.batch_hour, COUNT(*) AS tot_items
            FROM tgt_hours h
            JOIN raw_items i ON h.batch_hour = i.batch_hour
            GROUP BY h.batch_hour
        )
        SELECT
            g.batch_hour AS hour_ts,
            g.category,
            COALESCE(c.cat_sum, 0.0) AS category_sum,
            COALESCE(CAST(c.cat_cnt AS DOUBLE) / NULLIF(t.tot_items, 0), 0.0) AS category_share
        FROM cat_grid g
        LEFT JOIN counts c ON g.batch_hour = c.batch_hour AND g.category = c.category
        LEFT JOIN totals t ON g.batch_hour = t.batch_hour
        ORDER BY g.batch_hour, g.category
    """
    res_cats = con.execute(items_category_sql, {"categories": CATEGORIES}).fetchall()
    for h_ts, cat, c_sum, c_share in res_cats:
        rows.append(("raw_items", "items_category_sum", str(cat), h_ts, float(c_sum)))
        rows.append(("raw_items", "items_category_share", str(cat), h_ts, float(c_share)))

    # ==========================================================================
    # 3. RAW PAYMENTS METRICS (Group: payments)
    # ==========================================================================
    payments_overall_sql = """
        SELECT
            h.batch_hour AS hour_ts,
            COALESCE(COUNT(p.order_id), 0) AS row_count,
            COALESCE(COUNT(DISTINCT p.order_id) / NULLIF(COUNT(p.order_id), 0), 1.0) AS distinct_key_ratio,
            COALESCE(COUNT(CASE WHEN p.payment_type IS NULL THEN 1 END) / NULLIF(COUNT(p.order_id), 0), 0.0) AS null_rate_payment_type,
            COALESCE(COUNT(CASE WHEN p.payment_value IS NULL THEN 1 END) / NULLIF(COUNT(p.order_id), 0), 0.0) AS null_rate_payment_value,
            COALESCE(quantile_cont(epoch(p.landed_ts) - epoch(p.event_ts), 0.5) / 60.0, 0.0) AS arrival_lag_p50,
            COALESCE(AVG(p.payment_value), 0.0) AS value_mean,
            COALESCE(quantile_cont(p.payment_value, 0.5), 0.0) AS value_p50,
            COALESCE(quantile_cont(p.payment_value, 0.95), 0.0) AS value_p95
        FROM tgt_hours h
        LEFT JOIN raw_payments p ON h.batch_hour = p.batch_hour
        GROUP BY h.batch_hour
        ORDER BY h.batch_hour
    """
    res_payments = con.execute(payments_overall_sql).fetchall()
    for h_ts, rc, dkr, npt, npv, lag, vm, vp50, vp95 in res_payments:
        rows.append(("raw_payments", "payments_row_count", "ALL", h_ts, float(rc)))
        rows.append(("raw_payments", "payments_distinct_key_ratio", "ALL", h_ts, float(dkr)))
        rows.append(("raw_payments", "payments_null_rate_payment_type", "ALL", h_ts, float(npt)))
        rows.append(("raw_payments", "payments_null_rate_payment_value", "ALL", h_ts, float(npv)))
        rows.append(("raw_payments", "payments_arrival_lag_p50", "ALL", h_ts, float(lag)))
        rows.append(("raw_payments", "payments_value_mean", "ALL", h_ts, float(vm)))
        rows.append(("raw_payments", "payments_value_p50", "ALL", h_ts, float(vp50)))
        rows.append(("raw_payments", "payments_value_p95", "ALL", h_ts, float(vp95)))

    # Payments Segment Metrics: payment_type
    payments_type_sql = """
        WITH ptype_grid AS (
            SELECT h.batch_hour, pt.payment_type
            FROM tgt_hours h
            CROSS JOIN (SELECT unnest($ptypes) AS payment_type) pt
        ),
        sums AS (
            SELECT
                h.batch_hour,
                p.payment_type,
                COALESCE(SUM(p.payment_value), 0.0) AS pt_sum
            FROM tgt_hours h
            JOIN raw_payments p ON h.batch_hour = p.batch_hour
            WHERE p.payment_type IS NOT NULL
            GROUP BY h.batch_hour, p.payment_type
        ),
        totals AS (
            SELECT h.batch_hour, COALESCE(SUM(payment_value), 0.0) AS tot_val
            FROM tgt_hours h
            JOIN raw_payments p ON h.batch_hour = p.batch_hour
            GROUP BY h.batch_hour
        )
        SELECT
            g.batch_hour AS hour_ts,
            g.payment_type,
            COALESCE(s.pt_sum, 0.0) AS type_sum,
            COALESCE(CAST(s.pt_sum AS DOUBLE) / NULLIF(t.tot_val, 0.0), 0.0) AS type_share
        FROM ptype_grid g
        LEFT JOIN sums s ON g.batch_hour = s.batch_hour AND g.payment_type = s.payment_type
        LEFT JOIN totals t ON g.batch_hour = t.batch_hour
        ORDER BY g.batch_hour, g.payment_type
    """
    res_ptypes = con.execute(payments_type_sql, {"ptypes": PAYMENT_TYPES}).fetchall()
    for h_ts, pt, p_sum, p_share in res_ptypes:
        rows.append(("raw_payments", "payments_type_sum", str(pt), h_ts, float(p_sum)))
        rows.append(("raw_payments", "payments_type_share", str(pt), h_ts, float(p_share)))

    # ==========================================================================
    # 4. CROSS-TABLE INVARIANTS & RECONCILIATION (Group: totals)
    # ==========================================================================
    invariants_sql = """
        WITH h_orders AS (
            SELECT h.batch_hour, COUNT(DISTINCT o.order_id) AS distinct_orders, COUNT(o.order_id) AS total_orders
            FROM tgt_hours h
            LEFT JOIN raw_orders o ON h.batch_hour = o.batch_hour
            GROUP BY h.batch_hour
        ),
        h_items AS (
            SELECT
                h.batch_hour,
                COUNT(i.item_id) AS total_items,
                COALESCE(SUM(i.price + i.freight), 0.0) AS items_val,
                COUNT(CASE WHEN o.order_id IS NULL THEN 1 END) AS orphan_items
            FROM tgt_hours h
            LEFT JOIN raw_items i ON h.batch_hour = i.batch_hour
            LEFT JOIN raw_orders o ON i.order_id = o.order_id AND i.batch_hour = o.batch_hour
            GROUP BY h.batch_hour
        ),
        h_payments AS (
            SELECT
                h.batch_hour,
                COUNT(p.order_id) AS total_payments,
                COUNT(DISTINCT p.order_id) AS distinct_pay_orders,
                COALESCE(SUM(p.payment_value), 0.0) AS payments_val,
                COUNT(CASE WHEN o.order_id IS NULL THEN 1 END) AS orphan_payments
            FROM tgt_hours h
            LEFT JOIN raw_payments p ON h.batch_hour = p.batch_hour
            LEFT JOIN raw_orders o ON p.order_id = o.order_id AND p.batch_hour = o.batch_hour
            GROUP BY h.batch_hour
        )
        SELECT
            h.batch_hour AS hour_ts,
            COALESCE(hp.payments_val / NULLIF(hi.items_val, 0.0), 0.0) AS payments_to_items_ratio,
            COALESCE(CAST(hp.distinct_pay_orders AS DOUBLE) / NULLIF(ho.distinct_orders, 0), 1.0) AS orders_with_payment_rate,
            COALESCE(CAST(hi.orphan_items AS DOUBLE) / NULLIF(hi.total_items, 0), 0.0) AS orphan_item_rate,
            COALESCE(CAST(hp.orphan_payments AS DOUBLE) / NULLIF(hp.total_payments, 0), 0.0) AS orphan_payment_rate,
            COALESCE(CAST(hi.total_items AS DOUBLE) / NULLIF(ho.distinct_orders, 0), 0.0) AS items_per_order
        FROM tgt_hours h
        LEFT JOIN h_orders ho ON h.batch_hour = ho.batch_hour
        LEFT JOIN h_items hi ON h.batch_hour = hi.batch_hour
        LEFT JOIN h_payments hp ON h.batch_hour = hp.batch_hour
        ORDER BY h.batch_hour
    """
    res_invariants = con.execute(invariants_sql).fetchall()
    for h_ts, p_to_i, ord_pay_rate, orph_i, orph_p, ipo in res_invariants:
        rows.append(("int_order_totals", "payments_to_items_ratio", "ALL", h_ts, float(p_to_i)))
        rows.append(("int_order_totals", "orders_with_payment_rate", "ALL", h_ts, float(ord_pay_rate)))
        rows.append(("int_order_totals", "orphan_item_rate", "ALL", h_ts, float(orph_i)))
        rows.append(("int_order_totals", "orphan_payment_rate", "ALL", h_ts, float(orph_p)))
        rows.append(("int_order_totals", "items_per_order", "ALL", h_ts, float(ipo)))

    # Reconciliation with Control Totals
    recon_sql = """
        WITH landed_orders AS (
            SELECT h.batch_hour, COUNT(*) AS landed_rows
            FROM tgt_hours h JOIN raw_orders o ON h.batch_hour = o.batch_hour GROUP BY h.batch_hour
        ),
        landed_items AS (
            SELECT h.batch_hour, COUNT(*) AS landed_rows, COALESCE(SUM(price + freight), 0.0) AS landed_val
            FROM tgt_hours h JOIN raw_items i ON h.batch_hour = i.batch_hour GROUP BY h.batch_hour
        ),
        landed_payments AS (
            SELECT h.batch_hour, COUNT(*) AS landed_rows, COALESCE(SUM(payment_value), 0.0) AS landed_val
            FROM tgt_hours h JOIN raw_payments p ON h.batch_hour = p.batch_hour GROUP BY h.batch_hour
        ),
        ctrl_orders AS (
            SELECT h.batch_hour, COALESCE(c.true_row_count, 0) AS ctrl_rows
            FROM tgt_hours h
            LEFT JOIN control_totals c ON h.batch_hour = c.batch_hour AND c.table_name = 'raw_orders'
        ),
        ctrl_items AS (
            SELECT h.batch_hour, COALESCE(c.true_row_count, 0) AS ctrl_rows, COALESCE(c.true_value_sum, 0.0) AS ctrl_val
            FROM tgt_hours h
            LEFT JOIN control_totals c ON h.batch_hour = c.batch_hour AND c.table_name = 'raw_items'
        ),
        ctrl_payments AS (
            SELECT h.batch_hour, COALESCE(c.true_row_count, 0) AS ctrl_rows, COALESCE(c.true_value_sum, 0.0) AS ctrl_val
            FROM tgt_hours h
            LEFT JOIN control_totals c ON h.batch_hour = c.batch_hour AND c.table_name = 'raw_payments'
        )
        SELECT
            h.batch_hour AS hour_ts,
            ABS(COALESCE(lo.landed_rows, 0) - COALESCE(co.ctrl_rows, 0)) AS gap_rows_o,
            ABS(COALESCE(li.landed_rows, 0) - COALESCE(ci.ctrl_rows, 0)) AS gap_rows_i,
            ABS(COALESCE(li.landed_val, 0.0) - COALESCE(ci.ctrl_val, 0.0)) AS gap_val_i,
            ABS(COALESCE(lp.landed_rows, 0) - COALESCE(cp.ctrl_rows, 0)) AS gap_rows_p,
            ABS(COALESCE(lp.landed_val, 0.0) - COALESCE(cp.ctrl_val, 0.0)) AS gap_val_p
        FROM tgt_hours h
        LEFT JOIN landed_orders lo ON h.batch_hour = lo.batch_hour
        LEFT JOIN landed_items li ON h.batch_hour = li.batch_hour
        LEFT JOIN landed_payments lp ON h.batch_hour = lp.batch_hour
        LEFT JOIN ctrl_orders co ON h.batch_hour = co.batch_hour
        LEFT JOIN ctrl_items ci ON h.batch_hour = ci.batch_hour
        LEFT JOIN ctrl_payments cp ON h.batch_hour = cp.batch_hour
        ORDER BY h.batch_hour
    """
    res_recon = con.execute(recon_sql).fetchall()
    for h_ts, gr_o, gr_i, gv_i, gr_p, gv_p in res_recon:
        rows.append(("raw_orders", "control_total_gap_rows_orders", "ALL", h_ts, float(gr_o)))
        rows.append(("raw_items", "control_total_gap_rows_items", "ALL", h_ts, float(gr_i)))
        rows.append(("raw_items", "control_total_gap_value_items", "ALL", h_ts, float(gv_i)))
        rows.append(("raw_payments", "control_total_gap_rows_payments", "ALL", h_ts, float(gr_p)))
        rows.append(("raw_payments", "control_total_gap_value_payments", "ALL", h_ts, float(gv_p)))

    # ==========================================================================
    # 5. MART METRICS (Group: mart)
    # ==========================================================================
    mart_sql = """
        SELECT
            h.batch_hour AS hour_ts,
            COALESCE(m.revenue, 0.0) AS hourly_revenue,
            COALESCE(m.order_count, 0) AS order_count,
            COALESCE(m.total_items, 0) AS total_items,
            COALESCE(m.revenue / NULLIF(m.order_count, 0), 0.0) AS aov
        FROM tgt_hours h
        LEFT JOIN mart_revenue_hourly m ON h.batch_hour = m.batch_hour
        ORDER BY h.batch_hour
    """
    res_mart = con.execute(mart_sql).fetchall()
    for h_ts, rev, oc, ti, aov in res_mart:
        rows.append(("mart_revenue_hourly", "mart_hourly_revenue", "ALL", h_ts, float(rev)))
        rows.append(("mart_revenue_hourly", "mart_order_count", "ALL", h_ts, float(oc)))
        rows.append(("mart_revenue_hourly", "mart_total_items", "ALL", h_ts, float(ti)))
        rows.append(("mart_revenue_hourly", "mart_aov", "ALL", h_ts, float(aov)))

    con.unregister("tgt_hours")

    df = pd.DataFrame(rows, columns=["node", "metric", "segment", "hour_ts", "value"])

    # Guaranteed clean float and finite values
    df["value"] = np.nan_to_num(df["value"].values, nan=0.0, posinf=0.0, neginf=0.0)
    return df
