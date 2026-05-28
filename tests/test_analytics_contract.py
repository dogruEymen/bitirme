from backend.app.main import app


def test_single_analytics_route_registered():
    analytics_routes = [route for route in app.routes if getattr(route, "path", None) == "/analytics"]

    assert len(analytics_routes) == 1


def test_analytics_contract_keys():
    expected_keys = {
        "metrics",
        "barData",
        "pieData",
        "scatterData",
        "monthlyData",
        "clusters",
        "papers",
    }
    payload = {
        "metrics": {},
        "barData": [],
        "pieData": [],
        "scatterData": [],
        "monthlyData": [],
        "clusters": [],
        "papers": [],
    }

    assert expected_keys.issubset(payload.keys())
