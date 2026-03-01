# src/cogs/voice/handlers/on_ready.py
import asyncio

from ..session.restore_voice_sessions import restore_voice_sessions


async def on_ready(bot, read_channels: dict, state: dict) -> None:
    if state.get("_session_restore_done"):
        return
    state["_session_restore_done"] = True

    await asyncio.sleep(2)
    await restore_voice_sessions(bot, read_channels)
