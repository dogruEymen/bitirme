from backend.app.main import app


def test_single_analytics_route_registered():
    analytics_routes = [route for route in app.routes if getattr(route, "path", None) == "/analytics"]

    assert len(analytics_routes) == 1


def test_analytics_contract_keys():
    expected_keys = {
        "schemaVersion",
        "generatedAt",
        "filters",
        "metrics",
        "barData",
        "pieData",
        "scatterData",
        "monthlyData",
        "clusters",
        "papers",
        "sourceDistribution",
        "categoryDistribution",
        "clusterTrendData",
        "clusterTrendSeries",
        "risingTopics",
        "clusterQuality",
    }
    payload = {
        "schemaVersion": "analytics:v2",
        "generatedAt": "2026-06-09T10:00:00",
        "filters": {"source": None, "category": None, "period": "12m"},
        "metrics": {},
        "barData": [],
        "pieData": [],
        "scatterData": [],
        "monthlyData": [],
        "clusters": [],
        "papers": [],
        "sourceDistribution": [],
        "categoryDistribution": [],
        "clusterTrendData": [],
        "clusterTrendSeries": [],
        "risingTopics": [],
        "clusterQuality": {},
    }

    assert expected_keys.issubset(payload.keys())
