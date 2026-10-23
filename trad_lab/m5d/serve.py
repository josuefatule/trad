"""Explicitly authorized launch only; imports never listen on a socket."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys

from .prepare import verify


def check_interface(lan_ip):
    # Read Windows state again at launch; never guess an address or change profiles.
    query = "Get-NetIPAddress -AddressFamily IPv4 | Select-Object IPAddress,InterfaceIndex | ConvertTo-Json -Compress"
    result = subprocess.run(["powershell.exe", "-NoProfile", "-Command", query], capture_output=True, text=True, check=True)
    addresses = json.loads(result.stdout)
    addresses = addresses if isinstance(addresses, list) else [addresses]
    match = [row for row in addresses if row["IPAddress"] == lan_ip]
    if len(match) != 1:
        raise ValueError("Select an assigned IPv4 address")
    index = int(match[0]["InterfaceIndex"])
    query = f"Get-NetConnectionProfile -InterfaceIndex {index} | Select-Object NetworkCategory | ConvertTo-Json -Compress"
    result = subprocess.run(["powershell.exe", "-NoProfile", "-Command", query], capture_output=True, text=True, check=True)
    if json.loads(result.stdout)["NetworkCategory"] not in (1, "Private"):
        raise ValueError("A Private Windows interface is required; no profile is changed automatically")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("role", choices=("gateway", "trad", "backend"))
    parser.add_argument("--plan", required=True)
    parser.add_argument("--authorization", required=True)
    parser.add_argument("--lan-ip")
    parser.add_argument("--viewer-ip")
    parser.add_argument("--mode", choices=("replay", "live"), default="replay")
    args = parser.parse_args()
    expected = "M5-D red autorizada"
    if args.role == "backend":
        expected = "M5-D Turbo autorizado"
    elif args.role == "trad" and args.mode == "live":
        expected = "M5-D TRAD con DeepL autorizado"
    if args.authorization != expected:
        raise ValueError("Explicit authorization required for this role")
    data = verify(args.plan)
    copy = Path(data["copy"]).resolve()
    if Path.cwd().resolve() != copy or Path(__file__).resolve().parents[2] != copy:
        raise RuntimeError("Launch from the frozen M5-D copy")
    run = Path(args.plan).resolve().parent
    from trad_lab.m4b.server import listening
    port = {"gateway": 3000, "trad": 18010, "backend": 18000}[args.role]
    if any(listening(p) for p in (8000, 8010)) or listening(port):
        raise RuntimeError("LIVE or target ports occupied; do not restart another process")
    os.environ.update(M5D_MODE=args.mode, M5B_BACKEND="turbo", CAPTIONS_LOG_DIR=str(run / "operational_logs"))
    if args.role == "gateway":
        from .gateway import Policy, create_gateway
        policy = Policy(args.lan_ip, args.viewer_ip, copy)
        check_interface(policy.lan_ip)
        app = create_gateway(policy)
        host = policy.lan_ip
    elif args.role == "trad":
        from app.main import app
        host = "127.0.0.1"
    else:
        if args.mode != "live":
            raise ValueError("Turbo is unnecessary for the first replay test")
        from trad_lab.m5c2.serve import preflight_dependencies
        preflight_dependencies()
        from trad_lab.m5b.serve import restrict_new_key
        key = copy / ".runtime/m5b-service-key.txt"
        if key.exists():
            raise RuntimeError("Existing Turbo runtime; no automatic retry")
        restrict_new_key(key)
        os.environ["M5B_SERVICE_KEY_FILE"] = str(key)
        from trad_lab.m5b.model import load_decoder
        from trad_lab.m5b.transport import Broker, TurboService
        app = TurboService(Broker(load_decoder(run / "turbo_runtime"), run / "turbo_wire"), key.read_text().strip())
        host = "127.0.0.1"
    if args.role == "trad" and args.mode == "live":
        key = copy / ".runtime/m5b-service-key.txt"
        if not key.is_file() or not listening(18000):
            raise RuntimeError("Start the explicitly authorized Turbo first")
        os.environ["M5B_SERVICE_KEY_FILE"] = str(key)
    import uvicorn
    stop_file = copy / ".runtime" / ("m5d-stop-" + args.role)
    stop_file.parent.mkdir(parents=True, exist_ok=True)
    if stop_file.exists():
        raise RuntimeError("Previous stop marker; inspect closure and remove it before a new authorized launch")
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="warning", access_log=False,
        proxy_headers=False, server_header=False, ws_max_size=8192 if args.role == "gateway" else 1048576,
        ws_max_queue=4, limit_concurrency=16, timeout_keep_alive=3, timeout_graceful_shutdown=5))

    async def serve_loop():
        async def watch():
            while not server.should_exit:
                if stop_file.exists():
                    server.should_exit = True
                    return
                await asyncio.sleep(.2)
        watcher = asyncio.create_task(watch()) if args.role == "gateway" or args.mode == "replay" else None
        try:
            await server.serve()
        finally:
            if watcher:
                watcher.cancel()
                await asyncio.gather(watcher, return_exceptions=True)
    try:
        asyncio.run(serve_loop())
    finally:
        if args.role == "gateway":
            # Bounded metadata only; no caption text or viewer credentials.
            (run / "gateway_samples.json").write_text(json.dumps(list(app.state.samples), indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
