from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch
from app.models import User

@pytest.mark.asyncio
async def test_homepage_returns_200(client):
    resp = await client.get("/")
    assert resp.status_code == 200

@pytest.mark.asyncio
async def test_join_page_returns_200(client):
    resp = await client.get("/join")
    assert resp.status_code == 200

@pytest.mark.asyncio
async def test_join_registers_user(client, db):
    with patch("app.main.fetch_user_stats", new_callable=AsyncMock) as mock_fetch, \
         patch("app.main.save_snapshot", new_callable=AsyncMock):
        mock_fetch.return_value = {
            "xp_total": 1000, "streak": 5,
            "league": "Gold", "languages": ["es"]
        }
        resp = await client.post("/join", data={
            "duolingo_username": "newuser123",
            "real_name": "New User"
        })
    assert resp.status_code in (200, 303)

@pytest.mark.asyncio
async def test_join_duplicate_shows_error(client, db):
    user = User(duolingo_username="existing_user", real_name="Existing")
    db.add(user)
    await db.commit()

    with patch("app.main.fetch_user_stats", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = {"xp_total": 500, "streak": 2, "league": None, "languages": []}
        resp = await client.post("/join", data={
            "duolingo_username": "existing_user",
            "real_name": "Someone Else"
        })
    assert resp.status_code == 200
    assert b"already in the league" in resp.content

@pytest.mark.asyncio
async def test_leave_removes_user(client, db):
    user = User(duolingo_username="leaving_user", real_name="Leaving User")
    db.add(user)
    await db.commit()

    resp = await client.post("/leave", data={
        "duolingo_username": "leaving_user",
        "real_name": "Leaving User"
    })
    assert resp.status_code in (200, 303)
    await db.refresh(user)
    assert user.is_active is False

@pytest.mark.asyncio
async def test_admin_refresh_requires_token(client):
    resp = await client.post("/admin/refresh")
    assert resp.status_code == 403

@pytest.mark.asyncio
async def test_admin_refresh_with_valid_token(client):
    with patch("app.main.ADMIN_TOKEN", "test-token"), \
         patch("app.main._run_daily_update", new_callable=AsyncMock):
        resp = await client.post("/admin/refresh", params={"token": "test-token"})
    assert resp.status_code == 200
