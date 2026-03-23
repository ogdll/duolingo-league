from __future__ import annotations

from datetime import date, timedelta
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import User, StatsSnapshot

async def get_leaderboard(db: AsyncSession, period: str) -> list[dict]:
    """
    period: "day" | "week" | "month" | "alltime"
    Returns list of dicts sorted by XP descending.
    """
    today = date.today()

    if period == "day":
        return await _day_leaderboard(db, today)
    elif period == "week":
        start = today - timedelta(days=today.weekday())
        return await _period_leaderboard(db, start, today)
    elif period == "month":
        start = today.replace(day=1)
        return await _period_leaderboard(db, start, today)
    elif period == "alltime":
        return await _alltime_leaderboard(db, today)
    else:
        raise ValueError(f"Unknown period: {period}")

async def _day_leaderboard(db: AsyncSession, today: date) -> list[dict]:
    stmt = (
        select(
            User.duolingo_username,
            User.real_name,
            StatsSnapshot.xp_gained_today,
            StatsSnapshot.streak,
            StatsSnapshot.league,
            StatsSnapshot.languages,
        )
        .join(StatsSnapshot, StatsSnapshot.user_id == User.id)
        .where(User.is_active == True, StatsSnapshot.date == today)
        .order_by(func.coalesce(StatsSnapshot.xp_gained_today, 0).desc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        {
            "duolingo_username": r.duolingo_username,
            "real_name": r.real_name,
            "xp": r.xp_gained_today or 0,
            "streak": r.streak,
            "league": r.league,
            "languages": r.languages,
        }
        for r in rows
    ]

async def _alltime_leaderboard(db: AsyncSession, today: date) -> list[dict]:
    # Latest snapshot per user
    latest = (
        select(
            StatsSnapshot.user_id,
            func.max(StatsSnapshot.date).label("max_date"),
        )
        .group_by(StatsSnapshot.user_id)
        .subquery()
    )
    stmt = (
        select(
            User.duolingo_username,
            User.real_name,
            StatsSnapshot.xp_total,
            StatsSnapshot.streak,
            StatsSnapshot.league,
            StatsSnapshot.languages,
        )
        .join(latest, latest.c.user_id == User.id)
        .join(StatsSnapshot, (StatsSnapshot.user_id == User.id) & (StatsSnapshot.date == latest.c.max_date))
        .where(User.is_active == True)
        .order_by(StatsSnapshot.xp_total.desc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        {
            "duolingo_username": r.duolingo_username,
            "real_name": r.real_name,
            "xp": r.xp_total,
            "streak": r.streak,
            "league": r.league,
            "languages": r.languages,
        }
        for r in rows
    ]

async def _period_leaderboard(db: AsyncSession, start: date, end: date) -> list[dict]:
    # Earliest snapshot in period (or registration snap) per user
    first_in_period = (
        select(
            StatsSnapshot.user_id,
            func.min(StatsSnapshot.date).label("first_date"),
        )
        .where(StatsSnapshot.date >= start)
        .group_by(StatsSnapshot.user_id)
        .subquery()
    )
    latest_in_period = (
        select(
            StatsSnapshot.user_id,
            func.max(StatsSnapshot.date).label("last_date"),
        )
        .where(StatsSnapshot.date <= end)
        .group_by(StatsSnapshot.user_id)
        .subquery()
    )
    first_snap = select(StatsSnapshot).join(
        first_in_period,
        (StatsSnapshot.user_id == first_in_period.c.user_id) &
        (StatsSnapshot.date == first_in_period.c.first_date)
    ).subquery()
    last_snap = select(StatsSnapshot).join(
        latest_in_period,
        (StatsSnapshot.user_id == latest_in_period.c.user_id) &
        (StatsSnapshot.date == latest_in_period.c.last_date)
    ).subquery()

    stmt = (
        select(
            User.duolingo_username,
            User.real_name,
            (last_snap.c.xp_total - first_snap.c.xp_total).label("xp_gained"),
            last_snap.c.streak,
            last_snap.c.league,
            last_snap.c.languages,
        )
        .join(last_snap, last_snap.c.user_id == User.id)
        .join(first_snap, first_snap.c.user_id == User.id)
        .where(User.is_active == True)
        .order_by((last_snap.c.xp_total - first_snap.c.xp_total).desc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        {
            "duolingo_username": r.duolingo_username,
            "real_name": r.real_name,
            "xp": max(0, r.xp_gained),
            "streak": r.streak,
            "league": r.league,
            "languages": r.languages,
        }
        for r in rows
    ]
