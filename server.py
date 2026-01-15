from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from collections import defaultdict
import uuid

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

# -----------------------------
# CORS (для тестов)
# -----------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# Пользователи (в памяти)
# -----------------------------
users = {}  # username -> password
messages = defaultdict(list)  # username -> list of notifications/links

# -----------------------------
# Видеокомнаты
# -----------------------------
rooms = defaultdict(dict)  # room_id -> {client_id: WebSocket}

# -----------------------------
# Страницы
# -----------------------------
@app.get("/", response_class=HTMLResponse)
async def login_page():
    with open("static/login.html", "r", encoding="utf-8") as f:
        return f.read()

@app.post("/login")
async def login(username: str = Form(...), password: str = Form(...)):
    if username not in users:
        users[username] = password
    elif users[username] != password:
        return HTMLResponse("Wrong password", status_code=401)
    return RedirectResponse(url=f"/dashboard?user={username}", status_code=302)

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(user: str):
    with open("static/dashboard.html", "r", encoding="utf-8") as f:
        html = f.read()
        # создаём уникальную ссылку на комнату
        room_id = uuid.uuid4().hex[:8]
        link = f"/static/room.html?room={room_id}"
        html = html.replace("{{USER}}", user)
        html = html.replace("{{ROOM_LINK}}", link)
        # добавить сообщения
        inbox = "<br>".join(messages[user])
        html = html.replace("{{INBOX}}", inbox if inbox else "No messages")
        return html

@app.post("/send_link")
async def send_link(sender: str = Form(...), recipient: str = Form(...), link: str = Form(...)):
    if recipient in users:
        messages[recipient].append(f"From {sender}: {link}")
    return RedirectResponse(url=f"/dashboard?user={sender}", status_code=302)

# -----------------------------
# WebSocket для WebRTC и чата
# -----------------------------
@app.websocket("/ws/{room_id}")
async def websocket_endpoint(ws: WebSocket, room_id: str):
    await ws.accept()
    client_id = uuid.uuid4().hex[:8]
    rooms[room_id][client_id] = ws
    print(f"Client {client_id} joined {room_id}. Total: {len(rooms[room_id])}")

    # Отправляем новому клиенту список уже подключенных
    existing_clients = [cid for cid in rooms[room_id] if cid != client_id]
    await ws.send_text(f'{{"type":"existing","clients":{existing_clients}}}')

    try:
        while True:
            data = await ws.receive_text()
            # Проверяем, обычное ли это сообщение чата
            import json
            try:
                msg_obj = json.loads(data)
                # Если есть поле "chat", рассылаем всем
                if "chat" in msg_obj:
                    for cid2, ws2 in rooms[room_id].items():
                        if cid2 != client_id:
                            await ws2.send_text(json.dumps({"from": client_id, "chat": msg_obj["chat"]}))
                else:
                    # иначе это сигнал WebRTC
                    for cid2, ws2 in rooms[room_id].items():
                        if cid2 != client_id:
                            await ws2.send_text(f'{{"from":"{client_id}",{data[1:]}}}')
            except:
                # если не JSON, пересылаем как есть
                for cid2, ws2 in rooms[room_id].items():
                    if cid2 != client_id:
                        await ws2.send_text(f'{{"from":"{client_id}",{data[1:]}}}')
    except WebSocketDisconnect:
        del rooms[room_id][client_id]
        print(f"Client {client_id} left {room_id}. Total: {len(rooms[room_id])}")
