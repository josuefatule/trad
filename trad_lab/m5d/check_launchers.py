"""Exercise the launcher shutdown writer with a fake server, never TCP."""
import argparse
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch


def check(out):
    from trad_lab.m5d import serve
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    copy = out / "copy"
    copy.mkdir()
    sample = {"fixture": True, "type": "render_sample", "sequence": 1}
    app = SimpleNamespace(state=SimpleNamespace(samples=[sample]))
    server_calls = []

    class Server:
        should_exit = False
        def __init__(self, config):
            assert config.host == "192.168.50.10" and config.port == 3000
            assert config.proxy_headers is False
            assert config.ws_max_size == 8192
        async def serve(self):
            server_calls.append("fake-server-closed")

    old = Path.cwd()
    args = ["test", "gateway", "--plan", str(out / "plan.json"), "--lan-ip", "192.168.50.10",
            "--viewer-ip", "192.168.50.20", "--authorization", "M5-D red autorizada"]
    try:
        os.chdir(copy)
        with patch.object(sys, "argv", args), \
             patch.object(serve, "verify", return_value={"copy": str(copy)}), \
             patch.object(serve, "__file__", str(copy / "trad_lab/m5d/serve.py")), \
             patch.object(serve, "check_interface") as interface, \
             patch("trad_lab.m4b.server.listening", return_value=False), \
             patch("trad_lab.m5d.gateway.create_gateway", return_value=app), \
             patch("uvicorn.Server", Server):
            serve.main()
            interface.assert_called_once_with("192.168.50.10")
    finally:
        os.chdir(old)
    assert server_calls == ["fake-server-closed"]
    assert json.loads((out / "gateway_samples.json").read_text(encoding="utf-8")) == [sample]
    result = {"status": "PASS", "scope": "Real launcher main/finally, fake Uvicorn server, real bounded output file; no network or provider",
              "regression": "Gateway output path must remain a Path after the async server loop closes"}
    (out / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    check(args.out)
