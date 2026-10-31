"""Demo Verification Script for Phase 1 Simulation & Failure Injection."""

import sys
import time
from typing import Dict
import pandas as pd

from app.sim.event_log import EventLogger
from app.sim.failures import inject_unit_scale_slice
from app.sim.generator import generate_hourly_batch
from app.sim.pipeline import PipelineEngine


def run_demo_check(num_hours: int = 48, master_seed: int = 42):
    """
    Executes a multi-hour simulation run and evaluates clean vs injected performance.
    """
    start_time = time.perf_counter()
    print("=" * 80)
    print("           EXATHON SIMULATED PIPELINE & FAILURE INJECTOR DEMO")
    print("=" * 80)
    print(f"[*] Simulating {num_hours} hours of e-commerce pipeline stream...")

    # 1. CLEAN RUN
    clean_event_logger = EventLogger(":memory:")
    clean_engine = PipelineEngine(":memory:", event_logger=clean_event_logger, master_seed=master_seed)

    for h in range(num_hours):
        clean_engine.ingest(h)

    clean_table_counts = clean_engine.get_table_counts()
    clean_revenue = clean_engine.con.execute(
        "SELECT SUM(revenue) FROM mart_revenue_hourly"
    ).fetchone()[0] or 0.0

    clean_voucher_rev = clean_engine.con.execute(
        "SELECT SUM(payment_value) FROM int_order_totals WHERE payment_type = 'voucher'"
    ).fetchone()[0] or 0.0

    # 2. INJECTED RUN (unit_scale_slice on voucher)
    injected_event_logger = EventLogger(":memory:")
    injected_engine = PipelineEngine(":memory:", event_logger=injected_event_logger, master_seed=master_seed)

    # Inject failure starting at hour 12 through end of simulation
    injection_onset = 12
    for h in range(num_hours):
        orders, items, payments = generate_hourly_batch(h, master_seed=master_seed)
        active_failures = []
        if h >= injection_onset:
            payments, gt = inject_unit_scale_slice(
                payments,
                onset_hour=injection_onset,
                end_hour=num_hours - 1,
                payment_type="voucher",
                scale=0.01,
            )
            active_failures.append(gt)

        injected_engine.ingest(
            h,
            orders_df=orders,
            items_df=items,
            payments_df=payments,
            active_failures=active_failures,
        )

    injected_table_counts = injected_engine.get_table_counts()
    injected_revenue = injected_engine.con.execute(
        "SELECT SUM(revenue) FROM mart_revenue_hourly"
    ).fetchone()[0] or 0.0

    injected_voucher_rev = injected_engine.con.execute(
        "SELECT SUM(payment_value) FROM int_order_totals WHERE payment_type = 'voucher'"
    ).fetchone()[0] or 0.0

    elapsed = time.perf_counter() - start_time

    # 3. PRINT TABLE ROW COUNTS
    print("\n" + "-" * 80)
    print("TABLE ROW COUNTS (DuckDB Pipeline Storage)")
    print("-" * 80)
    col_w_t = 28
    col_w_c = 18
    print(f"| {'Table Name':<{col_w_t}} | {'Clean Rows':<{col_w_c}} | {'Injected Rows':<{col_w_c}} |")
    print(f"|{'-' * (col_w_t + 2)}|{'-' * (col_w_c + 2)}|{'-' * (col_w_c + 2)}|")
    for tbl, count in clean_table_counts.items():
        inj_count = injected_table_counts.get(tbl, 0)
        print(f"| {tbl:<{col_w_t}} | {count:<{col_w_c},} | {inj_count:<{col_w_c},} |")

    # 4. PRINT CLEAN VS INJECTED COMPARISON
    revenue_drop = clean_revenue - injected_revenue
    drop_pct = (revenue_drop / clean_revenue * 100.0) if clean_revenue > 0 else 0.0

    voucher_drop = clean_voucher_rev - injected_voucher_rev
    voucher_drop_pct = (voucher_drop / clean_voucher_rev * 100.0) if clean_voucher_rev > 0 else 0.0

    print("\n" + "-" * 80)
    print("CLEAN VS. INJECTED COMPARISON: unit_scale_slice(voucher)")
    print("-" * 80)
    print(f"  Injection Window        : Hours {injection_onset} .. {num_hours - 1}")
    print(f"  Target Payment Type     : voucher (scaling payment_value x0.01)")
    print(f"  Clean Total Revenue     : ${clean_revenue:,.2f}")
    print(f"  Injected Total Revenue  : ${injected_revenue:,.2f}")
    print(f"  Total Revenue Drop      : -${revenue_drop:,.2f} ({drop_pct:.2f}%)")
    print(f"  Voucher Clean Revenue   : ${clean_voucher_rev:,.2f}")
    print(f"  Voucher Injected Revenue: ${injected_voucher_rev:,.2f}")
    print(f"  Voucher Revenue Drop    : -${voucher_drop:,.2f} ({voucher_drop_pct:.2f}%)")

    # Event log true causes check
    true_causes = injected_event_logger.get_true_causes()
    print(f"\n  Recorded True Causes in SQLite: {len(true_causes)} events logged")
    print("-" * 80)
    print(f"[+] Total Execution Time: {elapsed:.2f} seconds (< 60s target: PASS)")
    print("=" * 80 + "\n")

    clean_engine.close()
    injected_engine.close()
    clean_event_logger.close()
    injected_event_logger.close()

    assert elapsed < 60.0, f"Execution took {elapsed:.2f}s which exceeds 60s limit!"
    return 0


if __name__ == "__main__":
    sys.exit(run_demo_check())
