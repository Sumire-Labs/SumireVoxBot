# tests/test_voicevox_client.py
"""
Tests for VoicevoxClient
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import aiohttp
from src.core.voicevox_client import VoicevoxClient


class TestVoicevoxClient:
    """VoicevoxClient クラスのテスト"""

    @pytest.fixture
    def client(self) -> VoicevoxClient:
        """新しい VoicevoxClient インスタンスを作成"""
        with patch.dict("os.environ", {"VOICEVOX_HOST": "localhost", "VOICEVOX_PORT": "50021"}):
            return VoicevoxClient()

    def test_initialization(self, client: VoicevoxClient):
        """初期化が正しく行われることを確認"""
        assert client.base_url == "http://localhost:50021"
        assert client.session is None

    @pytest.mark.asyncio
    async def test_get_session_creates_new_session(self, client: VoicevoxClient):
        """セッションが作成されることを確認"""
        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_session = MagicMock()
            mock_session.closed = False
            mock_session_class.return_value = mock_session

            session = await client._get_session()

            assert session is not None
            mock_session_class.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_session_reuses_existing_session(self, client: VoicevoxClient):
        """既存のセッションが再利用されることを確認"""
        mock_session = MagicMock()
        mock_session.closed = False
        client.session = mock_session

        session = await client._get_session()

        assert session is mock_session

    @pytest.mark.asyncio
    async def test_generate_sound(self, client: VoicevoxClient, mock_aiohttp_session: AsyncMock, tmp_path):
        """音声生成のテスト"""
        client.session = mock_aiohttp_session

        # Mock audio_query response
        query_response = AsyncMock()
        query_response.json = AsyncMock(return_value={"speedScale": 1.0, "pitchScale": 0.0})
        query_response.__aenter__ = AsyncMock(return_value=query_response)
        query_response.__aexit__ = AsyncMock(return_value=None)

        # Mock synthesis response
        synthesis_response = AsyncMock()
        synthesis_response.read = AsyncMock(return_value=b"fake_audio_data")
        synthesis_response.__aenter__ = AsyncMock(return_value=synthesis_response)
        synthesis_response.__aexit__ = AsyncMock(return_value=None)

        mock_aiohttp_session.post = MagicMock(side_effect=[query_response, synthesis_response])

        output_path = str(tmp_path / "test_output.wav")
        result = await client.generate_sound(
            text="テスト",
            speaker_id=1,
            speed=1.0,
            pitch=0.0,
            output_path=output_path
        )

        assert result == output_path

    @pytest.mark.asyncio
    async def test_add_user_dict(self, client: VoicevoxClient, mock_aiohttp_session: AsyncMock):
        """辞書追加のテスト"""
        client.session = mock_aiohttp_session

        result = await client.add_user_dict("テスト", "テスト", 0)

        assert result == "uuid-1234"

    @pytest.mark.asyncio
    async def test_add_user_dict_failure(self, client: VoicevoxClient, mock_aiohttp_session: AsyncMock):
        """辞書追加失敗のテスト"""
        client.session = mock_aiohttp_session

        # Mock error response
        error_response = AsyncMock()
        error_response.status = 400
        error_response.__aenter__ = AsyncMock(return_value=error_response)
        error_response.__aexit__ = AsyncMock(return_value=None)
        mock_aiohttp_session.post = MagicMock(return_value=error_response)

        with pytest.raises(Exception, match="辞書登録失敗"):
            await client.add_user_dict("テスト", "テスト", 0)

    @pytest.mark.asyncio
    async def test_get_user_dict(self, client: VoicevoxClient, mock_aiohttp_session: AsyncMock):
        """辞書取得のテスト"""
        client.session = mock_aiohttp_session

        dict_response = AsyncMock()
        dict_response.json = AsyncMock(return_value={
            "uuid-1": {"surface": "テスト", "pronunciation": "テスト"}
        })
        dict_response.__aenter__ = AsyncMock(return_value=dict_response)
        dict_response.__aexit__ = AsyncMock(return_value=None)
        mock_aiohttp_session.get = MagicMock(return_value=dict_response)

        result = await client.get_user_dict()

        assert "uuid-1" in result

    @pytest.mark.asyncio
    async def test_delete_user_dict(self, client: VoicevoxClient, mock_aiohttp_session: AsyncMock):
        """辞書削除のテスト"""
        client.session = mock_aiohttp_session

        delete_response = AsyncMock()
        delete_response.status = 204
        delete_response.__aenter__ = AsyncMock(return_value=delete_response)
        delete_response.__aexit__ = AsyncMock(return_value=None)
        mock_aiohttp_session.delete = MagicMock(return_value=delete_response)

        result = await client.delete_user_dict("uuid-1234")

        assert result is True

    @pytest.mark.asyncio
    async def test_delete_user_dict_failure(self, client: VoicevoxClient, mock_aiohttp_session: AsyncMock):
        """辞書削除失敗のテスト"""
        client.session = mock_aiohttp_session

        delete_response = AsyncMock()
        delete_response.status = 404
        delete_response.__aenter__ = AsyncMock(return_value=delete_response)
        delete_response.__aexit__ = AsyncMock(return_value=None)
        mock_aiohttp_session.delete = MagicMock(return_value=delete_response)

        with pytest.raises(Exception, match="辞書削除失敗"):
            await client.delete_user_dict("nonexistent-uuid")

    @pytest.mark.asyncio
    async def test_close(self, client: VoicevoxClient, mock_aiohttp_session: AsyncMock):
        """セッションクローズのテスト"""
        client.session = mock_aiohttp_session

        await client.close()

        mock_aiohttp_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_no_session(self, client: VoicevoxClient):
        """セッションがない場合のクローズ"""
        await client.close()  # エラーにならないことを確認
