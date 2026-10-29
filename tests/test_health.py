import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app

@pytest.mark.asyncio
async def test_health_check():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "property-video-generator"

@pytest.mark.asyncio
async def test_serve_index():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/")
        assert response.status_code == 200
        assert "AI Property Video Generator" in response.text


@pytest.mark.asyncio
async def test_get_sample_data():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/sample-data")
        assert response.status_code == 200
        data = response.json()
        assert "property_name" in data
        assert "images" in data
        assert len(data["images"]) >= 4
