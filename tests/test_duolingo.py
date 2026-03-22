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
