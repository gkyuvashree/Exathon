"""DuckDB Pipeline DAG Implementation with Lineage and Control Totals."""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import duckdb
import pandas as pd
import yaml

from .config import HOURS_PER_DAY
from .event_log import EventLogger
from .generator import generate_hourly_batch


def find_lineage_yaml() -> Path:
    """Find the lineage.yaml configuration file."""
    candidates = [
        Path("config/lineage.yaml"),
        Path("backend/config/lineage.yaml"),
        Path(__file__).resolve().parent.parent.parent.parent / "config" / "lineage.yaml",
        Path(__file__).resolve().parent.parent.parent / "config" / "lineage.yaml",
    ]
    for c in candidates:
        if c.exists():
            return c
    raise FileNotFoundError("Could not find config/lineage.yaml")


def load_lineage_config(path: Optional[Path] = None) -> Dict[str, Any]:
    """Load and parse the pipeline lineage YAML declaration."""
    p = path or find_lineage_yaml()
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def is_dag_acyclic(lineage: Dict[str, Any]) -> bool:
    """Verify that the DAG defined in lineage configuration has no cycles."""
    nodes = lineage.get("nodes", {})
    adj = {k: v.get("dependencies", []) for k, v in nodes.items()}

    # Standard cycle detection using DFS
    visited = {}  # node -> 0 (visiting), 1 (visited)

    def dfs(node: str) -> bool:
        if node in visited:
            return visited[node] == 1
        visited[node] = 0
        for neighbor in adj.get(node, []):
            if neighbor in adj:  # only visit nodes within the DAG
                if not dfs(neighbor):
                    return False
        visited[node] = 1
        return True

    for n in adj:
        if n not in visited:
            if not dfs(n):
                return False
    return True


