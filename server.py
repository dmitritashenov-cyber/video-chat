from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from collections import defaultdict
import uuid

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

# -----------------------------
# Пользователи (пока в памяти)
# -----------------------------
users = {}  # username -> password

# -----------------------------
# Видеокомнаты
# -----------------------------
rooms = defaultdict(list)

# -----------------------------
# Страницы
# -----------------------------
@app.get("/", response_class=HTMLResponse)
async def login_page():
    with open("static/login.html", "r", encoding="utf-8") as f:
        return f.read()

@app.post("/login")
async def login(username: str = Form(...), password: str = Form(...)):
    # регистрация или логин
    if username not in users:
        users[username] = password
    elif users[username] != password:
        return HTMLResponse("Wrong password", status_code=401)
    return RedirectResponse(url=f"/dashboard?user={username}", status_code=302)

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(user: str):
    with open("static/dashboard.html", "r", encoding="utf-8") as f:
        html = f.read()
        # создаём одну уникальную ссылку на комнату для пользователя
        room_id = uuid.uuid4().hex[:8]
        link = f"/static/room.html?room={room_id}"
        html = html.replace("{{USER}}", user)
        html = html.replace("{{ROOM_LINK}}", link)
        return html

# -----------------------------
# WebSocket для WebRTC
# -----------------------------
@app.websocket("/ws/{room_id}")
async def websocket_endpoint(ws: WebSocket, room_id: str):
    await ws.accept()
    rooms[room_id].append(ws)
    print(f"Client joined {room_id}. Total: {len(rooms[room_id])}")

    try:
        while True:
            data = await ws.receive_text()
            # рассылаем всем кроме отправителя
            for client in rooms[room_id]:
                if client != ws:
                    await client.send_text(data)

    except WebSocketDisconnect:
        rooms[room_id].remove(ws)
        print(f"Client left {room_id}. Total: {len(rooms[room_id])}")
