from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from collections import defaultdict

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

rooms = defaultdict(list)

@app.get("/")
async def root():
    return {"status": "ok"}

@app.websocket("/ws/{room_id}")
async def websocket_endpoint(ws: WebSocket, room_id: str):
    await ws.accept()
    rooms[room_id].append(ws)
    print(f"Client joined room {room_id}. Total: {len(rooms[room_id])}")

    try:
        while True:
            data = await ws.receive_text()
            # ретранслируем всем кроме отправителя
            for client in rooms[room_id]:
                if client != ws:
                    await client.send_text(data)

    except WebSocketDisconnect:
        rooms[room_id].remove(ws)
        print(f"Client left room {room_id}. Total: {len(rooms[room_id])}")
