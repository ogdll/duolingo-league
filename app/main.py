from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, AsyncSessionLocal
from app.duolingo import DuolingoUnavailable, DuolingoUserNotFound, fetch_user_stats, save_snapshot
from app.leaderboard import get_leaderboard
from app.models import StatsSnapshot, User

load_dotenv()
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
SCHEDULER_HOUR = int(os.getenv("SCHEDULER_HOUR", "2"))

import time
_last_refresh_at: float = float('-inf')
_REFRESH_COOLDOWN_SECONDS = 60

scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.add_job(_run_daily_update, "cron", hour=SCHEDULER_HOUR, timezone="UTC")
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


async def _run_daily_update() -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.is_active == True))
        users = result.scalars().all()
        for user in users:
            try:
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
    return templates.TemplateResponse(request, "index.html", {
        "rows": rows, "period": period
    })


@app.get("/api/leaderboard")
async def api_leaderboard(period: str = "day", db: AsyncSession = Depends(get_db)):
    rows = await get_leaderboard(db, period=period)
    return rows


@app.get("/join", response_class=HTMLResponse)
async def join_form(request: Request):
    return templates.TemplateResponse(request, "join.html", {"error": None})


@app.post("/join", response_class=HTMLResponse)
async def join_submit(
    request: Request,
    duolingo_username: str = Form(...),
    real_name: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    def error(msg: str):
        return templates.TemplateResponse(request, "join.html", {"error": msg})

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
    return templates.TemplateResponse(request, "leave.html", {"error": None})


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
        return templates.TemplateResponse(request, "leave.html", {
            "error": "No active member found with that username and name"
        })
    user.is_active = False
    await db.commit()
    return RedirectResponse("/", status_code=303)


@app.post("/admin/refresh")
async def admin_refresh(token: str = ""):
    global _last_refresh_at
    if not ADMIN_TOKEN or token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")
    now = time.monotonic()
    if now - _last_refresh_at < _REFRESH_COOLDOWN_SECONDS:
        raise HTTPException(status_code=429, detail="Rate limit: wait 60 seconds between refreshes")
    _last_refresh_at = now
    await _run_daily_update()
    return {"status": "ok"}
