from __future__ import annotations

import pytest
from datetime import date, timedelta
from unittest.mock import patch
from app.models import User, StatsSnapshot
from app.leaderboard import get_leaderboard

async def _make_user(db, username, real_name):
    u = User(duolingo_username=username, real_name=real_name)
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u

async def _make_snap(db, user_id, snap_date, xp_total, xp_today=None, streak=1):
    s = StatsSnapshot(
        user_id=user_id,
        date=snap_date,
        xp_total=xp_total,
        xp_gained_today=xp_today,
        streak=streak,
        league="Gold",
        languages=["es"],
    )
    db.add(s)
    await db.commit()
    return s

@pytest.mark.asyncio
async def test_day_leaderboard(db):
    today = date.today()
    u1 = await _make_user(db, "lb_day_u1", "User One")
    u2 = await _make_user(db, "lb_day_u2", "User Two")
    await _make_snap(db, u1.id, today, xp_total=1000, xp_today=50)
    await _make_snap(db, u2.id, today, xp_total=2000, xp_today=200)

    rows = await get_leaderboard(db, period="day")
    usernames = [r["duolingo_username"] for r in rows]
    assert usernames[0] == "lb_day_u2"  # higher xp_gained_today ranks first

@pytest.mark.asyncio
async def test_alltime_leaderboard(db):
    today = date.today()
    u1 = await _make_user(db, "lb_all_u1", "All One")
    u2 = await _make_user(db, "lb_all_u2", "All Two")
    await _make_snap(db, u1.id, today, xp_total=5000, xp_today=10)
    await _make_snap(db, u2.id, today, xp_total=3000, xp_today=300)

    rows = await get_leaderboard(db, period="alltime")
    assert rows[0]["duolingo_username"] == "lb_all_u1"  # highest xp_total

@pytest.mark.asyncio
async def test_week_leaderboard(db):
    # Use a fixed Wednesday so week_start (Monday) is always 2 days before
    # "today", avoiding the Monday edge case where week_start == today and we
    # cannot insert two distinct dates for the same user within the week.
    fixed_today = date.today()
    # Find the Wednesday of the current week (or use last Wednesday if today is Mon/Tue)
    days_to_wednesday = (2 - fixed_today.weekday()) % 7
    if days_to_wednesday == 0 and fixed_today.weekday() != 2:
        days_to_wednesday = 7
    fake_today = fixed_today + timedelta(days=days_to_wednesday) if days_to_wednesday > 0 else fixed_today

    # If today is already Wed or later, compute this week's Monday
    # otherwise use next Wednesday with its Monday
    week_start = fake_today - timedelta(days=fake_today.weekday())  # always a Monday

    u = await _make_user(db, "lb_week_u1", "Week One")
    await _make_snap(db, u.id, week_start, xp_total=1000)

    with patch("app.leaderboard.date") as mock_date:
        mock_date.today.return_value = fake_today
        mock_date.side_effect = lambda *args, **kw: date(*args, **kw)
        # Insert the "today" snap using the real DB but fake_today date
        await _make_snap(db, u.id, fake_today, xp_total=1500)
        rows = await get_leaderboard(db, period="week")

    week_rows = [r for r in rows if r["duolingo_username"] == "lb_week_u1"]
    assert week_rows[0]["xp"] == 500  # 1500 - 1000

@pytest.mark.asyncio
async def test_null_xp_today_treated_as_zero(db):
    today = date.today()
    u1 = await _make_user(db, "lb_null_u1", "Null One")
    u2 = await _make_user(db, "lb_null_u2", "Null Two")
    await _make_snap(db, u1.id, today, xp_total=100, xp_today=None)
    await _make_snap(db, u2.id, today, xp_total=200, xp_today=50)

    rows = await get_leaderboard(db, period="day")
    # Filter to only the users created in this test to avoid interference from
    # other tests sharing the same session-scoped in-memory SQLite DB.
    rows = [r for r in rows if r["duolingo_username"].startswith("lb_null_")]
    assert rows[0]["duolingo_username"] == "lb_null_u2"
