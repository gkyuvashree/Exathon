"""SQLite Event Logger for True Cause Injected Failures and Decoy Ops Events."""

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd

from .config import HOURS_PER_DAY, SIMULATION_START_TS

DECOY_TEMPLATES = [
    ("deployment", "checkout-api", "Deploy: service {service} rolled out v{major}.{minor}.{patch}"),
    ("config_change", "redis-cache", "Config: updated {service} TTL from {v1}s to {v2}s"),
    ("infra_scaling", "k8s-cluster", "Infrastructure: auto-scaled {service} replica count to {count}"),
    ("cert_rotation", "api-gateway", "Security: automated SSL certificate renewal completed for {service}"),
    ("cron_job", "analytics-sync", "Scheduled Job: {service} batch finished successfully in {sec}s"),
    ("feature_flag", "cart-service", "Feature Flag: toggled '{flag}' to {val}% roll-out"),
    ("db_maintenance", "orders-db", "Maintenance: VACUUM ANALYZE completed on {service} tables"),
]


class EventLogger:
    """Manages SQLite event logging for true causes and decoy events."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None or db_path == ":memory:":
            self.db_path = ":memory:"
        else:
            p = Path(db_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            self.db_path = str(p)

        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._init_db()

    def _init_db(self):
        with self._conn:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,       -- 'true_cause' or 'decoy'
                    failure_type TEXT,              -- specific failure name if true_cause
                    stage TEXT NOT NULL,
                    onset_hour INTEGER NOT NULL,
                    end_hour INTEGER NOT NULL,
                    severity TEXT,
                    slice_json TEXT,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_onset_hour ON events(onset_hour)")
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_event_type ON events(event_type)")

    def record_true_cause(self, gt: Dict[str, Any]) -> str:
        """Record a verified injected ground-truth failure cause."""
        event_id = gt.get("id") or f"tc_{uuid.uuid4().hex[:8]}"
        onset = int(gt["onset_hour"])
        end = int(gt.get("end_hour", onset))
        stage = str(gt.get("stage", "unknown"))
        f_type = str(gt.get("type", "unknown"))
        severity = str(gt.get("severity", ""))
        slice_json = json.dumps(gt.get("slice", {}))
        
        event_ts = (SIMULATION_START_TS + timedelta(hours=onset)).isoformat()
        title = f"Failure Injected: {f_type} on {stage}"
        desc = f"Injected {f_type} on stage {stage} between hours {onset} and {end} with severity {severity}"

        with self._conn:
            self._conn.execute("""
                INSERT OR REPLACE INTO events 
                (event_id, event_type, failure_type, stage, onset_hour, end_hour, severity, slice_json, title, description, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (event_id, "true_cause", f_type, stage, onset, end, severity, slice_json, title, desc, event_ts))

        return event_id

    def generate_decoys_for_day(self, day: int, seed: int = 42) -> List[str]:
        """Generate 3 to 5 realistic decoy events for a single day."""
        rng = np.random.default_rng(seed + day * 37)
        num_decoys = int(rng.integers(3, 6))  # 3, 4, or 5 decoys per day

        inserted_ids = []
        for i in range(num_decoys):
            hour = day * HOURS_PER_DAY + int(rng.integers(0, 24))
            minute = int(rng.integers(0, 60))
            event_ts = (SIMULATION_START_TS + timedelta(hours=hour, minutes=minute)).isoformat()

            category, service, template = rng.choice(DECOY_TEMPLATES)
            title = f"Ops Event: {category.replace('_', ' ').title()}"
            desc = template.format(
                service=service,
                major=rng.integers(1, 4),
                minor=rng.integers(0, 20),
                patch=rng.integers(0, 10),
                v1=rng.choice([60, 120, 300]),
                v2=rng.choice([300, 600, 900]),
                count=rng.integers(3, 12),
                sec=rng.integers(15, 90),
                flag=rng.choice(["v2_search", "dynamic_pricing_preview", "one_click_pay"]),
                val=rng.choice([10, 25, 50]),
            )

            event_id = f"decoy_{day:03d}_{i}_{uuid.uuid4().hex[:6]}"
            with self._conn:
                self._conn.execute("""
                    INSERT OR REPLACE INTO events 
                    (event_id, event_type, failure_type, stage, onset_hour, end_hour, severity, slice_json, title, description, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (event_id, "decoy", None, f"infra_{category}", hour, hour, "info", "{}", title, desc, event_ts))
            inserted_ids.append(event_id)

        return inserted_ids

    def get_events(self, onset_hour_min: Optional[int] = None, onset_hour_max: Optional[int] = None) -> pd.DataFrame:
        """Retrieve events within an optional hour range."""
        query = "SELECT * FROM events"
        params = []
        conditions = []
        if onset_hour_min is not None:
            conditions.append("onset_hour >= ?")
            params.append(onset_hour_min)
        if onset_hour_max is not None:
            conditions.append("onset_hour <= ?")
            params.append(onset_hour_max)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY onset_hour ASC"

        return pd.read_sql_query(query, self._conn, params=params)

    def get_true_causes(self) -> pd.DataFrame:
        """Retrieve only true cause events."""
        return pd.read_sql_query("SELECT * FROM events WHERE event_type = 'true_cause' ORDER BY onset_hour ASC", self._conn)

    def close(self):
        self._conn.close()
