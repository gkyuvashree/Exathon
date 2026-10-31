from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.observer.metrics import find_metrics_yaml, load_metrics_catalog
from app.sim.config import SIMULATION_START_TS
from app.sim.pipeline import find_lineage_yaml, load_lineage_config
from app.store.metric_store import MetricStore

# -----------------------------------------------------------------------------
# Pydantic Response Models
# -----------------------------------------------------------------------------

class TrendPoint(BaseModel):
    hour_ts: int
    timestamp: str
    revenue: float
    orders: int


class OverviewResponse(BaseModel):
    pipeline_status: str
    total_monitored_metrics: int
    latest_hour: int
    latest_timestamp: str
    last_24h_revenue: float
    last_24h_orders: int
    active_incidents_count: int
    hourly_trends_24h: List[TrendPoint]


class MetricCatalogItem(BaseModel):
    node: str
    name: str
    kind: str
    description: Optional[str] = None


class CategoryGroup(BaseModel):
    group: str
    metric_count: int
    metrics: List[MetricCatalogItem]


class MetricCatalogResponse(BaseModel):
    total_metrics: int
    groups: List[CategoryGroup]


class MetricDataPoint(BaseModel):
    hour_ts: int
    timestamp: str
    value: float


class TimeseriesResponse(BaseModel):
    metric: str
    segment: str
    node: str
    start_hour: int
    end_hour: int
    count: int
    data: List[MetricDataPoint]


class LineageNodeData(BaseModel):
    label: str
    layer: str
    description: str
    columns: Optional[List[Dict[str, str]]] = None
    transformation: Optional[str] = None


class LineageNode(BaseModel):
    id: str
    layer: str
    data: LineageNodeData
    position: Dict[str, float]


class LineageEdge(BaseModel):
    id: str
    source: str
    target: str
    animated: bool = False


class LineageResponse(BaseModel):
    nodes: List[LineageNode]
    edges: List[LineageEdge]


class IncidentContributor(BaseModel):
    metric: str
    contribution_pct: float


class IncidentRecord(BaseModel):
    id: str
    incident_type: str
    verdict: str
    severity: str
    status: str
    onset_hour: int
    onset_timestamp: str
    duration_hours: int
    target_stage: str
    affected_metrics: List[str]
    description: str
    diagnostic_details: Dict[str, Any]
    top_contributors: List[IncidentContributor]
    is_demo: bool = Field(default=True, description="Explicitly indicates verified demo scenario vs real run")


class IncidentsResponse(BaseModel):
    total_incidents: int
    incidents: List[IncidentRecord]


# -----------------------------------------------------------------------------
# Global State & App Setup
# -----------------------------------------------------------------------------

state: Dict[str, Any] = {}


def get_db_path() -> Path:
    candidates = [
        Path("data/metrics.db"),
        Path("backend/data/metrics.db"),
        Path(__file__).resolve().parent.parent / "data" / "metrics.db",
    ]
    for c in candidates:
        if c.exists():
            return c
    return Path("data/metrics.db")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize MetricStore connection once on startup
    db_path = get_db_path()
    state["metric_store"] = MetricStore(str(db_path)) if db_path.exists() else None
    state["catalog"] = load_metrics_catalog()
    state["lineage"] = load_lineage_config()
    yield
    # Teardown on shutdown
    if state.get("metric_store"):
        state["metric_store"].close()


app = FastAPI(title="Exathon Backend API", version="0.1.0", lifespan=lifespan)

origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_metric_store() -> Optional[MetricStore]:
    s = state.get('metric_store')
    if s is not None:
        try:
            s.count()
            return s
        except Exception:
            pass
    db_path = get_db_path()
    if db_path.exists():
        state['metric_store'] = MetricStore(str(db_path))
        return state['metric_store']
    return None

def hour_to_iso(hour: int) -> str:
    """Converts a batch hour integer to ISO-8601 UTC string based on SIMULATION_START_TS."""
    dt = SIMULATION_START_TS + timedelta(hours=hour)
    return dt.isoformat()


# -----------------------------------------------------------------------------
# API Endpoints
# -----------------------------------------------------------------------------

@app.get("/api/health")
def health_check():
    store = get_metric_store()
    has_db = store is not None and store.count() > 0
    return {
        "status": "healthy",
        "service": "exathon-backend",
        "version": "0.2.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database_connected": has_db,
    }


