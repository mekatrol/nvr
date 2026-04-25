from __future__ import annotations

from http.server import ThreadingHTTPServer

from nvr_web.debug_api_handler import DebugApiHandler


class NvrWebServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 8080) -> None:
        self.host = host
        self.port = port
        self.server = ThreadingHTTPServer((host, port), DebugApiHandler)

    def serve_forever(self) -> None:
        self.server.serve_forever()

    def shutdown(self) -> None:
        self.server.shutdown()
