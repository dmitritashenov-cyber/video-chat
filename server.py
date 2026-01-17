"""
Video Chat Application Server
A FastAPI-based video chat application with WebRTC support.
"""
import json
import logging
import os
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Инициализация приложения
app = FastAPI(
    title="Video Chat Application",
    description="WebRTC video chat with messaging",
    version="1.0.0"
)

# CORS middleware для работы с различными доменами
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене лучше указать конкретные домены
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключение статических файлов
static_dir = Path("static")
if static_dir.exists():
    app.mount("/static", StaticFiles(directory="static"), name="static")
else:
    logger.warning(f"Static directory {static_dir} not found")

# -----------------------------
# Хранилище данных (в продакшене лучше использовать БД)
# -----------------------------
users: Dict[str, str] = {}  # username -> password
messages: Dict[str, List[str]] = defaultdict(list)  # username -> list of notifications/links
rooms: Dict[str, Dict[str, WebSocket]] = defaultdict(dict)  # room_id -> {client_id: WebSocket}


# -----------------------------
# Вспомогательные функции
# -----------------------------
def load_static_file(filename: str) -> str:
    """Безопасная загрузка статических HTML файлов."""
    file_path = static_dir / filename
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logger.error(f"File not found: {file_path}")
        raise HTTPException(status_code=404, detail=f"File {filename} not found")
    except Exception as e:
        logger.error(f"Error reading file {file_path}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


def validate_username(username: str) -> bool:
    """Валидация имени пользователя."""
    if not username or len(username) < 3:
        return False
    if not username.replace("_", "").replace("-", "").isalnum():
        return False
    return True


# -----------------------------
# API маршруты
# -----------------------------
@app.get("/", response_class=HTMLResponse)
async def login_page():
    """Главная страница входа."""
    try:
        return load_static_file("login.html")
    except Exception as e:
        logger.error(f"Error loading login page: {e}")
        raise


@app.post("/login")
async def login(username: str = Form(...), password: str = Form(...)):
    """Обработка входа/регистрации пользователя."""
    if not validate_username(username):
        raise HTTPException(
            status_code=400,
            detail="Username must be at least 3 characters and contain only letters, numbers, _, or -"
        )
    
    if not password or len(password) < 3:
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 3 characters"
        )
    
    # Регистрация нового пользователя
    if username not in users:
        users[username] = password
        logger.info(f"New user registered: {username}")
    # Проверка пароля существующего пользователя
    elif users[username] != password:
        logger.warning(f"Invalid password attempt for user: {username}")
        raise HTTPException(status_code=401, detail="Wrong password")
    
    return RedirectResponse(url=f"/dashboard?user={username}", status_code=302)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(user: str):
    """Страница дашборда пользователя."""
    if user not in users:
        raise HTTPException(status_code=401, detail="User not authenticated")
    
    try:
        html = load_static_file("dashboard.html")
        room_id = uuid.uuid4().hex[:8]
        link = f"/static/room.html?room={room_id}"
        
        # Безопасная замена шаблонов
        html = html.replace("{{USER}}", user)
        html = html.replace("{{ROOM_LINK}}", link)
        
        inbox = "<br>".join(messages[user])
        html = html.replace("{{INBOX}}", inbox if inbox else "No messages")
        
        return html
    except Exception as e:
        logger.error(f"Error loading dashboard for user {user}: {e}")
        raise


@app.post("/send_link")
async def send_link(
    sender: str = Form(...),
    recipient: str = Form(...),
    link: str = Form(...)
):
    """Отправка ссылки на комнату другому пользователю."""
    if sender not in users:
        raise HTTPException(status_code=401, detail="Sender not authenticated")
    
    if recipient not in users:
        logger.warning(f"Attempt to send link to non-existent user: {recipient}")
        # Не показываем, что пользователь не существует (для безопасности)
        return RedirectResponse(url=f"/dashboard?user={sender}", status_code=302)
    
    if recipient != sender:
        messages[recipient].append(f"From {sender}: {link}")
        logger.info(f"Link sent from {sender} to {recipient}")
    
    return RedirectResponse(url=f"/dashboard?user={sender}", status_code=302)


# -----------------------------
# WebSocket для комнаты и чата
# -----------------------------
@app.websocket("/ws/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    """WebSocket endpoint для видеокомнаты с WebRTC сигнализацией."""
    await websocket.accept()
    client_id = uuid.uuid4().hex[:8]
    rooms[room_id][client_id] = websocket
    
    logger.info(f"Client {client_id} joined room {room_id}. Total clients: {len(rooms[room_id])}")
    
    # Отправка списка существующих клиентов новому клиенту
    existing_clients = [cid for cid in rooms[room_id] if cid != client_id]
    try:
        await websocket.send_text(
            json.dumps({"type": "existing", "clients": existing_clients})
        )
    except Exception as e:
        logger.error(f"Error sending existing clients to {client_id}: {e}")
    
    try:
        while True:
            data = await websocket.receive_text()
            
            try:
                msg_obj = json.loads(data)
                
                # Обработка чата
                if "chat" in msg_obj:
                    chat_message = msg_obj.get("chat", "").strip()
                    if chat_message:
                        broadcast_message = json.dumps({
                            "from": client_id,
                            "chat": chat_message
                        })
                        
                        # Отправка сообщения чата всем остальным клиентам
                        disconnected_clients = []
                        for cid, ws in rooms[room_id].items():
                            if cid != client_id:
                                try:
                                    await ws.send_text(broadcast_message)
                                except Exception as e:
                                    logger.warning(f"Failed to send chat message to {cid}: {e}")
                                    disconnected_clients.append(cid)
                        
                        # Очистка отключенных клиентов
                        for cid in disconnected_clients:
                            rooms[room_id].pop(cid, None)
                
                # Обработка WebRTC сигналов
                else:
                    target_client = msg_obj.get("to")
                    broadcast_message = json.dumps({"from": client_id, **msg_obj})
                    
                    # Отправка сигнала конкретному клиенту или всем остальным
                    disconnected_clients = []
                    for cid, ws in rooms[room_id].items():
                        if cid != client_id and (not target_client or cid == target_client):
                            try:
                                await ws.send_text(broadcast_message)
                            except Exception as e:
                                logger.warning(f"Failed to send WebRTC signal to {cid}: {e}")
                                disconnected_clients.append(cid)
                    
                    # Очистка отключенных клиентов
                    for cid in disconnected_clients:
                        rooms[room_id].pop(cid, None)
            
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON received from {client_id}: {data}")
                # Пропускаем невалидный JSON
    
    except WebSocketDisconnect:
        logger.info(f"Client {client_id} disconnected from room {room_id}")
    except Exception as e:
        logger.error(f"Error in websocket for client {client_id}: {e}")
    finally:
        # Очистка при отключении
        rooms[room_id].pop(client_id, None)
        
        # Удаление пустых комнат (опционально, можно оставить для будущих подключений)
        if not rooms[room_id]:
            rooms.pop(room_id, None)
            logger.info(f"Room {room_id} is now empty and removed")
        
        logger.info(f"Client {client_id} left room {room_id}. Remaining clients: {len(rooms.get(room_id, {}))}")


# -----------------------------
# Health check endpoint для Render
# -----------------------------
@app.get("/health")
async def health_check():
    """Health check endpoint для мониторинга."""
    return {
        "status": "healthy",
        "active_rooms": len(rooms),
        "total_users": len(users)
    }


if __name__ == "__main__":
    import uvicorn
    
    # Получение порта из переменной окружения (для Render)
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    
    uvicorn.run(app, host=host, port=port, log_level="info")
