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

    async def close(self):
        """Bot終了時などにセッションを安全に閉じるためのメソッド"""
        if self.session:
            await self.session.close()
