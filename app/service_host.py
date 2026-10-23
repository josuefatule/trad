"""Launcher-owned processes. Importing this module never starts a service."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys


def can_stop(role, app):
    # Recheck in the API event loop: START may race the PowerShell idle check.
    return role != 'api' or app.state.caption_hub.state not in {'connecting', 'live', 'draining'}


def asr_arguments(profile=None):
    profile = profile or os.environ.get('TRAD_ASR_MEMORY_PROFILE', 'bounded')
    if profile not in {'bounded', 'legacy'}:
        raise ValueError('TRAD_ASR_MEMORY_PROFILE must be bounded or legacy')
    arguments = ['wlk_server', '--backend', 'faster-whisper', '--model', 'small',
                 '--lan', 'en', '--pcm-input', '--host', 'localhost', '--port', '8000']
    if profile == 'bounded':
        # Supported WLK 0.2.26 options: limit decoder history, retain full captions.
        arguments += ['--audio-max-len', '10', '--max-context-tokens', '96']
    return arguments


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--role', choices=['api', 'asr', 'gateway'], required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--pid-file', required=True)
    parser.add_argument('--stop-file', required=True)
    parser.add_argument('--local-ip')
    parser.add_argument('--overlay-ip')
    args = parser.parse_args()
    stop_file = Path(args.stop_file)
    if stop_file.exists():
        raise RuntimeError('Previous stop marker; use a new launch run')
    Path(args.pid_file).write_text(json.dumps({'pid': os.getpid(), 'role': args.role,
                                              'run_id': args.run_id}), encoding='utf-8')
    if args.role == 'asr':
        from app.asr.wlk_server import main as wlk_main
        sys.argv = asr_arguments()
        wlk_main()
        return
    import uvicorn
    if args.role == 'api':
        from app.main import app
        host, port = '127.0.0.1', 8010
    else:
        from app.lan_gateway import Policy, create_gateway
        app = create_gateway(Policy(args.local_ip, args.overlay_ip, Path(__file__).resolve().parents[1]))
        host, port = args.local_ip, 3000
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, access_log=False,
        proxy_headers=False, server_header=False, ws_max_size=8192 if args.role == 'gateway' else 1048576,
        ws_max_queue=4, timeout_graceful_shutdown=5))

    async def run():
        async def watch():
            while not server.should_exit:
                if stop_file.exists() and can_stop(args.role, app):
                    server.should_exit = True
                    return
                await asyncio.sleep(.2)
        watcher = asyncio.create_task(watch())
        try:
            await server.serve()
        finally:
            watcher.cancel()
            await asyncio.gather(watcher, return_exceptions=True)
    asyncio.run(run())


if __name__ == '__main__':
    main()
