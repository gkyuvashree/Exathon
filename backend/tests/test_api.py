"""
Comprehensive Tests for Task 1: Backend API Exposure Endpoints.
Verifies all 5 REST endpoints:
  1. GET /api/overview
  2. GET /api/metrics/catalog
  3. GET /api/metrics/timeseries
  4. GET /api/lineage
  5. GET /api/incidents
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health_endpoint(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert "service" in data


def test_overview_endpoint(client):
    res = client.get("/api/overview")
    assert res.status_code == 200
    data = res.json()
    assert data["pipeline_status"] == "HEALTHY"
    assert data["total_monitored_metrics"] == 46
    assert data["latest_hour"] == 2879
    assert "latest_timestamp" in data
    assert data["last_24h_revenue"] > 0
    assert len(data["hourly_trends_24h"]) == 24
    # Validate trend schema
    first = data["hourly_trends_24h"][0]
    assert "hour_ts" in first
    assert "timestamp" in first
    assert "revenue" in first
    assert "orders" in first


def test_metrics_catalog_endpoint(client):
    res = client.get("/api/metrics/catalog")
    assert res.status_code == 200
    data = res.json()
    assert data["total_metrics"] == 46
    assert len(data["groups"]) == 5
    group_names = {g["group"] for g in data["groups"]}
    assert group_names == {"orders", "items", "payments", "totals", "mart"}
    for g in data["groups"]:
        assert len(g["metrics"]) > 0
        assert "name" in g["metrics"][0]
        assert "node" in g["metrics"][0]


def test_metrics_timeseries_valid(client):
    res = client.get("/api/metrics/timeseries?metric=mart_hourly_revenue&segment=ALL&start_hour=2800&end_hour=2850")
    assert res.status_code == 200
    data = res.json()
    assert data["metric"] == "mart_hourly_revenue"
    assert data["segment"] == "ALL"
    assert data["node"] == "mart_revenue_hourly"
    assert data["count"] == 51
    assert len(data["data"]) == 51
    assert data["data"][0]["hour_ts"] == 2800


def test_metrics_timeseries_defaults(client):
    res = client.get("/api/metrics/timeseries?metric=orders_row_count")
    assert res.status_code == 200
    data = res.json()
    assert data["metric"] == "orders_row_count"
    assert data["count"] > 0
    assert data["end_hour"] == 2879


def test_metrics_timeseries_invalid_range(client):
    res = client.get("/api/metrics/timeseries?metric=orders_row_count&start_hour=2850&end_hour=2800")
    assert res.status_code == 400
    assert "start_hour cannot be greater than end_hour" in res.json()["detail"]


def test_lineage_endpoint(client):
    res = client.get("/api/lineage")
    assert res.status_code == 200
    data = res.json()
    assert len(data["nodes"]) >= 9
    assert len(data["edges"]) >= 8
    node_ids = {n["id"] for n in data["nodes"]}
    assert "raw_orders" in node_ids
    assert "mart_revenue_hourly" in node_ids
    # Check React Flow node format
    first_node = data["nodes"][0]
    assert "position" in first_node
    assert "data" in first_node
    assert "x" in first_node["position"]
    assert "y" in first_node["position"]


def test_incidents_endpoint(client):
    res = client.get("/api/incidents")
    assert res.status_code == 200
    data = res.json()
    assert data["total_incidents"] >= 3
    first_inc = data["incidents"][0]
    assert first_inc["is_demo"] is True
    assert "verdict" in first_inc
    assert "diagnostic_details" in first_inc
    assert len(first_inc["top_contributors"]) > 0
