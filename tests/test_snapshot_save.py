from __future__ import annotations

import pytest
from datetime import date
from app.models import User, StatsSnapshot
from app.duolingo import save_snapshot
from sqlalchemy import select

@pytest.mark.asyncio
async def test_save_snapshot_creates_row(db):
    user = User(duolingo_username="snap_save_user", real_name="Snap Save")
    db.add(user)
    await db.commit()

    await save_snapshot(db, user, xp_total=1000, prev_xp_total=800, streak=5, league="Silver", languages=["es"])

    stmt = select(StatsSnapshot).where(StatsSnapshot.user_id == user.id)
    result = await db.execute(stmt)
    snap = result.scalar_one()
    assert snap.xp_total == 1000
    assert snap.xp_gained_today == 200
    assert snap.streak == 5

@pytest.mark.asyncio
async def test_save_snapshot_clamps_negative_xp(db):
    user = User(duolingo_username="snap_clamp_user", real_name="Clamp User")
    db.add(user)
    await db.commit()

    await save_snapshot(db, user, xp_total=900, prev_xp_total=1000, streak=3, league="Bronze", languages=[])

    stmt = select(StatsSnapshot).where(StatsSnapshot.user_id == user.id)
    result = await db.execute(stmt)
    snap = result.scalar_one()
    assert snap.xp_gained_today == 0  # clamped

@pytest.mark.asyncio
async def test_save_snapshot_null_when_no_prev(db):
    user = User(duolingo_username="snap_null_user", real_name="Null User")
    db.add(user)
    await db.commit()

    await save_snapshot(db, user, xp_total=500, prev_xp_total=None, streak=1, league=None, languages=["fr"])

    stmt = select(StatsSnapshot).where(StatsSnapshot.user_id == user.id)
    result = await db.execute(stmt)
    snap = result.scalar_one()
    assert snap.xp_gained_today is None

@pytest.mark.asyncio
async def test_save_snapshot_upserts_on_same_day(db):
    user = User(duolingo_username="snap_upsert_user", real_name="Upsert User")
    db.add(user)
    await db.commit()

    # First save
    await save_snapshot(db, user, xp_total=500, prev_xp_total=None, streak=1, league="Bronze", languages=["es"])
    # Second save same day (simulates admin/refresh)
    await save_snapshot(db, user, xp_total=600, prev_xp_total=500, streak=2, league="Silver", languages=["es", "fr"])

    stmt = select(StatsSnapshot).where(StatsSnapshot.user_id == user.id)
    result = await db.execute(stmt)
    snaps = result.scalars().all()
    assert len(snaps) == 1  # only one row, not two
    assert snaps[0].xp_total == 600
    assert snaps[0].xp_gained_today == 100
