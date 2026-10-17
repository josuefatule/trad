"""Authenticated local operator harness; production security stays enabled in tests."""
from fastapi.testclient import TestClient as BaseClient


class TestClient(BaseClient):
    __test__ = False

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("base_url", "http://localhost")
        kwargs.setdefault("client", ("127.0.0.1", 50000))
        super().__init__(*args, **kwargs)

    def websocket_connect(self, url, **kwargs):
        if url == "/ws/session":
            token = self.get("/api/operator/bootstrap").json()["control_token"]
            kwargs.setdefault("subprotocols", ["operator.v1", token])
            kwargs.setdefault("headers", {"origin": "http://localhost"})
        if url.startswith("/"):
            url = "ws://localhost" + url
        return super().websocket_connect(url, **kwargs)
