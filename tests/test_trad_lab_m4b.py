import asyncio
import base64
import json
from pathlib import Path
import tempfile
import unittest

from trad_lab.m4b.tap import EvidenceWriter, WireTap, projection
from trad_lab.m4b.analyze import validate_triplet, verify_stream, latency, clock_models, mapped, analyze


class PhysicalIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'logs')
        self.root=Path(self.tmp.name)

    def tearDown(self):self.tmp.cleanup()

    def make(self,name,kind,blocks):
        writer=EvidenceWriter(self.root/name)
        for i,b in enumerate(blocks):
            r={'kind':kind,'seq':i,'b64':base64.b64encode(b).decode()}
            if kind=='pre':r.update(samples=len(b)//4,sample_rate=48000,channels=1,frame=i*3)
            self.assertTrue(writer.submit([r]))
        writer.close();self.assertIsNone(writer.failed);return writer.path

    def triplet(self):
        import struct
        a=self.make('browser','pre',[struct.pack('<fff',.1,.2,.3),struct.pack('<fff',.4,.5,.6)])
        # Add browser sent stream with the same writer directory's log/summary.
        b=self.make('sent','sent',[b'\x01\x00',b'\x02\x00',b''])
        (a/'sent.s16le').write_bytes((b/'sent.s16le').read_bytes())
        with (a/'events.jsonl').open('a',encoding='utf-8') as f:f.write((b/'events.jsonl').read_text(encoding='utf-8'))
        sa=json.loads((a/'writer.json').read_text());sb=json.loads((b/'writer.json').read_text());sa['streams'].update(sb['streams'])
        (a/'writer.json').write_text(json.dumps(sa))
        tr=self.make('trad','received',[b'\x01\x00',b'\x02\x00',b''])
        wl=self.make('wlk','received',[b'\x01\x00',b'\x02\x00',b''])
        return a,tr,wl

    def test_exact_transport_and_worklet_count(self):
        a,tr,wl=self.triplet();integrity,_,_=validate_triplet(a,tr,wl)
        self.assertTrue(integrity['three_way_sha256_equal']);self.assertEqual(integrity['pre_samples'],6)

    def test_corruption_missing_frame_and_duplicate_eof_rejected(self):
        a,tr,wl=self.triplet();(wl/'received.s16le').write_bytes(b'\xff\xff\x02\x00')
        with self.assertRaisesRegex(ValueError,'hash'):validate_triplet(a,tr,wl)
        # A valid internal writer hash does not conceal an upstream loss.
        missing=self.make('missing','received',[b'\x01\x00',b''])
        with self.assertRaisesRegex(ValueError,'mismatch'):validate_triplet(a,tr,missing)

    def test_frame_jump_even_when_audio_hashes_match_rejected(self):
        a,tr,wl=self.triplet();events=(a/'events.jsonl').read_text();events=events.replace('"frame": 3','"frame": 4');(a/'events.jsonl').write_text(events)
        with self.assertRaisesRegex(ValueError,'discontinuity'):validate_triplet(a,tr,wl)

    def test_writer_ack_after_disk_and_limit_failure(self):
        w=EvidenceWriter(self.root/'ack');self.assertTrue(w.submit([{'kind':'test'}],17));w.close()
        self.assertEqual(w.acks.get_nowait(),17);self.assertTrue((w.path/'events.jsonl').read_text())
        w=EvidenceWriter(self.root/'limit');self.assertFalse(w.submit([{'kind':'test','text':'x'*262144}]))
        w.close();self.assertEqual(json.loads((w.path/'writer.json').read_text())['failed'],'evidence_size_limit')

    def test_full_synthetic_analysis_exports_same_pcm_without_clinical_wer(self):
        a,tr,wl=self.triplet();capture=a.parent/'synthetic';capture.mkdir();a.rename(capture/'browser');a=capture/'browser'
        sid='lab';config={'type':'config','session_id':sid,'direction':{'source_language':'en'},
            'capabilities':dict.fromkeys(['operator_console','operator_recovery','session_direction','captions_clear'],1),
            'wlk':{'session_language_isolation':1,'session_language':'en','mode':'full','useAudioWorklet':True}}
        records=list(map(json.loads,(a/'events.jsonl').read_text().splitlines()))
        for i,row in enumerate(records):row.update(ms=i,page='capture')
        for i,message in enumerate([config,{'type':'asr','session_id':sid,'payload':{'lines':[{'speaker':1,'text':'No edema.'}]},
                    'segmentation':{'ready_segments':[{'id':'s1','text':'No edema.'}]}},
                    {'type':'status','state':'stopped','session_id':sid,'completion':'complete'}]):
            records.append({'kind':'browser_frame','ms':100+i,'page':'capture','message':message})
        records.append({'kind':'terminal_observed','outcome':'complete','ms':105,'page':'operator'})
        (a/'events.jsonl').write_text('\n'.join(json.dumps(r) for r in records)+'\n')
        (capture/'completion.json').write_text(json.dumps({'owner':{'owns_session':True,'session_open':False,'outcome':'complete'}}))
        result=json.loads(analyze(capture,tr,wl).read_text())
        self.assertIsNone(result['clinical_wer']);self.assertEqual(result['text']['raw_vs_ready']['wer'],0)
        import wave
        with wave.open(str(capture/'sent_pcm.wav'),'rb') as f:self.assertEqual(f.readframes(999),b'\x01\x00\x02\x00')
        with wave.open(str(capture/'pre_listening_s16.wav'),'rb') as f:self.assertEqual(f.getnframes(),6)

    def test_auth_projection_and_raw_wlk_snapshots(self):
        p=projection({'type':'asr','payload':{'lines':[{'text':'No edema; 5 mg.'}], 'access_token':'private'},'control_token':'private','headers':{'Authorization':'private'}})
        self.assertNotIn('private',json.dumps(p));self.assertEqual(p['payload']['lines'][0]['text'],'No edema; 5 mg.')
        self.assertIn('lines',projection({'lines':[{'text':'RAW'}],'buffer_transcription':'partial'}))

    def test_serve_requires_fresh_authorization_before_accessing_plan(self):
        from trad_lab.m4b.server import serve
        with self.assertRaisesRegex(ValueError,'authorization'):serve('wlk','missing-plan','M3 authorized')

    def test_oom_observer_stops_only_current_attempt_without_sensitive_log(self):
        import logging
        from trad_lab.m4b.watchdog import StopOnOOM
        handler=StopOnOOM(self.root)
        handler.emit(logging.LogRecord('test',logging.ERROR,'',0,'ordinary error PRIVATE',(),None))
        self.assertFalse((self.root/'CUDA_OOM.json').exists())
        with self.assertRaises(SystemExit):handler.emit(logging.LogRecord('test',logging.ERROR,'',0,'CUDA out of memory PRIVATE',(),None))
        status=json.loads((self.root/'CUDA_OOM.json').read_text());self.assertEqual(status['status'],'blocked')
        self.assertNotIn('PRIVATE',json.dumps(status))

    def test_transparent_asgi_accept_binary_eof_and_denial(self):
        async def scenario(accept):
            original=[{'type':'websocket.receive','bytes':b'\x01\x00'}, {'type':'websocket.receive','bytes':b''}]
            received=[];sent=[]
            async def receive():return original.pop(0)
            async def send(m):sent.append(m)
            async def app(scope,receive,send):
                await send({'type':'websocket.accept' if accept else 'websocket.close'})
                if accept:
                    received.append(await receive());received.append(await receive())
                    await send({'type':'websocket.send','text':json.dumps({'lines':[{'text':'No edema.'}],'buffer_transcription':'5 mg'})})
            tap=WireTap(app,self.root/('accepted' if accept else 'denied'),'/asr')
            await tap({'type':'websocket','path':'/asr','headers':[(b'authorization',b'PRIVATE')]},receive,send)
            if accept:
                self.assertEqual([r['bytes'] for r in received],[b'\x01\x00',b''])
                stream,_=verify_stream(self.root/'accepted/wire_01','received');self.assertEqual(stream['bytes'],2)
            self.assertNotIn('PRIVATE',(tap.root/'wire_01/events.jsonl').read_text())
        asyncio.run(scenario(True));asyncio.run(scenario(False))


class ClockLatencyTests(unittest.TestCase):
    def test_cross_page_offsets_and_missing_clock_never_invent_latency(self):
        calibration=lambda page,now,py:{'kind':'clock_bracket','py_before_ns':int((py-1)*1e6),'py_after_ns':int((py+1)*1e6),'page_clock':{'now':now,'state':{'page':page}}}
        e=[calibration('capture',100,1100),calibration('operator',500,1100)]
        pre=[{'kind':'pre','page':'capture','ms':200}];sent=[{'bytes':3200}]
        e += [{'kind':'ready','page':'capture','ms':400,'segment':{'id':'S1','text':'No edema.','reason':'sentence','end_time':.1}},
              {'kind':'overlay_dom','page':'operator','ms':850,'segment_id':'S1'},
              {'kind':'binary_eof','page':'capture','ms':500}, {'kind':'terminal_observed','page':'operator','ms':1000}]
        result=latency(e,pre,sent)
        self.assertEqual(result['summary']['ready_received']['median_ms'],200)
        self.assertEqual(result['summary']['diagnostic_overlay_dom']['median_ms'],250)
        self.assertEqual(result['flush_drain']['ms'],100)
        self.assertEqual(result['segments'][0]['uncertainty_ms']['diagnostic_overlay_dom'],2)
        no_clock=latency([r for r in e if r['kind']!='clock_bracket'],pre,sent)
        self.assertEqual(no_clock['summary'],{})
        self.assertIsNone(mapped({'page':'unknown','ms':1},clock_models(e)))

    def test_outside_audio_timestamps_stay_unavailable(self):
        result=latency([{'kind':'ready','page':'p','ms':1,'segment':{'id':'s','text':'x','reason':'eof','end_time':500}}],[{}],[{'bytes':2}])
        self.assertIn('outside',result['segments'][0]['unavailable']);self.assertEqual(result['summary'],{})


if __name__=='__main__':unittest.main()
