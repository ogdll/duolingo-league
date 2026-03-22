import pytest
from sqlalchemy.ext.asyncio import AsyncSession

@pytest.mark.asyncio
async def test_get_db_yields_session(db):
    assert isinstance(db, AsyncSession)
