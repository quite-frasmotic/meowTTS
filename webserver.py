import twitchbot
import uvicorn
import tts
import asyncio
import re
import json
import traceback
import os

from common import event_bus
from mutagen.mp3 import MP3
from io import BytesIO
from starlette.websockets import WebSocket, WebSocketDisconnect
from starlette.responses import HTMLResponse
from starlette.routing import Route, WebSocketRoute, Mount
from starlette.applications import Starlette
from starlette.staticfiles import StaticFiles
from starlette.requests import Request

HTML_INDEX = """
<!doctype html>
<head><title>meowTTS Browser Source</title>
</head>
<body>
<audio id="player"></audio>
<script src="/static/app.js?v=15"></script>
</body>
"""
ADMIN_USERS = os.environ.get("ADMIN_USERS")

open_sockets: set[WebSocket] = set()
tts_queue = asyncio.Queue()
minimum_bits = 10


async def index(request: Request) -> HTMLResponse:
    return HTMLResponse(HTML_INDEX)


async def websocket_manager(socket: WebSocket):
    await socket.accept()
    open_sockets.add(socket)

    print("New websocket connection")
    print(f"Number of open sockets: {len(open_sockets)}")

    try:
        while True:
            await socket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        open_sockets.discard(socket)
        print("Lost websocket connection")
        print(f"Number of open sockets: {len(open_sockets)}")


routes = [
    Route("/", index),
    WebSocketRoute("/ws", websocket_manager),
    Mount("/static", app=StaticFiles(directory="static"), name="static"),
]

app = Starlette(debug=True, routes=routes)
app.mount("/", twitchbot.adapter)


@app.on_event("startup")
async def queue_tasks() -> None:
    # Listen for events from common event bus (e.g. from Twitch bot)
    async def event_consumer():
        while True:
            event, payload = await event_bus.get()
            await dispatch(event, payload)

    async def tts_consumer():
        while True:
            user, message = await tts_queue.get()
            await tts_worker(user, message)

    asyncio.create_task(event_consumer())
    asyncio.create_task(tts_consumer())


async def dispatch(event: str, payload) -> None:
    if event == "channel.cheer" and payload.bits >= minimum_bits:
        print(
            f'Bits received! "{payload.user}"\
            \n- Amount: "{payload.bits}"\
            \n- Message: "{payload.message}"'
        )

        # TODO: Move this message cleaning to the same bit in tts.py
        clean_message = re.sub(r"\bCheer\d+\b", "", payload.message)
        await tts_queue.put((payload.user, clean_message))

    if event == "channel.message" and payload.chatter.name in ADMIN_USERS:
        if "!tts " in payload.text:
            print("new tts item in queue:")
            print(tts_queue)
            await tts_queue.put((payload.chatter.name, payload.text[5:]))


async def tts_worker(user, message) -> None:
    generated_audio = await tts.generate(user, message)
    chunks: list[bytes] = []
    async for chunk in generated_audio:
        if chunk is not None:
            chunks.append(chunk)
    await stream_mp3(chunks, open_sockets)

    byte_string = b"".join(chunks)
    buffer = BytesIO(byte_string)
    audio_length = MP3(buffer).info.length
    await asyncio.sleep(audio_length + 3)


async def broadcast_text(sockets, text: str):
    dead_sockets = set()
    tasks = []
    for socket in sockets:
        try:
            tasks.append(socket.send_text(text))
        except Exception as exception:
            print(f"Error queueing send for socket: {exception}")
            dead_sockets.add(socket)

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

    for socket in dead_sockets:
        open_sockets.discard(socket)


async def broadcast_bytes(sockets, data):
    dead_sockets = set()
    tasks = []
    for socket in sockets:
        try:
            tasks.append(socket.send_bytes(data))
        except Exception as exception:
            print(f"Error queueing send for socket: {exception}")
            dead_sockets.add(socket)

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

    for socket in dead_sockets:
        open_sockets.discard(socket)


JSON_START = json.dumps({"type": "start"})
JSON_END = json.dumps({"type": "end"})


async def stream_mp3(mp3: list[bytes], sockets) -> None:
    print("Starting audio broadcast...")
    try:
        await broadcast_text(sockets, JSON_START)
        for chunk in mp3:
            if not isinstance(chunk, bytes):
                continue

            await broadcast_bytes(sockets, chunk)

            '''if len(chunk) % 2:
                print("Odd chunk, adding one extra blank byte")
                chunk += b"\x00"'''
        await broadcast_text(sockets, JSON_END)

    except Exception as exception:
        print(f"Error in broadcast stream: {exception}")
        print(traceback.format_exc())

    print("Broadcast finished")


async def main():
    config = uvicorn.Config(app=app, host="127.0.0.1", port=4343, loop="asyncio")
    server = uvicorn.Server(config)

    await asyncio.gather(twitchbot.initialise(), server.serve())


if __name__ == "__main__":
    asyncio.run(main())
