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
ADMIN_USER = "admin"
ADMIN_PASS = "sumire-password-2026"

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
async def index(request: Request, username: str = Depends(authenticate)):
    user_dict = await vv_client.get_user_dict()
    return templates.TemplateResponse("index.html", {"request": request, "user_dict": user_dict})

@app.post("/add")
async def add_word(word: str = Form(...), reading: str = Form(...), username: str = Depends(authenticate)):
    await vv_client.add_user_dict(word, reading)
    return RedirectResponse(url="/", status_code=303)

@app.post("/delete/{uuid}")
async def delete_word(uuid: str, username: str = Depends(authenticate)):
    await vv_client.delete_user_dict(uuid)
    return RedirectResponse(url="/", status_code=303)

async def run_web_admin(client):
    global vv_client
    vv_client = client
    # 外部からアクセスする場合は host="0.0.0.0" にします
    config = uvicorn.Config(app, host="0.0.0.0", port=8080, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()