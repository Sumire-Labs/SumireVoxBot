# tests/conftest.py
"""
pytest fixtures for SumireVoxBot tests
"""

import pytest
import asyncio
import os
from unittest.mock import AsyncMock, MagicMock
from typing import Generator

# 環境変数のモック設定
os.environ.setdefault("POSTGRES_USER", "test_user")
os.environ.setdefault("POSTGRES_PASSWORD", "test_password")
os.environ.setdefault("POSTGRES_DB", "test_db")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5432")
os.environ.setdefault("VOICEVOX_HOST", "localhost")
os.environ.setdefault("VOICEVOX_PORT", "50021")
os.environ.setdefault("GLOBAL_DICT_ID", "1201")
os.environ.setdefault("MIN_BOOST_LEVEL", "0")
os.environ.setdefault("DISCORD_TOKEN", "test_token")


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_aiohttp_session() -> AsyncMock:
    """Mock aiohttp ClientSession"""
    session = AsyncMock()

    # Mock response
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={})
    mock_response.read = AsyncMock(return_value=b"audio_data")
    mock_response.text = AsyncMock(return_value="uuid-1234")
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)

    session.post = MagicMock(return_value=mock_response)
    session.get = MagicMock(return_value=mock_response)
    session.delete = MagicMock(return_value=mock_response)
    session.close = AsyncMock()
    session.closed = False

    return session


@pytest.fixture
def mock_discord_guild() -> MagicMock:
    """Mock Discord Guild"""
    guild = MagicMock()
    guild.id = 123456789
    guild.name = "Test Guild"
    guild.voice_client = None
    guild.get_channel = MagicMock(return_value=None)
    return guild


@pytest.fixture
def mock_discord_member() -> MagicMock:
    """Mock Discord Member"""
    member = MagicMock()
    member.id = 987654321
    member.display_name = "TestUser"
    member.bot = False
    member.guild = MagicMock()
    member.guild.id = 123456789
    member.voice = MagicMock()
    member.voice.channel = MagicMock()
    member.voice.channel.id = 111222333
    return member


@pytest.fixture
def mock_discord_message() -> MagicMock:
    """Mock Discord Message"""
    message = MagicMock()
    message.author = MagicMock()
    message.author.id = 987654321
    message.author.bot = False
    message.author.display_name = "TestUser"
    message.guild = MagicMock()
    message.guild.id = 123456789
    message.guild.voice_client = MagicMock()
    message.guild.voice_client.is_playing = MagicMock(return_value=False)
    message.channel = MagicMock()
    message.channel.id = 444555666
    message.content = "Hello, World!"
    message.clean_content = "Hello, World!"
    message.attachments = []
    message.mentions = []
    return message


@pytest.fixture
def mock_discord_interaction() -> MagicMock:
    """Mock Discord Interaction"""
    interaction = MagicMock()
    interaction.user = MagicMock()
    interaction.user.id = 987654321
    interaction.user.voice = MagicMock()
    interaction.user.voice.channel = MagicMock()
    interaction.user.voice.channel.id = 111222333
    interaction.guild = MagicMock()
    interaction.guild.id = 123456789
    interaction.guild.voice_client = None
    interaction.guild_id = 123456789
    interaction.channel = MagicMock()
    interaction.channel.id = 444555666
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()
    interaction.response.is_done = MagicMock(return_value=False)
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    return interaction


@pytest.fixture
def sample_guild_settings() -> dict:
    """Sample guild settings data"""
    return {
        "auto_join": False,
        "auto_join_config": {},
        "max_chars": 50,
        "read_vc_status": False,
        "read_mention": True,
        "read_emoji": True,
        "add_suffix": False,
        "read_romaji": False,
        "read_attachments": True,
        "skip_code_blocks": True,
        "skip_urls": True
    }


@pytest.fixture
def sample_user_settings() -> dict:
    """Sample user settings data"""
    return {
        "speaker": 1,
        "speed": 1.0,
        "pitch": 0.0
    }


@pytest.fixture
def sample_dictionary() -> dict:
    """Sample dictionary data"""
    return {
        "こんにちは": "コンニチハ",
        "Discord": "ディスコード",
        "Bot": "ボット"
    }
