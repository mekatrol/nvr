from io import BytesIO

from nvr_web.debug_api_handler import DebugApiHandler


class TestableDebugApiHandler(DebugApiHandler):
    def __init__(self, path, method="GET", body=b""):
        self.path = path
        self.command = method
        self.rfile = BytesIO(body)
        self.wfile = BytesIO()
        self.headers = {"Content-Length": str(len(body))}
        self.status = 0
        self.response_headers = {}

    def send_response(self, code, message=None):
        self.status = code

    def send_header(self, keyword, value):
        self.response_headers[keyword] = value

    def end_headers(self):
        return
