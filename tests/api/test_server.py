from runtime.api.server import dispatch


def test_dispatch_calls_handler_and_echoes_id():
    handlers = {"status": lambda params: {"projects": []}}
    resp = dispatch({"jsonrpc": "2.0", "id": 7, "method": "status", "params": {}}, handlers)
    assert resp == {"jsonrpc": "2.0", "id": 7, "result": {"projects": []}}


def test_dispatch_unknown_method_returns_method_not_found():
    resp = dispatch({"jsonrpc": "2.0", "id": 1, "method": "nope", "params": {}}, {})
    assert resp["error"]["code"] == -32601


def test_dispatch_handler_error_is_wrapped():
    def boom(params): raise ValueError("bad")
    resp = dispatch({"jsonrpc": "2.0", "id": 2, "method": "up", "params": {}},
                    {"up": boom})
    assert resp["error"]["code"] == -32000
    assert "bad" in resp["error"]["message"]
