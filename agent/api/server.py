from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer


def dispatch(request: dict, handlers: dict) -> dict:
    rid = request.get("id")
    method = request.get("method")
    params = request.get("params") or {}
    handler = handlers.get(method)
    if handler is None:
        return {"jsonrpc": "2.0", "id": rid,
                "error": {"code": -32601, "message": f"method not found: {method}"}}
    try:
        return {"jsonrpc": "2.0", "id": rid, "result": handler(params)}
    except Exception as e:  # surface as a JSON-RPC error, never crash the server
        return {"jsonrpc": "2.0", "id": rid,
                "error": {"code": -32000, "message": str(e)}}


def _make_handler(handlers: dict):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            resp = dispatch(body, handlers)
            payload = json.dumps(resp).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass
    return Handler


def serve(handlers: dict, host="127.0.0.1", port=39099):
    HTTPServer((host, port), _make_handler(handlers)).serve_forever()
