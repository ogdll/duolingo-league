import pytest
from datetime import date
from sqlalchemy import select
from app.models import User, StatsSnapshot

@pytest.mark.asyncio
async def test_create_user(db):
    user = User(duolingo_username="testuser", real_name="Test User")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    assert user.id is not None
    assert user.is_active is True

@pytest.mark.asyncio
async def test_create_snapshot(db):
    user = User(duolingo_username="snapuser", real_name="Snap User")
    db.add(user)
    await db.commit()

    snap = StatsSnapshot(
        user_id=user.id,
        date=date.today(),
        xp_total=1000,
        xp_gained_today=None,
        streak=5,
        league="Gold",
        languages=["es", "fr"],
    )
    db.add(snap)
    await db.commit()
    await db.refresh(snap)
    assert snap.id is not None
    assert snap.xp_gained_today is None

@pytest.mark.asyncio
async def test_snapshot_unique_per_user_per_day(db):
    user = User(duolingo_username="dupeuser", real_name="Dupe User")
    db.add(user)
    await db.commit()

    snap1 = StatsSnapshot(user_id=user.id, date=date.today(), xp_total=100, streak=1, languages=[])
    snap2 = StatsSnapshot(user_id=user.id, date=date.today(), xp_total=200, streak=2, languages=[])
    db.add(snap1)
    await db.commit()
    db.add(snap2)
    with pytest.raises(Exception):  # IntegrityError
        await db.commit()
