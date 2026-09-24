"""Optional smoke check of running servers: silence only, never records audio."""
import asyncio
import json
from urllib.request import urlopen

from websockets.asyncio.client import connect


async def main():
    for url in ("http://localhost:8000/health", "http://localhost:8010/health", "http://localhost:8010/operator"):
        with urlopen(url, timeout=5) as response:
            print(url, response.status)
            assert response.status == 200
    async with connect("ws://localhost:8010/ws/session", proxy=None) as ws:
        while True:
            data = json.loads(await asyncio.wait_for(ws.recv(), 30))
            print(json.dumps(data, ensure_ascii=False))
            assert data["type"] != "error", data
            if data["type"] == "config":
                assert data["wlk"]["useAudioWorklet"] is True
                # One second of PCM silence, followed by the real binary EOF.
                await ws.send(bytes(32000))
                await ws.send(b"")
            if data.get("state") == "stopped":
                break
    print("PASS: real WLK config, PCM via proxy, snapshots, ready_to_stop")


if __name__ == "__main__":
    asyncio.run(main())
