"""Tests for the health check HTTP server."""

import aiohttp
import aiohttp.web
import pytest

from polymarket_bot.health import create_health_app


@pytest.fixture
async def health_app():
    app = create_health_app()
    runner = aiohttp.web.AppRunner(app)
    await runner.setup()
    site = aiohttp.web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    # Get the dynamically assigned port
    port = site._server.sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}"
    await runner.cleanup()


async def test_health_returns_200(health_app):
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{health_app}/health") as resp:
            assert resp.status == 200
            body = await resp.json()
            assert body["status"] == "ok"


async def test_health_unknown_route_returns_404(health_app):
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{health_app}/nonexistent") as resp:
            assert resp.status == 404