class PipelineEngine:
    """
    Manages DuckDB tables, transformations, control totals, and hourly ingestion.
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        event_logger: Optional[EventLogger] = None,
        master_seed: int = 42,
    ):
        if db_path is None or db_path == ":memory:":
            self.db_path = ":memory:"
        else:
            p = Path(db_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            self.db_path = str(p)

        self.con = duckdb.connect(self.db_path)
        self.event_logger = event_logger or EventLogger(":memory:")
        self.master_seed = master_seed
        self.lineage = load_lineage_config()
        self._init_schema()

    def _init_schema(self):
        """Initialize all DuckDB tables and views."""
        # 0. CONTROL TOTALS
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS control_totals (
                batch_hour INTEGER,
                table_name VARCHAR,
                true_row_count BIGINT,
                true_value_sum DOUBLE,
                PRIMARY KEY (batch_hour, table_name)
            )
        """)

        # 1. RAW LAYER
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS raw_orders (
                order_id VARCHAR,
                customer_id VARCHAR,
                state VARCHAR,
                status VARCHAR,
                event_ts TIMESTAMP,
                landed_ts TIMESTAMP,
                batch_hour INTEGER
            )
        """)
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS raw_items (
                order_id VARCHAR,
                item_id VARCHAR,
                category VARCHAR,
                price DOUBLE,
                freight DOUBLE,
                event_ts TIMESTAMP,
                landed_ts TIMESTAMP,
                batch_hour INTEGER
            )
        """)
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS raw_payments (
                order_id VARCHAR,
                payment_type VARCHAR,
                payment_value DOUBLE,
                event_ts TIMESTAMP,
                landed_ts TIMESTAMP,
                batch_hour INTEGER
            )
        """)

        # 2. STAGING LAYER
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS stg_orders (
                order_id VARCHAR,
                customer_id VARCHAR,
                state VARCHAR,
                status VARCHAR,
                event_ts TIMESTAMP,
                landed_ts TIMESTAMP,
                batch_hour INTEGER
            )
        """)
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS stg_items (
                order_id VARCHAR,
                item_id VARCHAR,
                category VARCHAR,
                price DOUBLE,
                freight DOUBLE,
                event_ts TIMESTAMP,
                landed_ts TIMESTAMP,
                batch_hour INTEGER
            )
        """)
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS stg_payments (
                order_id VARCHAR,
                payment_type VARCHAR,
                payment_value DOUBLE,
                event_ts TIMESTAMP,
                landed_ts TIMESTAMP,
                batch_hour INTEGER
            )
        """)

        # 3. INTERMEDIATE LAYER
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS int_order_totals (
                batch_hour INTEGER,
                order_id VARCHAR,
                items_total DOUBLE,
                n_items INTEGER,
                payment_value DOUBLE,
                payment_type VARCHAR
            )
        """)

        # 4. MART LAYER
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS mart_revenue_hourly (
                batch_hour INTEGER PRIMARY KEY,
                revenue DOUBLE,
                order_count BIGINT,
                total_items BIGINT
            )
        """)

        # 5. KPI LAYER
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS kpi_daily_revenue (
                batch_day INTEGER PRIMARY KEY,
                daily_revenue DOUBLE,
                daily_orders BIGINT,
                daily_items BIGINT
            )
        """)
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS kpi_aov (
                batch_day INTEGER PRIMARY KEY,
                aov DOUBLE
            )
        """)

    def record_control_totals(
        self,
        batch_hour: int,
        orders_df: pd.DataFrame,
        items_df: pd.DataFrame,
        payments_df: pd.DataFrame,
    ):
        """Record pre-injection true control totals."""
        orders_rows = len(orders_df)
        items_rows = len(items_df)
        payments_rows = len(payments_df)

        items_sum = float(items_df["price"].sum() + items_df["freight"].sum()) if items_rows > 0 else 0.0
        payments_sum = float(payments_df["payment_value"].sum()) if payments_rows > 0 else 0.0

        records = [
            (batch_hour, "raw_orders", orders_rows, 0.0),
            (batch_hour, "raw_items", items_rows, items_sum),
            (batch_hour, "raw_payments", payments_rows, payments_sum),
        ]
        self.con.executemany(
            "INSERT OR REPLACE INTO control_totals VALUES (?, ?, ?, ?)",
            records,
        )

    def ingest(
        self,
        batch_hour: int,
        orders_df: Optional[pd.DataFrame] = None,
        items_df: Optional[pd.DataFrame] = None,
        payments_df: Optional[pd.DataFrame] = None,
        clean_orders_df: Optional[pd.DataFrame] = None,
        clean_items_df: Optional[pd.DataFrame] = None,
        clean_payments_df: Optional[pd.DataFrame] = None,
        active_failures: Optional[List[Dict[str, Any]]] = None,
    ):
        """
        Ingests data for a given batch hour into DuckDB through all DAG stages.
        Calculates control totals before applying any injections.
        """
        failures = active_failures or []

        # Determine clean baseline for control totals
        clean_gen_orders, clean_gen_items, clean_gen_payments = generate_hourly_batch(
            batch_hour, master_seed=self.master_seed
        )

        c_orders = clean_orders_df if clean_orders_df is not None else (clean_gen_orders if failures else (orders_df if orders_df is not None else clean_gen_orders))
        c_items = clean_items_df if clean_items_df is not None else (clean_gen_items if failures else (items_df if items_df is not None else clean_gen_items))
        c_payments = clean_payments_df if clean_payments_df is not None else (clean_gen_payments if failures else (payments_df if payments_df is not None else clean_gen_payments))

        # 1. Record Pre-Injection Control Totals ALWAYS from clean source
        self.record_control_totals(batch_hour, c_orders, c_items, c_payments)

        # 2. Assign dataframes to ingest
        if orders_df is None:
            orders_df = clean_gen_orders.copy()
        if items_df is None:
            items_df = clean_gen_items.copy()
        if payments_df is None:
            payments_df = clean_gen_payments.copy()

        # 3. Check for join_fanout transform-level failure
        join_fanout_active = any(f.get("type") == "join_fanout" for f in failures)

        # 4. Insert into RAW tables
        self.con.register("tmp_orders", orders_df)
        self.con.register("tmp_items", items_df)
        self.con.register("tmp_payments", payments_df)

        self.con.execute("INSERT INTO raw_orders SELECT * FROM tmp_orders")
        self.con.execute("INSERT INTO raw_items SELECT * FROM tmp_items")
        self.con.execute("INSERT INTO raw_payments SELECT * FROM tmp_payments")

        # 5. Transform: RAW -> STAGING (type cast + exact-duplicate removal within batch)
        self.con.execute("""
            INSERT INTO stg_orders
            SELECT DISTINCT
                CAST(order_id AS VARCHAR),
                CAST(customer_id AS VARCHAR),
                CAST(state AS VARCHAR),
                CAST(status AS VARCHAR),
                CAST(event_ts AS TIMESTAMP),
                CAST(landed_ts AS TIMESTAMP),
                CAST(batch_hour AS INTEGER)
            FROM raw_orders
            WHERE batch_hour = ?
        """, [batch_hour])

        self.con.execute("""
            INSERT INTO stg_items
            SELECT DISTINCT
                CAST(order_id AS VARCHAR),
                CAST(item_id AS VARCHAR),
                CAST(category AS VARCHAR),
                CAST(price AS DOUBLE),
                CAST(freight AS DOUBLE),
                CAST(event_ts AS TIMESTAMP),
                CAST(landed_ts AS TIMESTAMP),
                CAST(batch_hour AS INTEGER)
            FROM raw_items
            WHERE batch_hour = ?
        """, [batch_hour])

        self.con.execute("""
            INSERT INTO stg_payments
            SELECT DISTINCT
                CAST(order_id AS VARCHAR),
                CAST(payment_type AS VARCHAR),
                CAST(payment_value AS DOUBLE),
                CAST(event_ts AS TIMESTAMP),
                CAST(landed_ts AS TIMESTAMP),
                CAST(batch_hour AS INTEGER)
            FROM raw_payments
            WHERE batch_hour = ?
        """, [batch_hour])

        # 6. Transform: STAGING -> INTERMEDIATE (int_order_totals)
        if join_fanout_active:
            # Transform-level bug: joins unaggregated items directly, causing row multiplication
            self.con.execute("""
                INSERT INTO int_order_totals
                SELECT
                    p.batch_hour,
                    p.order_id,
                    CAST(COALESCE(i.price + i.freight, 0.0) AS DOUBLE) AS items_total,
                    1 AS n_items,
                    CAST(p.payment_value AS DOUBLE) AS payment_value,
                    CAST(p.payment_type AS VARCHAR) AS payment_type
                FROM stg_payments p
                LEFT JOIN stg_items i ON p.order_id = i.order_id AND p.batch_hour = i.batch_hour
                WHERE p.batch_hour = ?
            """, [batch_hour])
        else:
            # Clean transform: LEFT joins on pre-aggregated items
            self.con.execute("""
                WITH pre_agg_items AS (
                    SELECT
                        order_id,
                        batch_hour,
                        SUM(price + freight) AS items_total,
                        COUNT(*) AS n_items
                    FROM stg_items
                    WHERE batch_hour = ?
                    GROUP BY order_id, batch_hour
                )
                INSERT INTO int_order_totals
                SELECT
                    p.batch_hour,
                    p.order_id,
                    CAST(COALESCE(i.items_total, 0.0) AS DOUBLE) AS items_total,
                    CAST(COALESCE(i.n_items, 0) AS INTEGER) AS n_items,
                    CAST(p.payment_value AS DOUBLE) AS payment_value,
                    CAST(p.payment_type AS VARCHAR) AS payment_type
                FROM stg_payments p
                LEFT JOIN pre_agg_items i ON p.order_id = i.order_id AND p.batch_hour = i.batch_hour
                WHERE p.batch_hour = ?
            """, [batch_hour, batch_hour])

        # 7. Transform: INTERMEDIATE -> MART (mart_revenue_hourly)
        self.con.execute("""
            INSERT OR REPLACE INTO mart_revenue_hourly
            SELECT
                batch_hour,
                CAST(SUM(payment_value) AS DOUBLE) AS revenue,
                COUNT(DISTINCT order_id) AS order_count,
                CAST(SUM(n_items) AS BIGINT) AS total_items
            FROM int_order_totals
            WHERE batch_hour = ?
            GROUP BY batch_hour
        """, [batch_hour])

        # 8. Transform: MART -> KPIS (kpi_daily_revenue, kpi_aov)
        batch_day = int(batch_hour // HOURS_PER_DAY)
        self.con.execute("""
            INSERT OR REPLACE INTO kpi_daily_revenue
            SELECT
                CAST(FLOOR(batch_hour / 24) AS INTEGER) AS batch_day,
                CAST(SUM(revenue) AS DOUBLE) AS daily_revenue,
                CAST(SUM(order_count) AS BIGINT) AS daily_orders,
                CAST(SUM(total_items) AS BIGINT) AS daily_items
            FROM mart_revenue_hourly
            WHERE CAST(FLOOR(batch_hour / 24) AS INTEGER) = ?
            GROUP BY CAST(FLOOR(batch_hour / 24) AS INTEGER)
        """, [batch_day])

        self.con.execute("""
            INSERT OR REPLACE INTO kpi_aov
            SELECT
                batch_day,
                CASE WHEN daily_orders > 0 THEN daily_revenue / daily_orders ELSE 0.0 END AS aov
            FROM kpi_daily_revenue
            WHERE batch_day = ?
        """, [batch_day])

        # Clean unregister
        self.con.unregister("tmp_orders")
        self.con.unregister("tmp_items")
        self.con.unregister("tmp_payments")

        # 9. Record true cause failures in EventLogger
        for f in failures:
            self.event_logger.record_true_cause(f)

    def get_table_counts(self) -> Dict[str, int]:
        """Return row counts for all tables across the pipeline."""
        tables = [
            "raw_orders", "raw_items", "raw_payments",
            "stg_orders", "stg_items", "stg_payments",
            "int_order_totals", "mart_revenue_hourly",
            "kpi_daily_revenue", "kpi_aov", "control_totals"
        ]
        counts = {}
        for t in tables:
            counts[t] = self.con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        return counts

    def close(self):
        self.con.close()
