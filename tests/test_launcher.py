import asyncio
from dataclasses import replace
from contextlib import asynccontextmanager
import json
from pathlib import Path
import socket
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
import uvicorn

from app.lan_gateway import Policy, create_gateway, LoopbackUpstream
from app.launcher_network import network_status
from app.service_host import can_stop
from app.main import Settings, create_app
from app.translation import TranslationConfig
from tests.test_operator_control import local_client, authorize, headers
from tests.test_overlay import translated

ROOT = Path(__file__).resolve().parents[1]


class NetworkTests(unittest.TestCase):
    def test_api_rechecks_active_session_before_accepting_stop_marker(self):
        app = SimpleNamespace(state=SimpleNamespace(caption_hub=SimpleNamespace(state='live')))
        for state in ['connecting', 'live', 'draining']:
            app.state.caption_hub.state = state
            self.assertFalse(can_stop('api', app))
            self.assertTrue(can_stop('gateway', app))
        for state in ['waiting', 'stopped', 'error', 'disconnected']:
            app.state.caption_hub.state = state
            self.assertTrue(can_stop('api', app))

    def status(self, data):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'network.json'
            path.write_text(json.dumps(data), encoding='utf-8-sig')
            return network_status(path)

    def test_network_selected_addresses_and_url_no_secrets_or_supplied_urls(self):
        result = self.status(dict(local_ip='192.168.50.10', local_ips=['192.168.50.10'],
            overlay_pc_ip='192.168.50.20', network_profile='Private', lan_enabled=True,
            overlay_url='https://evil.example/', token='secret'))
        self.assertTrue(result['lan_enabled'])
        self.assertEqual(result['overlay_url'], 'http://192.168.50.10:3000/overlay')
        self.assertNotIn('secret', str(result))

    def test_unsafe_network_configuration_never_produces_remote_link(self):
        base = dict(local_ip='192.168.50.10', local_ips=['192.168.50.10'],
                    overlay_pc_ip='192.168.50.20', network_profile='Private', lan_enabled=True)
        for change in [dict(network_profile='Public'), dict(overlay_pc_ip='8.8.8.8'),
                       dict(overlay_pc_ip='192.168.50.10'), dict(local_ip='192.168.50.99'),
                       dict(lan_enabled=False), dict(overlay_pc_ip=None)]:
            with self.subTest(change=change):
                result = self.status({**base, **change})
                self.assertFalse(result['lan_enabled'])
                self.assertIsNone(result['overlay_url'])

    def test_open_overlay_works_on_public_profile_without_receiver_ip(self):
        for profile in ['Public','Private','DomainAuthenticated']:
            result=self.status(dict(local_ip='192.168.50.10',local_ips=['192.168.50.10'],
                overlay_pc_ip=None,network_profile=profile,lan_enabled=True,overlay_access='any'))
            self.assertTrue(result['lan_enabled'])
            self.assertEqual('http://192.168.50.10:3000/overlay',result['overlay_url'])
            self.assertEqual('any',result['overlay_access'])

    def test_malformed_state_falls_back_without_throwing(self):
        for data in [None, [], 'invalid', {'local_ips': 12}]:
            self.assertFalse(self.status(data)['lan_enabled'])

    def test_network_only_visible_in_authenticated_operator_status(self):
        app = create_app(Settings(log_dir='logs/tests', translation=TranslationConfig(enabled=False)))
        with local_client(app) as client:
            self.assertEqual(403, client.get('/api/operator/status').status_code)
            token = authorize(client)
            data = client.get('/api/operator/status', headers=headers(token)).json()
            self.assertIn('network', data)
            self.assertNotIn('network', client.get('/health').json())
            self.assertNotIn('network', client.get('/api/overlay/config').json())
            self.assertIn('IP DE ESTA PC', client.get('/operator').text)


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.policy = Policy('192.168.50.10', '192.168.50.20', ROOT)
        self.app = create_gateway(self.policy)

    def client(self, **kwargs):
        return TestClient(self.app, base_url=self.policy.origin, client=('192.168.50.20', 50000), **kwargs)

    def test_routes_only_read_only_assets_no_operator_or_secrets(self):
        with self.client() as client:
            self.assertEqual(200, client.get('/overlay').status_code)
            for name in ['overlay.css','overlay.js','caption_renderer.js','overlay_latency.js','overlay_geometry.js']:
                self.assertEqual(200, client.get('/static/' + name).status_code)
            for path in ['/operator','/capture','/api/operator/bootstrap','/api/operator/status',
                         '/api/operator/clear','/ws/session','/.env','/health','/docs',
                         '/static/operator.js','/static/launcher_network.js','/overlay?token=x']:
                self.assertEqual(404, client.get(path).status_code, path)
            self.assertEqual(404, client.post('/overlay').status_code)
            self.assertEqual(404, client.head('/overlay').status_code)

    def test_peer_host_origin_and_queries_are_enforced(self):
        with TestClient(self.app, base_url=self.policy.origin, client=('192.168.50.21', 1)) as client:
            self.assertEqual(404, client.get('/overlay', headers={'X-Forwarded-For': self.policy.viewer_ip}).status_code)
        with self.client() as client:
            for value in [{'host': 'localhost:3000'}, {'origin': 'http://evil.example'}, {'sec-fetch-site': 'cross-site'}]:
                self.assertEqual(404, client.get('/overlay', headers=value).status_code)
            with self.assertRaises(WebSocketDisconnect):
                with client.websocket_connect('/ws/overlay', headers={'origin': 'http://evil.example'}):
                    pass

    def test_invalid_policies(self):
        for a, b in [('0.0.0.0','192.168.50.20'), ('192.168.50.10','8.8.8.8'), ('192.168.50.10','192.168.50.10')]:
            with self.assertRaises(ValueError):
                Policy(a, b, ROOT)

    def test_open_policy_allows_multiple_viewers_but_no_operator_or_commands(self):
        policy=Policy('192.168.50.10',None,ROOT)
        class Source:
            first=True
            async def recv(self):
                if self.first:
                    self.first=False
                    return json.dumps({'type':'snapshot','protocol_version':3,'session_id':None,'direction':None})
                await asyncio.Event().wait()
        class Upstream:
            @asynccontextmanager
            async def subscribe(self): yield Source()
        app=create_gateway(policy,Upstream())
        for peer in ['192.168.50.20','192.168.50.21','127.0.0.1','198.51.100.20']:
            with TestClient(app,base_url=policy.origin,client=(peer,50000)) as client:
                self.assertEqual(200,client.get('/overlay').status_code)
                self.assertEqual(404,client.get('/operator').status_code)
                self.assertEqual(404,client.post('/api/operator/stop').status_code)
                with client.websocket_connect('ws://'+policy.host+'/ws/overlay',headers={'origin':policy.origin}) as ws:
                    self.assertEqual('snapshot',ws.receive_json()['type'])
                    ws.send_json({'type':'stop'})
                    with self.assertRaises(WebSocketDisconnect): ws.receive_json()


class GatewayPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_hub_to_gateway_overlay_clear_and_remote_controls_blocked_no_audio_no_translation(self):
        with tempfile.TemporaryDirectory() as directory:
            app = create_app(Settings(log_dir=directory, translation=TranslationConfig(enabled=False)))
            hub = app.state.caption_hub
            hub.begin('launcher-synthetic', direction={'source_language':'en','target_language':'es','id':'en-es'})
            bound = socket.socket()
            bound.bind(('127.0.0.1', 0)); bound.listen(128)
            server = uvicorn.Server(uvicorn.Config(app, log_level='error', lifespan='on'))
            task = asyncio.create_task(server.serve(sockets=[bound]))
            try:
                for _ in range(100):
                    if server.started:
                        break
                    await asyncio.sleep(.05)
                self.assertTrue(server.started)
                policy = Policy('192.168.50.10','192.168.50.20',ROOT)
                gateway = create_gateway(policy, LoopbackUpstream(bound.getsockname()[1]))
                loop = asyncio.get_running_loop()
                def browser():
                    with TestClient(gateway, base_url=policy.origin, client=(policy.viewer_ip, 50000)) as client:
                        self.assertEqual(200, client.get('/api/overlay/config').status_code)
                        with client.websocket_connect('ws://' + policy.host + '/ws/overlay', headers={'origin':policy.origin}) as ws:
                            self.assertEqual('snapshot', ws.receive_json()['type'])
                            loop.call_soon_threadsafe(hub.set_state, 'launcher-synthetic', 'live')
                            ws.receive_json()
                            caption = replace(translated(1,'launcher-synthetic',text='PRUEBA SINTETICA SIN TRADUCCION.'), source_language='en', target_language='es')
                            loop.call_soon_threadsafe(hub.publish, caption)
                            event = ws.receive_json()
                            self.assertEqual('caption',event['type'])
                            self.assertEqual('PRUEBA SINTETICA SIN TRADUCCION.',event['caption']['text'])
                            loop.call_soon_threadsafe(hub.clear_captions, 'launcher-synthetic', 0)
                            self.assertEqual('captions_cleared',ws.receive_json()['type'])
                            ws.send_json({'type':'clock_probe','client_sent_ms':1})
                            self.assertEqual('clock_sync',ws.receive_json()['type'])
                            ws.send_json({'type':'stop'})
                            with self.assertRaises(WebSocketDisconnect): ws.receive_json()
                        self.assertEqual(404,client.post('/api/operator/clear').status_code)
                await asyncio.wait_for(asyncio.to_thread(browser), 15)
                self.assertEqual('launcher-synthetic',hub.session_id)
                self.assertEqual(1,hub.sequence)
                self.assertEqual(0,hub.broadcast_errors)
                self.assertFalse(gateway.state.active)
            finally:
                server.should_exit = True
                await asyncio.wait_for(task, 10)
