from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import json, os

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

# ===== USERS =====
USERS_FILE = "users.json"
if not os.path.exists(USERS_FILE):
    with open(USERS_FILE, "w") as f:
        json.dump({}, f)

def load_users():
    with open(USERS_FILE, "r") as f:
        return json.load(f)

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f)

# ===== LOGIN / REGISTER =====
@app.get("/", response_class=HTMLResponse)
def index():
    return open("static/login.html").read()

@app.post("/login")
async def login(username: str = Form(...), password: str = Form(...)):
    users = load_users()
    if username in users and users[username]["password"] == password:
        return RedirectResponse(url=f"/dashboard?user={username}", status_code=302)
    return HTMLResponse("<h3>Неверное имя или пароль. <a href='/'>Попробовать снова</a></h3>")

@app.post("/register")
async def register(username: str = Form(...), password: str = Form(...)):
    users = load_users()
    if username in users:
        return HTMLResponse("<h3>Пользователь уже существует. <a href='/'>Войти</a></h3>")
    users[username] = {"password": password}
    save_users(users)
    return RedirectResponse(url=f"/dashboard?user={username}", status_code=302)

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(user: str):
    html = open("static/dashboard.html").read()
    return html.replace("{{username}}", user)

# ===== ROOMS =====
rooms = {}

@app.websocket("/ws/{room_id}")
async def websocket_endpoint(ws: WebSocket, room_id: str):
    await ws.accept()
    if room_id not in rooms:
        rooms[room_id] = []
    rooms[room_id].append(ws)
    idx = len(rooms[room_id]) - 1
    print(f"Client connected to {room_id}. Index={idx}")

    # Отправляем start только если есть хотя бы 2 участников
    if len(rooms[room_id]) >= 2:
        for client in rooms[room_id]:
            try:
                await client.send_text('{"type":"start"}')
            except:
                pass

    try:
        while True:
            msg = await ws.receive_text()
            for client in rooms[room_id]:
                if client != ws:
                    try:
                        await client.send_text(msg)
                    except:
                        pass
    except WebSocketDisconnect:
        rooms[room_id].remove(ws)
        print("Client disconnected")
