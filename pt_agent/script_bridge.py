"""Local HTTP bridge for a Packet Tracer Script Module.

The vendored PTS extension polls ``/next`` every 500 ms. Each returned
snippet runs inside PT through its ``__mcpEval`` helper, which posts a
hex-encoded result to ``/result``.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from queue import Empty, Queue
from typing import Callable
from urllib.parse import urlparse


class ScriptBridgeError(RuntimeError):
    """Script Engine bridge communication failed."""


def wrap_expression(expression: str, port: int) -> str:
    """Wrap a self-contained JS expression for the vendored PT extension."""
    return f"__mcpEval({json.dumps(expression, ensure_ascii=False)},{port});"


def decode_result_hex(body: str) -> str:
    """Decode the hex text posted by the PT Script Module."""
    cleaned = "".join(ch for ch in body if ch in "0123456789abcdefABCDEF")
    if len(cleaned) % 2:
        raise ScriptBridgeError("Result contains an odd number of hex digits")
    try:
        raw = bytes.fromhex(cleaned)
    except ValueError as exc:
        raise ScriptBridgeError("Result is not valid hex") from exc
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="replace")


class PTBridgeServer:
    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 54321,
        result_timeout: float = 30.0,
        logger: Callable[[str], None] | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.result_timeout = result_timeout
        self.logger = logger or (lambda message: None)
        self._commands: Queue[str] = Queue(maxsize=100)
        self._results: Queue[str] = Queue()
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._last_poll = 0.0
        self._status_lock = threading.Lock()
        self._client_headers: dict[str, str] = {}
        self._request_count = 0

    @property
    def connected(self) -> bool:
        with self._status_lock:
            return self._last_poll > 0 and time.time() - self._last_poll < 5.0

    def status(self) -> dict[str, object]:
        return {
            "connected": self.connected,
            "host": self.host,
            "port": self.port,
            "queue_length": self._commands.qsize(),
            "last_poll_ago": (
                round(time.time() - self._last_poll, 1)
                if self._last_poll
                else None
            ),
            "client_headers": dict(self._client_headers),
            "request_count": self._request_count,
        }

    def start(self) -> None:
        if self._server is not None:
            return

        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def _cors(self) -> None:
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type, *")

            def _host_ok(self) -> bool:
                host = (self.headers.get("Host") or "").strip().lower()
                return host in (
                    f"127.0.0.1:{bridge.port}",
                    f"localhost:{bridge.port}",
                )

            def _send_text(
                self,
                status: int,
                body: str,
                content_type: str = "text/plain; charset=utf-8",
            ) -> None:
                encoded = body.encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(encoded)))
                self._cors()
                self.end_headers()
                self.wfile.write(encoded)

            def _remember_client(self) -> None:
                with bridge._status_lock:
                    bridge._request_count += 1
                    if not bridge._client_headers:
                        for header in (
                            "Origin",
                            "User-Agent",
                            "Sec-Fetch-Site",
                            "Sec-Fetch-Mode",
                        ):
                            value = self.headers.get(header)
                            if value:
                                bridge._client_headers[header] = value

            def do_OPTIONS(self) -> None:
                self.send_response(204)
                self._cors()
                self.end_headers()

            def do_GET(self) -> None:
                if not self._host_ok():
                    self._send_text(403, "forbidden")
                    return

                path = urlparse(self.path).path
                if path == "/ping":
                    self._send_text(200, "pong")
                    return
                if path == "/status":
                    self._send_text(
                        200,
                        json.dumps(bridge.status(), ensure_ascii=False),
                        "application/json; charset=utf-8",
                    )
                    return
                if path == "/next":
                    self._remember_client()
                    with bridge._status_lock:
                        bridge._last_poll = time.time()
                    try:
                        command = bridge._commands.get_nowait()
                    except Empty:
                        command = ""
                    self._send_text(200, command)
                    return
                self._send_text(404, "not found")

            def do_POST(self) -> None:
                if not self._host_ok():
                    self._send_text(403, "forbidden")
                    return

                path = urlparse(self.path).path
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    self._send_text(400, "invalid content length")
                    return
                if length < 0 or length > 1_000_000:
                    self._send_text(413, "body too large")
                    return
                body = self.rfile.read(length).decode("utf-8", errors="replace")

                if path == "/result":
                    try:
                        result = decode_result_hex(body)
                    except ScriptBridgeError as exc:
                        self._send_text(400, str(exc))
                        return
                    bridge._results.put(result)
                    self._send_text(200, "ok")
                    return
                if path == "/queue":
                    try:
                        bridge._commands.put_nowait(body)
                    except Exception:
                        self._send_text(503, "queue full")
                        return
                    self._send_text(200, "queued")
                    return
                self._send_text(404, "not found")

            def log_message(self, format: str, *args) -> None:
                return

        server = ThreadingHTTPServer((self.host, self.port), Handler)
        self.port = int(server.server_address[1])
        self._server = server
        self._thread = threading.Thread(
            target=server.serve_forever,
            name="pt-script-bridge",
            daemon=True,
        )
        self._thread.start()
        self.logger(f"bridge listening on http://{self.host}:{self.port}")

    def stop(self) -> None:
        if self._server is None:
            return
        server = self._server
        self._server = None
        server.shutdown()
        server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def wait_for_extension(self, timeout: float = 60.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.connected:
                return
            time.sleep(0.25)
        raise ScriptBridgeError(
            "Packet Tracer extension did not poll the bridge. "
            "Install the PTS module and open its window."
        )

    def send_and_wait(self, expression: str, timeout: float | None = None) -> str:
        wait = self.result_timeout if timeout is None else timeout
        while True:
            try:
                self._results.get_nowait()
            except Empty:
                break
        try:
            self._commands.put(wrap_expression(expression, self.port), timeout=5)
        except Exception as exc:
            raise ScriptBridgeError("Bridge command queue is full") from exc
        try:
            return self._results.get(timeout=wait)
        except Empty as exc:
            raise ScriptBridgeError(
                f"Script Engine returned no result within {wait:.1f}s"
            ) from exc

    def execute_json(self, expression: str, timeout: float | None = None) -> object:
        result = self.send_and_wait(expression, timeout=timeout)
        if result.startswith("ERROR:"):
            raise ScriptBridgeError(result)
        try:
            return json.loads(result)
        except json.JSONDecodeError as exc:
            raise ScriptBridgeError(
                f"Expected JSON result, received: {result!r}"
            ) from exc

