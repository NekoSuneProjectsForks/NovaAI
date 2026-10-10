from __future__ import annotations

import cgi
import html
import json
import shutil
import socketserver
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Callable

try:
    import websockets
    from websockets import WebSocketServerProtocol
except ImportError:  # pragma: no cover
    websockets = None
    WebSocketServerProtocol = object

from .paths import AVATAR_UPLOADS_DIR, ROOT_DIR, STATIC_DIR


class AvatarHttpRequestHandler(BaseHTTPRequestHandler):
    server_version = "NovaAIAvatarHTTP/1.0"

    def do_GET(self) -> None:
        if self.path in {"/", "/index.html"}:
            self._serve_file(STATIC_DIR / "avatar.html", content_type="text/html; charset=utf-8")
            return

        if self.path.startswith("/uploads/"):
            local_path = AVATAR_UPLOADS_DIR / self.path[len("/uploads/") :]
            self._serve_file(local_path, content_type="application/octet-stream")
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Resource not found")

    def do_POST(self) -> None:
        if self.path != "/upload":
            self.send_error(HTTPStatus.NOT_FOUND, "Resource not found")
            return

        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            self.send_error(HTTPStatus.BAD_REQUEST, "Expected multipart/form-data")
            return

        form = cgi.FieldStorage(
            fp=self.rfile,
            headers=self.headers,
            environ={
                "REQUEST_METHOD": "POST",
                "CONTENT_TYPE": content_type,
            },
        )

        file_item = form.getfirst("file") if not form else form.get("file")
        if file_item is None or not getattr(file_item, "filename", None):
            self.send_error(HTTPStatus.BAD_REQUEST, "No file uploaded")
            return

        filename = Path(file_item.filename).name
        filename = html.escape(filename)
        target_path = AVATAR_UPLOADS_DIR / filename
        target_path.parent.mkdir(parents=True, exist_ok=True)

        with target_path.open("wb") as output_file:
            shutil.copyfileobj(file_item.file, output_file)

        url = f"/uploads/{target_path.name}"
        self.send_response(HTTPStatus.CREATED)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            json.dumps(
                {
                    "success": True,
                    "url": url,
                    "name": target_path.name,
                },
                ensure_ascii=False,
            ).encode("utf-8")
        )

        if isinstance(self.server, AvatarHttpServer):
            self.server.on_upload(target_path)

    def log_message(self, format: str, *args: object) -> None:
        # Suppress standard HTTP request logging in the GUI.
        pass

    def _serve_file(self, path: Path, content_type: str) -> None:
        if not path.exists() or not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "Resource not found")
            return

        try:
            with path.open("rb") as source:
                content = source.read()
        except OSError:
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "Unable to read file")
            return

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


class AvatarHttpServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True

    def __init__(self, server_address, RequestHandlerClass, on_upload: Callable[[Path], None]):
        super().__init__(server_address, RequestHandlerClass)
        self.on_upload = on_upload


class AvatarBridge:
    def __init__(
        self,
        on_vrm_loaded: Callable[[Path], None],
        http_host: str = "127.0.0.1",
        http_port: int = 8766,
        ws_port: int = 8765,
    ) -> None:
        self.on_vrm_loaded = on_vrm_loaded
        self.http_host = http_host
        self.http_port = http_port
        self.ws_port = ws_port
        self.http_server: AvatarHttpServer | None = None
        self.http_thread: threading.Thread | None = None
        self.ws_thread: threading.Thread | None = None
        self.ws_loop = None
        self.ws_clients: set[WebSocketServerProtocol] = set()
        self.current_avatar_url: str | None = None

    def start(self) -> None:
        AVATAR_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        STATIC_DIR.mkdir(parents=True, exist_ok=True)

        self.http_server = AvatarHttpServer(
            (self.http_host, self.http_port),
            AvatarHttpRequestHandler,
            on_upload=self._handle_upload,
        )
        self.http_server.RequestHandlerClass.server = self.http_server
        self.http_thread = threading.Thread(
            target=self.http_server.serve_forever,
            daemon=True,
            name="NovaAIAvatarHTTP",
        )
        self.http_thread.start()

        if websockets is None:
            print(
                "[NovaAI Avatar] websockets package is not installed. "
                "Install it with: pip install websockets"
            )
            return

        self.ws_loop = __import__("asyncio").new_event_loop()
        self.ws_thread = threading.Thread(
            target=self._run_ws_loop,
            daemon=True,
            name="NovaAIAvatarWS",
        )
        self.ws_thread.start()

    def _run_ws_loop(self) -> None:
        import asyncio

        asyncio.set_event_loop(self.ws_loop)
        try:
            start_server = websockets.serve(self._ws_handler, self.http_host, self.ws_port)
            self.ws_loop.run_until_complete(start_server)
            self.ws_loop.run_forever()
        except Exception as exc:
            print(f"[NovaAI Avatar] WebSocket bridge failed to start: {exc}")

    async def _ws_handler(self, websocket: WebSocketServerProtocol) -> None:
        self.ws_clients.add(websocket)
        try:
            await websocket.send(json.dumps({"type": "hello", "status": "connected"}))
            if self.current_avatar_url:
                await websocket.send(
                    json.dumps(
                        {"type": "avatar", "event": "current", "url": self.current_avatar_url}
                    )
                )
            while True:
                await websocket.recv()
        except Exception:
            pass
        finally:
            self.ws_clients.discard(websocket)

    def _handle_upload(self, path: Path) -> None:
        self.on_vrm_loaded(path)

    def publish_avatar(self, url: str) -> None:
        self.current_avatar_url = url
        self._broadcast({"type": "avatar", "event": "load", "url": url})

    def publish_state(self, state: dict[str, object]) -> None:
        self._broadcast({"type": "state", "payload": state})

    def publish_reminder(self, reminder: dict[str, object]) -> None:
        self._broadcast({"type": "reminder", "event": "due", "reminder": reminder})

    def _broadcast(self, payload: dict[str, object]) -> None:
        if self.ws_loop is None or websockets is None:
            return
        import asyncio

        async def send_all() -> None:
            if not self.ws_clients:
                return
            data = json.dumps(payload)
            await asyncio.gather(
                *[client.send(data) for client in list(self.ws_clients)],
                return_exceptions=True,
            )

        asyncio.run_coroutine_threadsafe(send_all(), self.ws_loop)

    def get_frontend_url(self) -> str:
        return f"http://{self.http_host}:{self.http_port}/"

    def get_ws_url(self) -> str:
        return f"ws://{self.http_host}:{self.ws_port}/"
