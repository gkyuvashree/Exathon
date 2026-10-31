# Phase 1 Verification Report: Simulated E-Commerce Pipeline & Failure Injector

**Date & Time**: 2026-10-31T12:08:00+05:30  
**Repository**: `C:\Users\Yuvashree\OneDrive\Desktop\Exathon`  
**Status**: ALL PASS  

---

## 1. Phase 1 Overview

Phase 1 implements the full simulated e-commerce data pipeline, deterministic hourly data generation, 9 labeled failure injectors, 2 hard negatives, SQLite event logging, DuckDB pipeline DAG transformations with control totals, and a comprehensive validation test suite.

### Architecture Components:
- **`config/lineage.yaml` & `backend/config/lineage.yaml`**: Complete DAG lineage specification across Raw $\rightarrow$ Staging $\rightarrow$ Intermediate $\rightarrow$ Mart $\rightarrow$ KPI layers.
- **`backend/app/sim/config.py`**: Domain parameters (150 days horizon, promo days 35/70/105/125, Poisson arrival rate $\lambda(h)$, lognormal noise $\sigma=0.05$, daily & weekly profiles, 6 weighted categories, 8 weighted states, 4 payment types, 8% coupon probability).
- **`backend/app/sim/generator.py`**: Fast NumPy-vectorized synthetic hourly stream generator for `orders`, `order_items`, and `payments` tables with deterministic hour-keyed RNG.
- **`backend/app/sim/failures.py`**: 9 labeled failure injectors (`unit_scale_slice`, `partial_load`, `duplicate_replay`, `stale_source`, `schema_drift_nulls`, `default_fill`, `timezone_shift`, `orphan_keys`, `join_fanout`) + 2 hard negatives (`promo_surge`, `category_flash_sale`) returning standardized ground-truth records.
- **`backend/app/sim/event_log.py`**: SQLite event logger recording verified true cause events alongside 3–5 daily realistic decoy ops/infra events.
- **`backend/app/sim/pipeline.py`**: DuckDB pipeline engine executing exact-duplicate deduplication, pre-aggregated joins, hourly revenue mart rollups, daily revenue/AOV KPIs, and pre-injection control totals.
- **`backend/app/sim/demo_check.py`**: Verification script demonstrating clean vs. injected pipeline comparisons and performance benchmarks.
- **`backend/tests/test_phase1.py`**: 15 comprehensive unit & integration tests validating determinism, domain integrity, slice isolation, SQLite ground truth, control totals, and DAG acyclicity.

---

## 2. Pytest Execution (`cd backend && python -m pytest -q`)

Command executed:
```powershell
cd backend
python -m pytest -q
```

### Output:
```text
................                                                         [100%]
16 passed in 1.28s
```

**Result**: PASS (16/16 passed in 1.28s, including Phase 0 health smoke test and 15 Phase 1 tests)

---

## 3. Demo Check Execution (`python -m app.sim.demo_check`)

Command executed:
```powershell
cd backend
python -m app.sim.demo_check
```

### Output:
```text
================================================================================
           EXATHON SIMULATED PIPELINE & FAILURE INJECTOR DEMO
================================================================================
[*] Simulating 48 hours of e-commerce pipeline stream...

--------------------------------------------------------------------------------
TABLE ROW COUNTS (DuckDB Pipeline Storage)
--------------------------------------------------------------------------------
| Table Name                   | Clean Rows         | Injected Rows      |
|------------------------------|--------------------|--------------------|
| raw_orders                   | 6,806              | 6,806              |
| raw_items                    | 17,239             | 17,239             |
| raw_payments                 | 6,806              | 6,806              |
| stg_orders                   | 6,806              | 6,806              |
| stg_items                    | 17,239             | 17,239             |
| stg_payments                 | 6,806              | 6,806              |
| int_order_totals             | 6,806              | 6,806              |
| mart_revenue_hourly          | 48                 | 48                 |
| kpi_daily_revenue            | 2                  | 2                  |
| kpi_aov                      | 2                  | 2                  |
| control_totals               | 144                | 144                |

--------------------------------------------------------------------------------
CLEAN VS. INJECTED COMPARISON: unit_scale_slice(voucher)
--------------------------------------------------------------------------------
  Injection Window        : Hours 12 .. 47
  Target Payment Type     : voucher (scaling payment_value x0.01)
  Clean Total Revenue     : $992,453.54
  Injected Total Revenue  : $900,407.64
  Total Revenue Drop      : -$92,045.90 (9.27%)
  Voucher Clean Revenue   : $114,963.11
  Voucher Injected Revenue: $22,917.21
  Voucher Revenue Drop    : -$92,045.90 (80.07%)

  Recorded True Causes in SQLite: 36 events logged
--------------------------------------------------------------------------------
[+] Total Execution Time: 2.97 seconds (< 60s target: PASS)
================================================================================
```

**Result**: PASS (Completed in 2.97 seconds, well under the 60-second limit)

---

## 4. Verification of Acceptance Criteria

1. **Same seed $\Rightarrow$ byte-identical history**: Tested and confirmed via `test_same_seed_byte_identical_history` using `pd.testing.assert_frame_equal(..., check_exact=True)`.
2. **Clean data satisfies `payment_value ~ items_total` within coupon tolerance**: Tested across orders with mean ratio $\sim 0.99$ and coupon ratio in $[0.85, 0.95]$.
3. **Each injector changes ONLY its intended slice/stage**: Verified for all 9 injectors and hard negatives.
4. **Ground truth is recorded**: Standardized ground-truth records stored in SQLite event log alongside decoy ops events.
5. **Control totals reflect pre-injection truth**: Clean source totals recorded in `control_totals` table in DuckDB before any injection.
6. **DAG loads and is acyclic**: Validated `config/lineage.yaml` via cycle-detection traversal.
