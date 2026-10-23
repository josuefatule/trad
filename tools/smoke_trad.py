"""Non-invasive installed-runtime check. No capture, sessions or translator calls."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from urllib.request import Request, ProxyHandler, build_opener
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='.runtime/launcher/last-test.json')
    parser.add_argument('--check-published-overlay', action='store_true',
                        help='Also connect through the assigned LAN address, when the runner permits LAN sockets')
    args = parser.parse_args()
    opener = build_opener(ProxyHandler({}))
    def get(path, token=None):
        headers = {'X-Operator-Token': token} if token else {}
        with opener.open(Request('http://127.0.0.1:8010' + path, headers=headers), timeout=5) as response:
            raw = response.read()
            return json.loads(raw) if 'json' in response.headers.get('Content-Type', '') else raw.decode('utf-8')
    health = get('/health')
    assert health['launcher_version'] == 'mvp-launcher-v1'
    boot = get('/api/operator/bootstrap')
    before = get('/api/operator/status', boot['control_token'])
    assert before['can_start'] and not before['session_open'], 'Deten la sesion antes de probar.'
    with opener.open('http://127.0.0.1:8000/health', timeout=5) as response:
        asr = json.load(response)
    assert asr['ready'] and asr['backend'] == 'faster-whisper'
    assert health['glossary']['concepts'] == 657
    assert health['glossary']['effective_mode'] == 'soft'
    assert health['glossary']['patch']['state'] == 'active'
    html = get('/operator')
    for value in ['this-pc-ip', 'overlay-pc-ip', 'lan-overlay-url', '/static/launcher_network.js']:
        assert value in html, value
    for asset in ['operator_console.js', 'operator.js', 'glossary_control.js', 'launcher_network.js', 'overlay.js', 'caption_renderer.js']:
        assert len(get('/static/' + asset)) > 50
    assert 'overlay-canvas' in get('/overlay')
    config = get('/api/overlay/config')
    assert (config['canvas_width'], config['canvas_height']) == (1920, 1080)
    from websockets.sync.client import connect
    with connect('ws://127.0.0.1:8010/ws/overlay', proxy=None, open_timeout=5) as ws:
        snapshot = json.loads(ws.recv(timeout=5))
        assert snapshot['type'] == 'snapshot' and snapshot['protocol_version'] == 3
        ws.send(json.dumps({'type': 'clock_probe', 'client_sent_ms': 1}))
        assert json.loads(ws.recv(timeout=5))['type'] == 'clock_sync'
    from app.captions.identity_normalizer import IdentityNormalizer
    from app.terminology.rollout import GlossaryConfig, session_normalizer
    normalizer = session_normalizer(GlossaryConfig(mode='soft', state_path=''), 'en', IdentityNormalizer())
    source = 'No hyper tension by this test; primary adosterizm; hypo tension; 5 mg, not 15 mg.'
    normalized = normalizer.normalize('launcher-smoke', source)
    assert normalized.normalized_text == 'No hypertension by this test; primary aldosteronism; hypotension; 5 mg, not 15 mg.'
    assert normalized.raw_text == source
    after = get('/api/operator/status', boot['control_token'])
    assert not after['session_open'] and after['can_start']
    for key in ['session_id', 'sequence', 'translator_verified']:
        assert before[key] == after[key], key
    remote_overlay_checked=False
    network=after['network']
    if args.check_published_overlay and network.get('lan_enabled') and network.get('overlay_access')=='any':
        origin=f"http://{network['local_ip']}:3000"
        with opener.open(origin+'/overlay',timeout=5) as response:
            assert 'overlay-canvas' in response.read().decode('utf-8')
        with opener.open(origin+'/api/overlay/config',timeout=5) as response:
            assert json.load(response)['canvas_width']==1920
        try:
            opener.open(origin+'/operator',timeout=5)
        except HTTPError as error:
            assert error.code==404
        else:
            raise AssertionError('Operator must remain local')
        with connect(f"ws://{network['local_ip']}:3000/ws/overlay",origin=origin,proxy=None,open_timeout=5) as ws:
            assert json.loads(ws.recv(timeout=5))['type']=='snapshot'
            ws.send(json.dumps({'type':'clock_probe','client_sent_ms':1}))
            assert json.loads(ws.recv(timeout=5))['type']=='clock_sync'
        remote_overlay_checked=True
    report = {'result': 'PASS', 'checked_utc': datetime.now(timezone.utc).isoformat(),
              'api_pid': health['server_pid'], 'asr_ready': asr['ready'],
              'concepts': 657, 'glossary_patch': health['glossary']['patch']['version'],
              'operator_network': after['network'], 'overlay_http_ws': True,
              'published_gateway_http_ws': remote_overlay_checked,
              'published_gateway_check_requested': args.check_published_overlay,
              'offline_normalization': True, 'session_started': False,
              'microphone_used': False, 'translation_requested': False,
              'physical_remote_overlay_tested': False}
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print('PASS: ASR listo, Operator, red, 657 conceptos, correcciones y overlay HTTP/WebSocket.')
    print('Sin microfono, sin iniciar sesion y sin solicitar traduccion.')
    print('Informe: ' + str(output))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('FAIL: no se completo la comprobacion. Inicia TRAD y deten la sesion antes de probar.', file=sys.stderr)
        if str(error):
            print(str(error), file=sys.stderr)
        sys.exit(1)
