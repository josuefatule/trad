import asyncio
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock,patch
from .runtime import Diagnostics,DiagnosticBrowser,VerifiedConnection,connect,SESSION


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_no_silent_backend_fallback(self):
        for selected,payload in [('turbo',{'type':'config'}),('wlk',{'type':'config','backend':'turbo-experimental'})]:
            fake=SimpleNamespace(recv=AsyncMock(return_value=json.dumps(payload)))
            with self.assertRaisesRegex(ValueError,'selection mismatch'):await VerifiedConnection(fake,selected).recv()

    async def test_eof_metadata_distinguishes_transport_and_transcription(self):
        d=Diagnostics();d.begin('a');browser=SimpleNamespace(send_json=AsyncMock())
        wrapper=DiagnosticBrowser(browser,d,'a')
        tail=[{'text':' aldosterone','start':1.,'end':2.}]
        await wrapper.send_json({'type':'asr','payload':{'type':'ready_to_stop','unconfirmed_eof_tail':tail}})
        tail[0]['text']='mutated'
        await wrapper.send_json({'type':'status','state':'stopped','completion':'complete'})
        diagnostic=browser.send_json.call_args.args[0]['experimental_asr']
        self.assertEqual(diagnostic['transport_completion'],'complete')
        self.assertEqual(diagnostic['transcription_completion'],'unconfirmed_tail')
        self.assertEqual(diagnostic['unconfirmed_eof_tail'][0]['text'],' aldosterone')

    async def test_rollback_does_not_claim_unreported_tail_confirmed(self):
        d=Diagnostics();d.begin('a')
        wrapper=DiagnosticBrowser(SimpleNamespace(send_json=AsyncMock()),d,'a')
        await wrapper.send_json({'type':'asr','payload':{'type':'ready_to_stop'}})
        self.assertEqual(d.data['transcription_completion'],'not_reported_by_wlk')

    async def test_new_session_resets_tail_and_rejects_old_events(self):
        d=Diagnostics();d.begin('a');old=DiagnosticBrowser(SimpleNamespace(send_json=AsyncMock()),d,'a')
        d.data['unconfirmed_eof_tail']=[{'text':'old'}];d.begin('b')
        self.assertFalse(d.data['unconfirmed_eof_tail'])
        with self.assertRaises(RuntimeError):await old.send_json({'type':'status'})

    async def test_connector_rejects_live_ports_without_connecting(self):
        with patch.dict(os.environ,{'M5B_BACKEND':'turbo'}),patch('trad_lab.m5b.runtime.network_connect',AsyncMock()) as network:
            for url in ('ws://127.0.0.1:8000/asr','ws://localhost:18000/asr','ws://127.0.0.1:18000/asr?mode=full&language=es'):
                with self.assertRaises(RuntimeError):await connect(url)
            network.assert_not_called()

    async def test_launch_requires_later_authorization_before_any_server(self):
        from .serve import main
        with patch('sys.argv',['m5b','trad','--plan','absent','--backend','turbo','--authorization','not approved']):
            with self.assertRaisesRegex(ValueError,'human'):main()

    async def test_backend_rejection_is_not_a_deepl_auth_error(self):
        from websockets.exceptions import InvalidHandshake
        from app.operator_control import operational_error
        with patch.dict(os.environ,{'M5B_BACKEND':'wlk'}),patch('trad_lab.m5b.runtime.network_connect',AsyncMock(side_effect=InvalidHandshake('HTTP 403'))):
            with self.assertRaises(RuntimeError) as raised:await connect('ws://127.0.0.1:18000/asr?mode=full&language=en')
        self.assertNotEqual(operational_error(raised.exception)[0],'translation_auth')

    async def test_diagnosed_backend_failure_does_not_restart_startup(self):
        from app.asr.whisperlivekit_client import starting_connection
        from app.reliability import ReliabilityConfig
        from .flow import PhaseError
        fake=SimpleNamespace(recv=AsyncMock(side_effect=PhaseError('backend','decoder_timeout_native_call_quarantined')),
                             close=AsyncMock())
        network=AsyncMock(return_value=fake)
        settings=SimpleNamespace(connect_timeout=1.,reliability=ReliabilityConfig(connect_attempts=3))
        with patch('app.asr.whisperlivekit_client.connect',network):
            with self.assertRaisesRegex(PhaseError,'backend_decoder_timeout'):
                async with starting_connection('ws://unused',settings,AsyncMock(),json.loads):
                    self.fail('Failed config must never yield an upstream')
        self.assertEqual(network.await_count,1)
        fake.close.assert_awaited_once()


if __name__=='__main__':unittest.main()
