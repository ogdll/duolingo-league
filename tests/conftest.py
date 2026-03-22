import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.models import Base
from app.main import app
from app.database import get_db

TEST_DB_URL = "postgresql+asyncpg://user:password@localhost:5432/duolingo_leagues_test"

_engine = create_async_engine(TEST_DB_URL)
_AsyncTestSession = async_sessionmaker(_engine, expire_on_commit=False)

@pytest_asyncio.fixture(scope="session")
async def engine():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield _engine
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await _engine.dispose()

@pytest_asyncio.fixture
async def db(engine):
    async with _AsyncTestSession() as session:
        yield session
        await session.rollback()

@pytest_asyncio.fixture
async def client(db):
    async def override_get_db():
        yield db
    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    del app.dependency_overrides[get_db]
