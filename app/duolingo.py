from __future__ import annotations

import httpx
import logging
from bs4 import BeautifulSoup
from datetime import date as date_type
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select as sa_select
from app.models import StatsSnapshot, User

logger = logging.getLogger(__name__)

API_URL = "https://www.duolingo.com/2017-06-30/users"
PROFILE_URL = "https://www.duolingo.com/profile/{username}"

class DuolingoUserNotFound(Exception):
    pass

class DuolingoUnavailable(Exception):
    pass

async def fetch_user_stats(username: str) -> dict:
    """
    Returns: {xp_total, streak, languages, league}
    Raises: DuolingoUserNotFound, DuolingoUnavailable
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                API_URL,
                params={"fields": "username,name,streak,courses,currentCourse", "username": username},
                headers={"User-Agent": "Mozilla/5.0"},
            )
            resp.raise_for_status()
            data = resp.json()

            users = data.get("users", [])
            if not users:
                raise DuolingoUserNotFound(f"Username '{username}' not found on Duolingo")

            user = users[0]
            courses = user.get("courses", [])
            xp_total = sum(sum(c.get("xpSums", [])) for c in courses)
            languages = [c["learningLanguage"] for c in courses if "learningLanguage" in c]
            streak = user.get("streak", 0)

            # Attempt to scrape league — must be inside the async with block
            league = await _scrape_league(client, username)

    except httpx.HTTPError as e:
        raise DuolingoUnavailable(f"Could not reach Duolingo: {e}") from e

    return {
        "xp_total": xp_total,
        "streak": streak,
        "languages": languages,
        "league": league,
    }

# NOTE: _scrape_league MUST be called inside the same `async with httpx.AsyncClient` block
# as the API call — do not refactor it to open a new client unless you update the call site.

async def _scrape_league(client: httpx.AsyncClient, username: str) -> str | None:
    try:
        resp = await client.get(
            PROFILE_URL.format(username=username),
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        tag = soup.find(attrs={"data-test": "league-tile"})
        if tag:
            return tag.get_text(strip=True).replace(" League", "").replace(" league", "")
        return None
    except Exception as e:
        logger.debug("League scraping failed for %s: %s", username, e)
        return None


async def save_snapshot(
    db: AsyncSession,
    user: User,
    xp_total: int,
    prev_xp_total: int | None,
    streak: int,
    league: str | None,
    languages: list[str],
) -> None:
    """Insert or update today's snapshot for the user. XP gained is clamped to 0 if negative.

    Note: commits the session internally. Do not call within a larger transaction.
    """
    if prev_xp_total is None:
        xp_gained_today = None
    else:
        xp_gained_today = max(0, xp_total - prev_xp_total)

    today = date_type.today()

    # Check if a snapshot already exists for today (upsert pattern for SQLite + PostgreSQL)
    stmt = sa_select(StatsSnapshot).where(
        StatsSnapshot.user_id == user.id,
        StatsSnapshot.date == today,
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()

    if existing:
        from datetime import datetime, timezone
        existing.xp_total = xp_total
        existing.xp_gained_today = xp_gained_today
        existing.streak = streak
        existing.league = league
        existing.languages = languages
        existing.captured_at = datetime.now(timezone.utc)
    else:
        snapshot = StatsSnapshot(
            user_id=user.id,
            date=today,
            xp_total=xp_total,
            xp_gained_today=xp_gained_today,
            streak=streak,
            league=league,
            languages=languages,
        )
        db.add(snapshot)

    await db.commit()
