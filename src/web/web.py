from dotenv import load_dotenv
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
import os
import jaconv
from loguru import logger
from src.core.database import Database

# データベースの初期化
db = Database()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 起動時に接続
    await db.connect()
    yield
    # 終了時に切断
    await db.close()


app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="src/web/template")

# 環境変数からグローバル辞書IDを取得
GLOBAL_DICT_ID = int(os.getenv("GLOBAL_DICT_ID", 1201))


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    words = await db.get_dict(GLOBAL_DICT_ID)
    return templates.TemplateResponse("index.html", {
        "request": request,
        "words": words,
        "guild_id": GLOBAL_DICT_ID
    })


@app.post("/add")
async def add_word(word: str = Form(...), reading: str = Form(...)):
    word = word.strip()
    reading = reading.strip()

    if not word or not reading:
        return RedirectResponse(url="/", status_code=303)

    # 読み方の正規化 (カタカナ変換)
    try:
        normalized_reading = jaconv.h2z(reading, kana=True, digit=False, ascii=False)
        normalized_reading = jaconv.hira2kata(normalized_reading)
    except Exception as e:
        logger.error(f"読み方の正規化エラー: {e}")
        return RedirectResponse(url="/", status_code=303)

    words = await db.get_dict(GLOBAL_DICT_ID)
    words[word] = normalized_reading
    await db.add_or_update_dict(GLOBAL_DICT_ID, words)

    logger.info(f"[Web] グローバル辞書追加: {word} -> {normalized_reading}")
    return RedirectResponse(url="/", status_code=303)


@app.post("/delete")
async def delete_word(word: str = Form(...)):
    words = await db.get_dict(GLOBAL_DICT_ID)
    if word in words:
        del words[word]
        await db.add_or_update_dict(GLOBAL_DICT_ID, words)
        logger.info(f"[Web] グローバル辞書削除: {word}")

    return RedirectResponse(url="/", status_code=303)


if __name__ == "__main__":
    import uvicorn
    load_dotenv()
    WEB_PORT = int(os.getenv("WEB_PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=WEB_PORT)