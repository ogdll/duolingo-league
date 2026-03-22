import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db

@pytest.mark.asyncio
async def test_get_db_yields_session(db):
    assert isinstance(db, AsyncSession)
