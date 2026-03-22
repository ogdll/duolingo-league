# Duolingo Corporate Leagues — Design Spec

**Date:** 2026-03-23
**Status:** Approved
**Type:** Personal proof-of-concept

---

## Overview

A web app where people can self-register into a shared Duolingo league. The app fetches stats daily from Duolingo (XP, streak, league, languages) and displays a leaderboard with views by day, week, month, and all-time.

---

## Data Model

### `users`
| Column | Type | Notes |
|---|---|---|
| id | serial PK | |
| duolingo_username | varchar, unique | entered at registration |
| real_name | varchar | entered at registration |
| joined_at | timestamp | |
| is_active | boolean | false = left the league, data kept |

### `stats_snapshots`
| Column | Type | Notes |
|---|---|---|
| id | serial PK | |
| user_id | FK → users | |
| date | date | one row per user per day; UNIQUE(user_id, date) |
| xp_total | integer | cumulative XP: sum of `xpSums` across all `courses` from API |
| xp_gained_today | integer (nullable) | diff vs. previous snapshot; NULL if no prior snapshot exists; clamped to 0 if XP decreased |
| streak | integer | current streak in days |
| league | varchar | Bronze / Silver / Gold / etc. (from scraper) |
| languages | jsonb | list of language codes (`learningLanguage` from each course) |
| captured_at | timestamp | |

**Leaderboard calculation:**
- **Day** — `xp_gained_today` from the latest snapshot (NULL treated as 0 in rankings)
- **Week / Month** — `xp_total` diff between the earliest and latest snapshot within the period. For users who joined mid-period, the registration snapshot is the period-start anchor.
- **All-time** — latest `xp_total`

**Upsert semantics:** The daily job uses `INSERT ... ON CONFLICT (user_id, date) DO UPDATE` so re-runs and manual refreshes are idempotent.

---

## Duolingo Data Fetching

**Primary:** Unofficial API endpoint
```
GET https://www.duolingo.com/2017-06-30/users?fields=username,name,streak,xpGains,lingots,courses,currentCourse&username={username}
```

**Response mapping:**
| API field | Model column |
|---|---|
| `courses[].xpSums` summed | `xp_total` |
| `streak` | `streak` |
| `courses[].learningLanguage` | `languages` |
| league | not in API — use scraper |

**Fallback (league only):** Scrape `https://www.duolingo.com/profile/{username}`. Parse the league badge element (CSS selector: `[data-test="league-tile"]` or the `<h2>` within `.league-section` — to be confirmed against live HTML at implementation time).

**XP per day:** `xp_gained_today = max(0, xp_total_today - xp_total_yesterday)`. Negative diffs (Duolingo XP corrections) are clamped to 0 and logged for debugging.

**On registration:** An immediate first fetch validates the username exists and seeds the first snapshot. `xp_gained_today` is NULL for the registration snapshot (no prior to diff against).

**Daily update:** APScheduler runs a job at 02:00 UTC (`SCHEDULER_HOUR` env var, interpreted as UTC). Iterates all `is_active = true` users. Each user's fetch is wrapped in a try/except — a failure logs the error and skips that user's snapshot for the day without aborting the job.

---

## Pages

| Route | Description |
|---|---|
| `/` | Leaderboard — tabs: Day / Week / Month / All-time. Tab switching without page reload (vanilla JS). Columns: rank, name, XP, streak, league, languages. |
| `/join` | Registration form — Duolingo username + real name. Validates username against Duolingo on submit, seeds first snapshot. Error states: (1) username not found on Duolingo → "Username not found — check your Duolingo profile URL"; (2) username already registered → "This username is already in the league"; (3) Duolingo API unreachable → "Couldn't reach Duolingo right now — try again in a few minutes". |
| `/leave` | Exit form — enter Duolingo username + registered real name (used as a second factor). Sets `is_active = false`. Known limitation: no strong identity verification in v1. |
| `/admin/refresh` | Manual trigger for stats update. Protected by a static token in `.env` (`ADMIN_TOKEN`) passed as a query param. Rate-limited to 1 request/minute. |

**UI:** Minimal, clean CSS, no framework. Desktop-first for prototype.

---

## Project Structure

```
amitim/
├── app/
│   ├── main.py          # FastAPI app, routes, APScheduler setup
│   ├── models.py        # SQLAlchemy models (users, stats_snapshots)
│   ├── database.py      # PostgreSQL connection, session factory
│   ├── duolingo.py      # Data fetching: API + scraping fallback
│   └── leaderboard.py   # Leaderboard query logic (day/week/month/all-time)
├── templates/
│   ├── base.html        # shared layout
│   ├── index.html       # leaderboard with tabs
│   ├── join.html        # registration form
│   └── leave.html       # leave form
├── static/
│   └── style.css
├── .env                 # DATABASE_URL, SCHEDULER_HOUR, ADMIN_TOKEN
├── requirements.txt
└── Dockerfile           # single-worker only (uvicorn --workers 1) — required for in-process APScheduler
```

---

## Stack

| Component | Choice |
|---|---|
| Backend | FastAPI |
| Templates | Jinja2 |
| Scheduler | APScheduler (in-process) |
| ORM | SQLAlchemy |
| Database | PostgreSQL |
| HTTP client | httpx (async) |
| HTML parsing | BeautifulSoup4 |
| Deployment | Railway or Render (future); must deploy with single Uvicorn worker |

---

## Out of Scope (v1)

- Authentication / admin panel
- Language-specific leaderboards (planned for later)
- Email notifications
- Mobile-optimized UI
- Historical charts
