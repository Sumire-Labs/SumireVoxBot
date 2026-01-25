import os

import jaconv
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Form, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import uvicorn
import secrets

app = FastAPI()
templates = Jinja2Templates(directory="src/templates")
security = HTTPBasic()
vv_client = None

# 認証用のIDとパスワード（好きなものに変えてください）
load_dotenv()
ADMIN_USER = os.getenv("ADMIN_USER")
ADMIN_PASS = os.getenv("ADMIN_PASSWORD")

def authenticate(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, ADMIN_USER)
    correct_password = secrets.compare_digest(credentials.password, ADMIN_PASS)
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="IDまたはパスワードが違います",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    user_dict = await vv_client.get_user_dict()
    return templates.TemplateResponse("index.html", {"request": request, "user_dict": user_dict})

@app.post("/add")
async def add_word(word: str = Form(...), reading: str = Form(...), username: str = Depends(authenticate)):
    # 1. 入力データの正規化 (比較用)
    # 単語(表記)を「全角・小文字」に統一
    input_word = jaconv.h2z(word.strip(), kana=True, digit=True, ascii=True).lower()

    # 読みを「全角カタカナ」に統一
    input_reading = jaconv.hira2kata(jaconv.h2z(reading.strip(), kana=True, digit=False, ascii=False))

    # 2. エンジン側の辞書を取得
    user_dict = await vv_client.get_user_dict()

    # 3. 重複チェック
    # エンジン側の既存データも「全角・小文字」に変換して比較する
    existing_uuids = []
    for uuid, data in user_dict.items():
        # エンジンから返ってくる surface を正規化
        normalized_surface = jaconv.h2z(data['surface'], kana=True, digit=True, ascii=True).lower()

        if normalized_surface == input_word:
            existing_uuids.append(uuid)

    # 4. 重複がある場合は削除
    for old_uuid in existing_uuids:
        try:
            await vv_client.delete_user_dict(old_uuid)
        except:
            pass

    # 5. 登録
    await vv_client.add_user_dict(input_word, input_reading)

    return RedirectResponse(url="/", status_code=303)

@app.post("/delete/{uuid}")
async def delete_word(uuid: str):
    await vv_client.delete_user_dict(uuid)
    return RedirectResponse(url="/", status_code=303)

async def run_web_admin(client):
    global vv_client
    vv_client = client
    # 外部からアクセスする場合は host="0.0.0.0" にします
    config = uvicorn.Config(app, host="0.0.0.0", port=8080, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()
