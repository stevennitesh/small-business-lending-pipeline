"""Guard the embedded Prefect routing contract without starting a service."""

from fastapi.testclient import TestClient
from prefect.server.api.server import create_app


def test_prefect_embedded_health_route_is_compatible():
    """New FastAPI router versions must not silently break the pinned Prefect API."""
    client = TestClient(create_app(ephemeral=True))
    response = client.get("/api/health")
    assert response.status_code == 200
