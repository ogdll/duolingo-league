# Duolingo Corporate Leagues Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a self-service Duolingo league tracker that fetches stats daily and shows leaderboards by day, week, month, and all-time.

**Architecture:** FastAPI app with Jinja2 server-side rendering, APScheduler running daily stat fetches in-process, PostgreSQL storing per-user daily snapshots. Leaderboard views are derived from snapshot diffs at query time.

**Tech Stack:** Python 3.11+, FastAPI, Jinja2, SQLAlchemy 2.x (async), asyncpg, APScheduler 3.x, httpx, BeautifulSoup4, pytest, pytest-asyncio, alembic

---

## File Map

| File | Responsibility |
|---|---|
| `app/database.py` | Async engine, session factory, `get_db` dependency |
| `app/models.py` | SQLAlchemy ORM models: `User`, `StatsSnapshot` |
| `app/duolingo.py` | Fetch stats from Duolingo API; scrape league as fallback |
| `app/leaderboard.py` | Query logic for day/week/month/all-time rankings |
| `app/main.py` | FastAPI app, all routes, APScheduler wiring |
| `templates/base.html` | Shared HTML layout |
| `templates/index.html` | Leaderboard with JS tab switching |
| `templates/join.html` | Registration form + error display |
| `templates/leave.html` | Leave form + confirmation |
| `static/style.css` | Minimal desktop-first CSS |
| `alembic/` | DB migrations |
| `tests/test_duolingo.py` | Unit tests for Duolingo fetcher (mocked httpx) |
| `tests/test_leaderboard.py` | Integration tests for leaderboard queries |
| `tests/test_routes.py` | FastAPI TestClient route tests |
| `requirements.txt` | All dependencies pinned |
| `.env.example` | Template for required env vars |

---

## Task 1: Project scaffold and dependencies

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `app/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create requirements.txt**

```
fastapi==0.111.0
uvicorn[standard]==0.29.0
sqlalchemy[asyncio]==2.0.30
asyncpg==0.29.0
alembic==1.13.1
httpx==0.27.0
beautifulsoup4==4.12.3
apscheduler==3.10.4
jinja2==3.1.4
python-dotenv==1.0.1
pytest==8.2.0
pytest-asyncio==0.23.6
pytest-mock==3.14.0
```

- [ ] **Step 2: Install dependencies**

```bash
pip install -r requirements.txt
```

Expected: All packages install without errors.

- [ ] **Step 3: Create .env.example**

```
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/duolingo_leagues
SCHEDULER_HOUR=2
ADMIN_TOKEN=change-me
```

- [ ] **Step 4: Create app/__init__.py and tests/__init__.py**

Both empty files.

- [ ] **Step 5: Create tests/conftest.py**

```python
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.models import Base
from app.main import app
from app.database import get_db

TEST_DB_URL = "postgresql+asyncpg://user:password@localhost:5432/duolingo_leagues_test"

@pytest_asyncio.fixture(scope="session")
async def engine():
    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

@pytest_asyncio.fixture
async def db(engine):
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        yield session
        await session.rollback()

@pytest_asyncio.fixture
async def client(db):
    async def override_get_db():
        yield db
    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
```

- [ ] **Step 6: Commit**

```bash
git add requirements.txt .env.example app/__init__.py tests/__init__.py tests/conftest.py
git commit -m "chore: scaffold project, add dependencies and test fixtures"
```

---

## Task 2: Database connection

**Files:**
- Create: `app/database.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_database.py`:

```python
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db

@pytest.mark.asyncio
async def test_get_db_yields_session(db):
    assert isinstance(db, AsyncSession)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_database.py -v
```

Expected: FAIL — `app.database` not found.

- [ ] **Step 3: Implement app/database.py**

```python
import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_database.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/database.py tests/test_database.py
git commit -m "feat: add async database connection"
```

---

## Task 3: SQLAlchemy models

**Files:**
- Create: `app/models.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_models.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_models.py -v
```

Expected: FAIL — `app.models` not found.

- [ ] **Step 3: Implement app/models.py**

```python
from datetime import datetime
from typing import Optional
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    duolingo_username: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    real_name: Mapped[str] = mapped_column(String, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    snapshots: Mapped[list["StatsSnapshot"]] = relationship(back_populates="user")

class StatsSnapshot(Base):
    __tablename__ = "stats_snapshots"
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_user_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    date: Mapped[datetime] = mapped_column(Date, nullable=False)
    xp_total: Mapped[int] = mapped_column(Integer, nullable=False)
    xp_gained_today: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    league: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    languages: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    captured_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="snapshots")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_models.py -v