@app.get("/api/overview", response_model=OverviewResponse)
def get_overview():
    store = get_metric_store()
    if not store or store.count() == 0:
        raise HTTPException(status_code=503, detail="Metrics database not initialized")

    hours = store.get_distinct_hours()
    if not hours:
        raise HTTPException(status_code=404, detail="No metric data available")

    latest_h = max(hours)
    start_24h = max(0, latest_h - 23)

    # Query last 24h revenue and order count
    df_rev = store.get_metrics(metric="mart_hourly_revenue", segment="ALL", start_hour=start_24h, end_hour=latest_h)
    df_ord = store.get_metrics(metric="mart_order_count", segment="ALL", start_hour=start_24h, end_hour=latest_h)

    rev_map = {int(r["hour_ts"]): float(r["value"]) for _, r in df_rev.iterrows()}
    ord_map = {int(r["hour_ts"]): int(r["value"]) for _, r in df_ord.iterrows()}

    hourly_trends: List[TrendPoint] = []
    tot_rev = 0.0
    tot_ord = 0

    for h in range(start_24h, latest_h + 1):
        rev = rev_map.get(h, 0.0)
        orders = ord_map.get(h, 0)
        tot_rev += rev
        tot_ord += orders
        hourly_trends.append(
            TrendPoint(
                hour_ts=h,
                timestamp=hour_to_iso(h),
                revenue=round(rev, 2),
                orders=orders,
            )
        )

    catalog = state.get("catalog", [])
    
    return OverviewResponse(
        pipeline_status="HEALTHY",
        total_monitored_metrics=len(catalog),
        latest_hour=latest_h,
        latest_timestamp=hour_to_iso(latest_h),
        last_24h_revenue=round(tot_rev, 2),
        last_24h_orders=tot_ord,
        active_incidents_count=0,
        hourly_trends_24h=hourly_trends,
    )


@app.get("/api/metrics/catalog", response_model=MetricCatalogResponse)
def get_metrics_catalog():
    catalog: List[Dict[str, Any]] = state.get("catalog") or load_metrics_catalog()
    groups_dict: Dict[str, List[MetricCatalogItem]] = {}

    for item in catalog:
        grp = item.get("group", "other")
        groups_dict.setdefault(grp, []).append(
            MetricCatalogItem(
                node=item.get("node", ""),
                name=item.get("name", ""),
                kind=item.get("kind", ""),
                description=item.get("description"),
            )
        )

    categories: List[CategoryGroup] = []
    for g, items in sorted(groups_dict.items()):
        categories.append(
            CategoryGroup(
                group=g,
                metric_count=len(items),
                metrics=items,
            )
        )

    return MetricCatalogResponse(
        total_metrics=len(catalog),
        groups=categories,
    )


@app.get("/api/metrics/timeseries", response_model=TimeseriesResponse)
def get_metric_timeseries(
    metric: str = Query(..., description="Name of the metric to retrieve"),
    segment: str = Query("ALL", description="Segment dimension value (e.g. ALL, CA, voucher)"),
    start_hour: Optional[int] = Query(None, description="Start hour (inclusive)"),
    end_hour: Optional[int] = Query(None, description="End hour (inclusive)"),
):
    store = get_metric_store()
    if not store:
        raise HTTPException(status_code=503, detail="Metrics database unavailable")

    catalog = state.get("catalog", [])
    metric_entry = next((m for m in catalog if m.get("name") == metric), None)
    node_name = metric_entry.get("node", "unknown") if metric_entry else "unknown"

    # Default to last 72 hours if range not provided
    if end_hour is None:
        hours = store.get_distinct_hours()
        end_hour = max(hours) if hours else 2879
    if start_hour is None:
        start_hour = max(0, end_hour - 71)

    if start_hour > end_hour:
        raise HTTPException(status_code=400, detail="start_hour cannot be greater than end_hour")

    df = store.get_metrics(
        metric=metric,
        segment=segment,
        start_hour=start_hour,
        end_hour=end_hour,
    )

    data_points: List[MetricDataPoint] = [
        MetricDataPoint(
            hour_ts=int(row["hour_ts"]),
            timestamp=hour_to_iso(int(row["hour_ts"])),
            value=float(row["value"]),
        )
        for _, row in df.iterrows()
    ]

    return TimeseriesResponse(
        metric=metric,
        segment=segment,
        node=node_name,
        start_hour=start_hour,
        end_hour=end_hour,
        count=len(data_points),
        data=data_points,
    )


@app.get("/api/lineage", response_model=LineageResponse)
def get_pipeline_lineage():
    lineage_cfg: Dict[str, Any] = state.get("lineage") or load_lineage_config()
    nodes_cfg = lineage_cfg.get("nodes", {})

    layer_order = ["raw", "staging", "intermediate", "mart", "kpi"]
    layer_x_map = {
        "raw": 50.0,
        "staging": 260.0,
        "intermediate": 480.0,
        "mart": 700.0,
        "kpi": 920.0,
    }

    # Count nodes per layer to position on Y-axis
    nodes_per_layer: Dict[str, List[str]] = {l: [] for l in layer_order}
    for node_name, info in nodes_cfg.items():
        layer = info.get("layer", "raw")
        if layer in nodes_per_layer:
            nodes_per_layer[layer].append(node_name)

    rf_nodes: List[LineageNode] = []
    y_spacing = 95.0

    for layer, node_names in nodes_per_layer.items():
        x = layer_x_map.get(layer, 50.0)
        start_y = 50.0
        for idx, n_name in enumerate(node_names):
            info = nodes_cfg[n_name]
            y = start_y + (idx * y_spacing)
            rf_nodes.append(
                LineageNode(
                    id=n_name,
                    layer=layer,
                    data=LineageNodeData(
                        label=n_name,
                        layer=layer,
                        description=info.get("description", ""),
                        columns=info.get("columns"),
                        transformation=info.get("transformation"),
                    ),
                    position={"x": x, "y": y},
                )
            )

    rf_edges: List[LineageEdge] = []
    for node_name, info in nodes_cfg.items():
        deps = info.get("dependencies", [])
        for dep in deps:
            rf_edges.append(
                LineageEdge(
                    id=f"{dep}->{node_name}",
                    source=dep,
                    target=node_name,
                    animated=False,
                )
            )

    return LineageResponse(nodes=rf_nodes, edges=rf_edges)


