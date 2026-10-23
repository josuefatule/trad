"""Live appearance control: persistence, permissions and observer delivery."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import httpx

from app.main import Settings, create_app
from app.overlay.style import OverlayStyleStore


class OverlayStyleTests(unittest.IsolatedAsyncioTestCase):
    async def test_live_color_is_saved_broadcast_and_restored_without_clearing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "style.json"
            store = OverlayStyleStore(path)
            with patch("app.main.OverlayStyleStore", return_value=store):
                app = create_app(Settings())
            hub = app.state.caption_hub
            hub.begin("live-session")
            hub.set_state("live-session", "live")
            token = app.state.operator_authority.issue()
            app.state.operator_authority.owner = token
            observer = hub.subscribe()
            self.assertEqual(observer.queue.get_nowait()["overlay_style"]["text_color"], "#ffffff")
            transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 50000))
            async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
                headers = {"Origin": "http://localhost", "X-Operator-Token": token}
                result = await client.post("/api/operator/overlay-style", headers=headers, json={"text_color": "#FFCC00"})
                self.assertEqual(result.status_code, 200)
                self.assertEqual(result.json()["overlay_style"]["text_color"], "#ffcc00")
                event = observer.queue.get_nowait()
                self.assertEqual(event["type"], "overlay_style")
                self.assertEqual(event["overlay_style"]["text_color"], "#ffcc00")
                self.assertEqual(hub.state, "live")
                self.assertEqual(hub.visual_generation, 0)
                status = await client.get("/api/operator/status", headers=headers)
                self.assertEqual(status.json()["overlay_style"]["text_color"], "#ffcc00")
                reconnect = hub.subscribe().queue.get_nowait()
                self.assertEqual(reconnect["overlay_style"]["text_color"], "#ffcc00")
                self.assertEqual(OverlayStyleStore(path).text_color, "#ffcc00")
                result = await client.post("/api/operator/overlay-style", headers=headers, json={"background_color": "#123ABC"})
                self.assertEqual(result.status_code, 200)
                self.assertEqual(result.json()["overlay_style"], {"text_color": "#ffcc00", "background_color": "#123abc"})
                self.assertEqual(observer.queue.get_nowait()["overlay_style"]["background_color"], "#123abc")
                self.assertEqual(hub.subscribe().queue.get_nowait()["overlay_style"]["background_color"], "#123abc")
                self.assertEqual(OverlayStyleStore(path).background_color, "#123abc")
                outsider = app.state.operator_authority.issue()
                forbidden = await client.post("/api/operator/overlay-style", headers={**headers, "X-Operator-Token": outsider}, json={"text_color": "#000000"})
                self.assertEqual(forbidden.status_code, 403)
                forbidden = await client.post("/api/operator/overlay-style", json={"text_color": "#000000"})
                self.assertEqual(forbidden.status_code, 403)
                forbidden = await client.post("/api/operator/overlay-style", headers={**headers, "Origin": "http://other.example"}, json={"text_color": "#000000"})
                self.assertEqual(forbidden.status_code, 403)
                for body in ({"text_color": "red"}, {"text_color": "#fff"}, {"text_color": None}, {"text_color": "#ffffff", "css": "x"}, {"background_color": "red"}, {"background_color": None}, {}, []):
                    invalid = await client.post("/api/operator/overlay-style", headers=headers, json=body)
                    self.assertEqual(invalid.status_code, 400)
                with patch.object(store, "save", side_effect=OSError("disk unavailable")):
                    failed = await client.post("/api/operator/overlay-style", headers=headers, json={"text_color": "#000000"})
                    self.assertEqual(failed.status_code, 503)
                self.assertEqual(hub.overlay_style["text_color"], "#ffcc00")
                self.assertEqual(hub.overlay_style["background_color"], "#123abc")
                self.assertTrue(observer.queue.empty())