```

Expected: All 3 PASS.

- [ ] **Step 5: Set up Alembic and generate initial migration**

```bash
alembic init alembic
```

Edit `alembic/env.py` — add:
```python
from app.models import Base
target_metadata = Base.metadata
```

Also set `sqlalchemy.url` in `alembic.ini` or configure it to read from env.

```bash
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
```

Expected: Tables `users` and `stats_snapshots` created in the database.

- [ ] **Step 6: Commit**

```bash
git add app/models.py tests/test_models.py alembic/ alembic.ini
git commit -m "feat: add ORM models and initial migration"
```

---

## Task 4: Duolingo data fetching

**Files:**
- Create: `app/duolingo.py`
- Create: `tests/test_duolingo.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_duolingo.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.duolingo import fetch_user_stats, DuolingoUserNotFound

MOCK_API_RESPONSE = {
    "users": [{
        "username": "testuser",
        "name": "Test User",
        "streak": 42,
        "courses": [
            {"learningLanguage": "es", "xpSums": [100, 200]},
            {"learningLanguage": "fr", "xpSums": [50]},
        ],
        "currentCourse": {"learningLanguage": "es"}
    }]
}

@pytest.mark.asyncio
async def test_fetch_returns_stats():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = MOCK_API_RESPONSE

    with patch("app.duolingo.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        stats = await fetch_user_stats("testuser")

    assert stats["streak"] == 42
    assert stats["xp_total"] == 350  # sum of all xpSums across courses
    assert "es" in stats["languages"]
    assert "fr" in stats["languages"]

@pytest.mark.asyncio
async def test_raises_when_user_not_found():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"users": []}

    with patch("app.duolingo.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        with pytest.raises(DuolingoUserNotFound):
            await fetch_user_stats("nobody")

@pytest.mark.asyncio
async def test_league_scraping_fallback():
    mock_api_response = MagicMock()
    mock_api_response.status_code = 200
    mock_api_response.json.return_value = MOCK_API_RESPONSE

    mock_profile_response = MagicMock()
    mock_profile_response.status_code = 200
    mock_profile_response.text = '<h2 data-test="league-tile">Gold League</h2>'

    with patch("app.duolingo.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(side_effect=[mock_api_response, mock_profile_response])
        mock_client_cls.return_value = mock_client

        stats = await fetch_user_stats("testuser")

    assert stats["league"] == "Gold"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_duolingo.py -v
```

Expected: FAIL — `app.duolingo` not found.

- [ ] **Step 3: Implement app/duolingo.py**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_duolingo.py -v
```

Expected: All 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add app/duolingo.py tests/test_duolingo.py
git commit -m "feat: add Duolingo API fetcher with scraping fallback for league"
```

---

## Task 5: Leaderboard query logic

**Files:**
- Create: `app/leaderboard.py`
- Create: `tests/test_leaderboard.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_leaderboard.py`:

```python
import pytest
from datetime import date, timedelta
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
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    u = await _make_user(db, "lb_week_u1", "Week One")
    await _make_snap(db, u.id, week_start, xp_total=1000)
    await _make_snap(db, u.id, today, xp_total=1500)

    rows = await get_leaderboard(db, period="week")
    assert rows[0]["xp"] == 500  # 1500 - 1000

@pytest.mark.asyncio
async def test_null_xp_today_treated_as_zero(db):
    today = date.today()
    u1 = await _make_user(db, "lb_null_u1", "Null One")
    u2 = await _make_user(db, "lb_null_u2", "Null Two")
    await _make_snap(db, u1.id, today, xp_total=100, xp_today=None)
    await _make_snap(db, u2.id, today, xp_total=200, xp_today=50)

    rows = await get_leaderboard(db, period="day")
    assert rows[0]["duolingo_username"] == "lb_null_u2"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_leaderboard.py -v
```

Expected: FAIL — `app.leaderboard` not found.

- [ ] **Step 3: Implement app/leaderboard.py**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_leaderboard.py -v
```

Expected: All 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add app/leaderboard.py tests/test_leaderboard.py
git commit -m "feat: add leaderboard query logic for day/week/month/all-time"
```

---

## Task 6: Snapshot save helper

**Files:**
- Modify: `app/duolingo.py` (add save helper)
- Create: `tests/test_snapshot_save.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_snapshot_save.py`:

```python
import pytest
from datetime import date
from unittest.mock import AsyncMock, patch, MagicMock
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_snapshot_save.py -v
```

Expected: FAIL — `save_snapshot` not found.

- [ ] **Step 3: Add save_snapshot to app/duolingo.py**

Add to the bottom of `app/duolingo.py`:

```python
from datetime import date as date_type
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.models import StatsSnapshot, User

async def save_snapshot(
    db,
    user: "User",
    xp_total: int,
    prev_xp_total: int | None,
    streak: int,
    league: str | None,
    languages: list[str],
) -> None:
    if prev_xp_total is None:
        xp_gained_today = None
    else:
        xp_gained_today = max(0, xp_total - prev_xp_total)

    stmt = pg_insert(StatsSnapshot).values(
        user_id=user.id,
        date=date_type.today(),
        xp_total=xp_total,
        xp_gained_today=xp_gained_today,
        streak=streak,
        league=league,
        languages=languages,
    ).on_conflict_do_update(
        constraint="uq_user_date",
        set_={
            "xp_total": xp_total,
            "xp_gained_today": xp_gained_today,
            "streak": streak,
            "league": league,
            "languages": languages,
        }
    )
    await db.execute(stmt)
    await db.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_snapshot_save.py -v
```

Expected: All 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add app/duolingo.py tests/test_snapshot_save.py
git commit -m "feat: add save_snapshot with upsert and xp clamping"
```

---

## Task 7: FastAPI routes

**Files:**
- Create: `app/main.py`
- Create: `tests/test_routes.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_routes.py`:

```python
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
    import os
    os.environ["ADMIN_TOKEN"] = "test-token"
    with patch("app.main._run_daily_update", new_callable=AsyncMock):
        resp = await client.post("/admin/refresh", params={"token": "test-token"})
    assert resp.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_routes.py -v
```

Expected: FAIL — `app.main` not found.

- [ ] **Step 3: Implement app/main.py**

```python
import logging
import os
from contextlib import asynccontextmanager
from datetime import date

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.duolingo import DuolingoUnavailable, DuolingoUserNotFound, fetch_user_stats, save_snapshot
from app.leaderboard import get_leaderboard
from app.models import StatsSnapshot, User

load_dotenv()
logger = logging.getLogger(__name__)

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
SCHEDULER_HOUR = int(os.getenv("SCHEDULER_HOUR", "2"))

scheduler = AsyncIOScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.add_job(_run_daily_update, "cron", hour=SCHEDULER_HOUR, timezone="UTC")
    scheduler.start()
    yield
    scheduler.shutdown()

app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


async def _run_daily_update():
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.is_active == True))
        users = result.scalars().all()
        for user in users:
            try:
                # Get previous xp_total
                prev_stmt = (
                    select(StatsSnapshot.xp_total)
                    .where(StatsSnapshot.user_id == user.id)
                    .order_by(StatsSnapshot.date.desc())
                    .limit(1)
                )
                prev_row = (await db.execute(prev_stmt)).scalar_one_or_none()
                stats = await fetch_user_stats(user.duolingo_username)
                await save_snapshot(
                    db, user,
                    xp_total=stats["xp_total"],
                    prev_xp_total=prev_row,
                    streak=stats["streak"],
                    league=stats["league"],
                    languages=stats["languages"],
                )
            except Exception:
                logger.exception("Failed to update stats for %s", user.duolingo_username)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, period: str = "day", db: AsyncSession = Depends(get_db)):
    rows = await get_leaderboard(db, period=period)
    return templates.TemplateResponse("index.html", {
        "request": request, "rows": rows, "period": period
    })


@app.get("/join", response_class=HTMLResponse)
async def join_form(request: Request):
    return templates.TemplateResponse("join.html", {"request": request, "error": None})


@app.post("/join", response_class=HTMLResponse)
async def join_submit(
    request: Request,
    duolingo_username: str = Form(...),
    real_name: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    def error(msg: str):
        return templates.TemplateResponse("join.html", {"request": request, "error": msg})

    try:
        stats = await fetch_user_stats(duolingo_username)
    except DuolingoUserNotFound:
        return error("Username not found — check your Duolingo profile URL")
    except DuolingoUnavailable:
        return error("Couldn't reach Duolingo right now — try again in a few minutes")

    user = User(duolingo_username=duolingo_username, real_name=real_name)
    db.add(user)
    try:
        await db.commit()
        await db.refresh(user)
    except IntegrityError:
        await db.rollback()
        return error("This username is already in the league")

    await save_snapshot(
        db, user,
        xp_total=stats["xp_total"],
        prev_xp_total=None,
        streak=stats["streak"],
        league=stats["league"],
        languages=stats["languages"],
    )
    return RedirectResponse("/", status_code=303)


@app.get("/leave", response_class=HTMLResponse)
async def leave_form(request: Request):
    return templates.TemplateResponse("leave.html", {"request": request, "error": None})


@app.post("/leave", response_class=HTMLResponse)
async def leave_submit(
    request: Request,
    duolingo_username: str = Form(...),
    real_name: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(User).where(
        User.duolingo_username == duolingo_username,
        User.real_name == real_name,
        User.is_active == True,
    )
    user = (await db.execute(stmt)).scalar_one_or_none()
    if not user:
        return templates.TemplateResponse("leave.html", {
            "request": request,
            "error": "No active member found with that username and name"
        })
    user.is_active = False
    await db.commit()
    return RedirectResponse("/", status_code=303)


@app.post("/admin/refresh")
async def admin_refresh(token: str = "", db: AsyncSession = Depends(get_db)):
    if not ADMIN_TOKEN or token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")
    await _run_daily_update()
    return {"status": "ok"}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_routes.py -v
```

Expected: All 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add app/main.py tests/test_routes.py
git commit -m "feat: add FastAPI routes for leaderboard, join, leave, admin refresh"
```

---

## Task 8: Templates

**Files:**
- Create: `templates/base.html`
- Create: `templates/index.html`
- Create: `templates/join.html`
- Create: `templates/leave.html`
- Create: `static/style.css`

No tests for templates — visual output verified by running the server.

- [ ] **Step 1: Create templates/base.html**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Duolingo League</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
  <header>
    <a href="/" class="site-title">🦉 Duolingo League</a>
    <nav>
      <a href="/join">Join</a>
      <a href="/leave">Leave</a>
    </nav>
  </header>
  <main>
    {% block content %}{% endblock %}
  </main>
</body>
</html>
```

- [ ] **Step 2: Create templates/index.html**

Tab switching uses JS fetch to `/api/leaderboard?period=X` — no page reload.
Add a JSON endpoint to `app/main.py` (add after the `/` route):

```python
@app.get("/api/leaderboard")
async def api_leaderboard(period: str = "day", db: AsyncSession = Depends(get_db)):
    rows = await get_leaderboard(db, period=period)
    return rows
```

```html
{% extends "base.html" %}
{% block content %}
<h1>Leaderboard</h1>

<div class="tabs">
  {% for p, label in [("day","Today"), ("week","This Week"), ("month","This Month"), ("alltime","All Time")] %}
  <button class="tab {% if period == p %}active{% endif %}" data-period="{{ p }}">{{ label }}</button>
  {% endfor %}
</div>

<div id="leaderboard-wrap">
  {% include "_leaderboard_table.html" %}
</div>

<script>
  const LEAGUE_FLAGS = {};
  document.querySelectorAll('.tab').forEach(btn => {
    btn.addEventListener('click', async () => {
      document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const period = btn.dataset.period;
      const resp = await fetch(`/api/leaderboard?period=${period}`);
      const rows = await resp.json();
      const wrap = document.getElementById('leaderboard-wrap');
      if (!rows.length) {
        wrap.innerHTML = '<p class="empty">No data yet. <a href="/join">Be the first to join!</a></p>';
        return;
      }
      wrap.innerHTML = `<table>
        <thead><tr><th>#</th><th>Name</th><th>XP</th><th>Streak</th><th>League</th><th>Languages</th></tr></thead>
        <tbody>${rows.map((r, i) => `<tr>
          <td>${i+1}</td>
          <td>${r.real_name}</td>
          <td>${r.xp}</td>
          <td>${r.streak} 🔥</td>
          <td>${r.league || '—'}</td>
          <td>${(r.languages||[]).join(', ')}</td>
        </tr>`).join('')}</tbody>
      </table>`;
    });
  });
</script>
{% endblock %}
```

Create `templates/_leaderboard_table.html` (used for initial server-side render):

```html
{% if rows %}
<table>
  <thead>
    <tr><th>#</th><th>Name</th><th>XP</th><th>Streak</th><th>League</th><th>Languages</th></tr>
  </thead>
  <tbody>
    {% for row in rows %}
    <tr>
      <td>{{ loop.index }}</td>
      <td>{{ row.real_name }}</td>
      <td>{{ row.xp }}</td>
      <td>{{ row.streak }} 🔥</td>
      <td>{{ row.league or "—" }}</td>
      <td>{{ row.languages | join(", ") }}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>
{% else %}
<p class="empty">No data yet. <a href="/join">Be the first to join!</a></p>
{% endif %}
```

- [ ] **Step 3: Create templates/join.html**

```html
{% extends "base.html" %}
{% block content %}
<h1>Join the League</h1>
{% if error %}
<div class="error">{{ error }}</div>
{% endif %}
<form method="post" action="/join">
  <label>
    Duolingo username
    <input type="text" name="duolingo_username" required autofocus>
  </label>
  <label>
    Your real name
    <input type="text" name="real_name" required>
  </label>
  <button type="submit">Join</button>
</form>
{% endblock %}
```

- [ ] **Step 4: Create templates/leave.html**

```html
{% extends "base.html" %}
{% block content %}
<h1>Leave the League</h1>
{% if error %}
<div class="error">{{ error }}</div>
{% endif %}
<form method="post" action="/leave">
  <label>
    Duolingo username
    <input type="text" name="duolingo_username" required autofocus>
  </label>
  <label>
    Your real name (for verification)
    <input type="text" name="real_name" required>
  </label>
  <button type="submit" class="danger">Leave</button>
</form>
{% endblock %}
```

- [ ] **Step 5: Create static/style.css**

```css
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: system-ui, sans-serif;
  background: #f9f9f9;
  color: #1f1f1f;
  line-height: 1.5;
}

header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 2rem;
  background: #fff;
  border-bottom: 1px solid #e5e5e5;
}

.site-title { font-size: 1.2rem; font-weight: 700; text-decoration: none; color: inherit; }
nav a { margin-left: 1.5rem; text-decoration: none; color: #58cc02; font-weight: 600; }

main { max-width: 900px; margin: 2rem auto; padding: 0 1rem; }
h1 { margin-bottom: 1.5rem; }

.tabs { display: flex; gap: 0.5rem; margin-bottom: 1.5rem; }
.tab {
  padding: 0.4rem 1rem;
  border-radius: 20px;
  text-decoration: none;
  background: #eee;
  color: #555;
  font-size: 0.9rem;
}
.tab.active { background: #58cc02; color: #fff; font-weight: 700; }

table { width: 100%; border-collapse: collapse; background: #fff; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,0.06); }
th, td { padding: 0.75rem 1rem; text-align: left; border-bottom: 1px solid #f0f0f0; }
th { background: #f5f5f5; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.05em; color: #888; }
tr:last-child td { border-bottom: none; }
tr:hover td { background: #fafafa; }

.empty { color: #888; margin-top: 2rem; }

form { display: flex; flex-direction: column; gap: 1rem; max-width: 400px; }
label { display: flex; flex-direction: column; gap: 0.3rem; font-weight: 600; font-size: 0.9rem; }
input {
  padding: 0.6rem 0.8rem;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 1rem;
  font-weight: 400;
}
input:focus { outline: none; border-color: #58cc02; box-shadow: 0 0 0 2px #58cc0220; }

button {
  padding: 0.7rem 1.5rem;
  background: #58cc02;
  color: #fff;
  font-weight: 700;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-size: 1rem;
  align-self: flex-start;
}
button:hover { background: #4caf00; }
button.danger { background: #ff4b4b; }
button.danger:hover { background: #e03c3c; }

.error {
  background: #fff0f0;
  border: 1px solid #ffcccc;
  color: #c00;
  padding: 0.75rem 1rem;
  border-radius: 6px;
  margin-bottom: 1rem;
}
```

- [ ] **Step 6: Start dev server and verify visually**

```bash
uvicorn app.main:app --reload
```

Open http://localhost:8000 — check leaderboard, /join, /leave pages.

- [ ] **Step 7: Commit**

```bash
git add templates/ static/
git commit -m "feat: add Jinja2 templates and CSS"
```

---

## Task 9: Dockerfile

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`

- [ ] **Step 1: Create Dockerfile**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Single worker required — APScheduler runs in-process
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
```

- [ ] **Step 2: Create .dockerignore**

```
__pycache__
*.pyc
.env
.venv
tests/
```

- [ ] **Step 3: Commit**

```bash
git add Dockerfile .dockerignore
git commit -m "chore: add Dockerfile for future deployment (single-worker)"
```

---

## Task 10: Run full test suite

- [ ] **Step 1: Run all tests**

```bash
pytest tests/ -v
```

Expected: All tests PASS.

- [ ] **Step 2: Smoke test the running app**

```bash
uvicorn app.main:app --reload
```

- Open http://localhost:8000 — leaderboard loads
- Go to /join, register with your own Duolingo username — you appear on the leaderboard
- Go to /leave, remove yourself — you disappear
- Hit `/admin/refresh?token=<ADMIN_TOKEN>` — returns `{"status": "ok"}`

- [ ] **Step 3: Final commit**

```bash
git add .
git commit -m "chore: verified full test suite and smoke test pass"
```