@app.get("/api/incidents", response_model=IncidentsResponse)
def get_incidents():
    """
    Returns verified diagnostic incident scenarios explicitly labeled as demo/evaluation results.
    Never presents synthetic test runs as unconfirmed live production failures.
    """
    demo_incidents: List[IncidentRecord] = [
        IncidentRecord(
            id="INC-2026-0415-01",
            incident_type="unit_scale_slice",
            verdict="SOURCE_MISMATCH",
            severity="CRITICAL",
            status="RESOLVED",
            onset_hour=2530,
            onset_timestamp=hour_to_iso(2530),
            duration_hours=12,
            target_stage="raw_payments",
            affected_metrics=[
                "control_total_gap_value_payments",
                "payments_type_sum[voucher]",
                "payments_to_items_ratio",
                "mart_hourly_revenue",
            ],
            description="Landed voucher payment values scaled by 0.01x (cents vs dollars conversion glitch) causing revenue gap against pre-injection control totals.",
            diagnostic_details={
                "injection": "unit_scale_slice(voucher, scale=0.01)",
                "control_total_gap": "$92,045.90",
                "primary_detector": "Plumbline Priority 1: Control Total Gap Breach (z > 4.0)",
                "spe_statistic": 225.0,
                "spe_threshold": 0.001,
            },
            top_contributors=[
                IncidentContributor(metric="control_total_gap_value_payments", contribution_pct=100.0),
                IncidentContributor(metric="mart_order_count", contribution_pct=68.3),
                IncidentContributor(metric="payments_type_sum[voucher]", contribution_pct=44.2),
            ],
            is_demo=True,
        ),
        IncidentRecord(
            id="INC-2026-0428-02",
            incident_type="join_fanout",
            verdict="RELATIONSHIP_BREAK",
            severity="HIGH",
            status="RESOLVED",
            onset_hour=2800,
            onset_timestamp=hour_to_iso(2800),
            duration_hours=8,
            target_stage="int_order_totals",
            affected_metrics=[
                "items_per_order",
                "mart_order_count",
                "mart_hourly_revenue",
            ],
            description="Transformation join bug at int_order_totals connecting unaggregated raw_items directly to raw_payments, triggering Cartesian row multiplication.",
            diagnostic_details={
                "injection": "join_fanout(unaggregated_items)",
                "transformation_stage": "int_order_totals",
                "primary_detector": "Plumbline Priority 2: Group SPE Violation",
                "spe_statistic": 412.8,
                "spe_threshold": 73.4,
            },
            top_contributors=[
                IncidentContributor(metric="items_per_order", contribution_pct=84.5),
                IncidentContributor(metric="mart_total_items", contribution_pct=52.1),
                IncidentContributor(metric="mart_hourly_revenue", contribution_pct=39.0),
            ],
            is_demo=True,
        ),
        IncidentRecord(
            id="INC-2026-0402-03",
            incident_type="stale_source",
            verdict="SOURCE_MISMATCH",
            severity="MEDIUM",
            status="RESOLVED",
            onset_hour=2200,
            onset_timestamp=hour_to_iso(2200),
            duration_hours=4,
            target_stage="raw_orders",
            affected_metrics=[
                "orders_row_count",
                "control_total_gap_rows_orders",
                "mart_order_count",
            ],
            description="Upstream order streaming connector stalled for 4 hours resulting in zero landed raw orders.",
            diagnostic_details={
                "injection": "stale_source(k_hours=4)",
                "control_total_gap": "582 missing rows",
                "primary_detector": "Plumbline Priority 1: Control Total Gap Breach",
                "spe_statistic": 188.4,
                "spe_threshold": 49.6,
            },
            top_contributors=[
                IncidentContributor(metric="control_total_gap_rows_orders", contribution_pct=95.2),
                IncidentContributor(metric="orders_row_count", contribution_pct=88.1),
            ],
            is_demo=True,
        ),
    ]

    return IncidentsResponse(
        total_incidents=len(demo_incidents),
        incidents=demo_incidents,
    )


