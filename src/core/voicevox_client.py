import aiofiles
import aiohttp
import json
import os


class VoicevoxClient:
    def __init__(self):
        host = os.getenv("VOICEVOX_HOST", "127.0.0.1")
        port = os.getenv("VOICEVOX_PORT", "50021")
        self.base_url = f"http://{host}:{port}"
        self.session = None # type: aiohttp.ClientSession or None

    # create an API session
    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def generate_sound(self, text: str, speaker_id: int = 0, speed: float = 1.0, pitch: float = 0.0, output_path: str = "output.wav"):
        # 使い回しのセッションを取得
        session = await self._get_session()

        # audio_query
        async with session.post(f"{self.base_url}/audio_query", params={"text": text, "speaker": speaker_id}) as resp:
            query_data = await resp.json()

        # 設定を反映
        query_data["speedScale"] = speed
        query_data["pitchScale"] = pitch

        # synthesis
        async with session.post(
                f"{self.base_url}/synthesis",
                params={"speaker": speaker_id},
                data=json.dumps(query_data),
                headers={"Content-Type": "application/json"}
        ) as resp:
            audio_data = await resp.read()

        async with aiofiles.open(output_path, "wb") as f:
            await f.write(audio_data)
        return output_path

    async def add_user_dict(self, surface: str, pronunciation: str, accent_type: int = 0):
        """エンジン側のユーザー辞書に単語を登録する"""
        session = await self._get_session()
        params = {
            "surface": surface,
            "pronunciation": pronunciation,
            "accent_type": accent_type
        }
        async with session.post(f"{self.base_url}/user_dict_word", params=params) as resp:
            if resp.status != 200:
                raise Exception(f"辞書登録失敗: {resp.status}")
            return await resp.text() # 登録された単語のUUIDが返る

    async def get_user_dict(self):
        """エンジン側のユーザー辞書一覧を取得"""
        session = await self._get_session()
        async with session.get(f"{self.base_url}/user_dict") as resp:
            # { "uuid": { "surface": "単語", "pronunciation": "ヨミ", ... }, ... }
            return await resp.json()

    async def delete_user_dict(self, uuid: str):
        """エンジン側のユーザー辞書から特定のUUIDを削除"""
        session = await self._get_session()
        async with session.delete(f"{self.base_url}/user_dict_word/{uuid}") as resp:
            if resp.status != 204:
                raise Exception(f"辞書削除失敗: {resp.status}")
            return True

    async def close(self):
        """Bot終了時などにセッションを安全に閉じるためのメソッド"""
        if self.session:
            await self.session.close()
