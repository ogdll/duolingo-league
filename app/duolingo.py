from __future__ import annotations

import httpx
from bs4 import BeautifulSoup

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
    except Exception:
        return None
