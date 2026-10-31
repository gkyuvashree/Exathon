"""SQLite Time-Series Metric Store for Pipeline Observability."""

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union
import numpy as np
import pandas as pd


class MetricStore:
    """Manages storage and retrieval of time-series observability metrics in SQLite."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None or db_path == ":memory:":
            self.db_path = ":memory:"
        else:
            p = Path(db_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            self.db_path = str(p)

        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._init_schema()

    def _init_schema(self):
        """Create metrics_ts table with appropriate primary key and indices."""
        with self._conn:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS metrics_ts (
                    node TEXT NOT NULL,
                    metric TEXT NOT NULL,
                    segment TEXT NOT NULL DEFAULT 'ALL',
                    hour_ts INTEGER NOT NULL,
                    value REAL NOT NULL,
                    PRIMARY KEY (node, metric, segment, hour_ts)
                )
            """)
            self._conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_metrics_ts_lookup 
                ON metrics_ts(node, metric, segment, hour_ts)
            """)
            self._conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_metrics_ts_hour 
                ON metrics_ts(hour_ts)
            """)
            self._conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_metrics_ts_metric 
                ON metrics_ts(metric, hour_ts)
            """)

    def write_metrics(self, records: Union[pd.DataFrame, Sequence[Dict[str, Any]], Sequence[tuple]]):
        """
        Efficiently write batch of metrics into metrics_ts using INSERT OR REPLACE.
        Accepts DataFrame or list of dicts/tuples (node, metric, segment, hour_ts, value).
        """
        if isinstance(records, pd.DataFrame):
            if records.empty:
                return
            data = records[["node", "metric", "segment", "hour_ts", "value"]].to_records(index=False)
            rows = [
                (
                    str(r[0]),
                    str(r[1]),
                    str(r[2]),
                    int(r[3]),
                    float(r[4]) if np.isfinite(r[4]) else 0.0,
                )
                for r in data
            ]
        elif len(records) > 0 and isinstance(records[0], dict):
            rows = [
                (
                    str(r["node"]),
                    str(r["metric"]),
                    str(r.get("segment", "ALL")),
                    int(r["hour_ts"]),
                    float(r["value"]) if np.isfinite(r["value"]) else 0.0,
                )
                for r in records
            ]
        else:
            rows = [
                (
                    str(r[0]),
                    str(r[1]),
                    str(r[2]),
                    int(r[3]),
                    float(r[4]) if np.isfinite(r[4]) else 0.0,
                )
                for r in records
            ]

        with self._conn:
            self._conn.executemany(
                "INSERT OR REPLACE INTO metrics_ts (node, metric, segment, hour_ts, value) VALUES (?, ?, ?, ?, ?)",
                rows,
            )

    def get_metrics(
        self,
        node: Optional[str] = None,
        metric: Optional[str] = None,
        segment: Optional[str] = None,
        hour_ts: Optional[int] = None,
        start_hour: Optional[int] = None,
        end_hour: Optional[int] = None,
    ) -> pd.DataFrame:
        """Query time series metrics with optional multi-attribute filters."""
        query = "SELECT node, metric, segment, hour_ts, value FROM metrics_ts"
        clauses = []
        params = []

        if node:
            clauses.append("node = ?")
            params.append(node)
        if metric:
            clauses.append("metric = ?")
            params.append(metric)
        if segment:
            clauses.append("segment = ?")
            params.append(segment)
        if hour_ts is not None:
            clauses.append("hour_ts = ?")
            params.append(hour_ts)
        if start_hour is not None:
            clauses.append("hour_ts >= ?")
            params.append(start_hour)
        if end_hour is not None:
            clauses.append("hour_ts <= ?")
            params.append(end_hour)

        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY hour_ts ASC, node ASC, metric ASC, segment ASC"

        return pd.read_sql_query(query, self._conn, params=params)

    def count(self) -> int:
        """Return total row count in metrics_ts."""
        cur = self._conn.cursor()
        cur.execute("SELECT COUNT(*) FROM metrics_ts")
        res = cur.fetchone()
        return res[0] if res else 0

    def get_distinct_hours(self) -> List[int]:
        """Return sorted list of distinct hour_ts present in metrics_ts."""
        cur = self._conn.cursor()
        cur.execute("SELECT DISTINCT hour_ts FROM metrics_ts ORDER BY hour_ts ASC")
        return [row[0] for row in cur.fetchall()]

    def close(self):
        """Close SQLite connection."""
        self._conn.close()
