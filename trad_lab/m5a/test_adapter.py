import hashlib
from types import SimpleNamespace
import unittest
import numpy as np
from app.overlay.hub import CaptionHub
from trad_lab.m4c.incremental import Word
from .adapter import TurboAdapter, PROFILE
from .consumer import TradConsumer, compact


class AdapterTests(unittest.TestCase):
    def make(self, hypotheses=None, session='a', consumer=None):
        events=[];raw=[];calls=[]
        hypotheses=hypotheses or [[]]
        def decode(audio,start):
            calls.append((start,hashlib.sha256(audio.tobytes()).hexdigest(),len(audio)))
            return hypotheses[min(len(calls)-1,len(hypotheses)-1)]
        def emit(payload):
            events.append(payload)
            if consumer:
                at=raw[-1].get('serial_completion_s',consumer.now) if raw else 0.
                consumer.receive(payload,at)
        a=TurboAdapter(session,decode,emit,raw_sink=raw.append,backend='turbo-experimental')
        return a,events,raw,calls

    def feed(self,a,raw,sizes=(64000,)):
        offset=0;i=0
        while offset<len(raw):
            size=sizes[i%len(sizes)];block=raw[offset:offset+size]
            a.push(a.session_id,a.sequence,block);offset+=len(block);i+=1

    def test_explicit_lab_selection_and_format(self):
        with self.assertRaises(ValueError):TurboAdapter('a',None,None)
        for opts in ({'language':'es'},{'sample_rate':48000},{'channels':2},{'backend':'live'}):
            with self.assertRaises(ValueError):
                TurboAdapter('a',None,None,**{'backend':'turbo-experimental',**opts})
        self.assertEqual((PROFILE.agreement,PROFILE.minimum_age_s,PROFILE.update_s,PROFILE.window_s,PROFILE.max_buffer_s),(2,1,2,15,30))

    def test_pcm_partitions_do_not_change_windows_or_samples(self):
        pcm=np.arange(112321,dtype='int16').tobytes();results=[]
        for sizes in [(64000,),(86,),(2,4096,64000,128)]:
            a,events,raw,calls=self.make();a.start();self.feed(a,pcm,sizes)
            a.push('a',a.sequence,b'')
            results.append(calls)
            self.assertEqual(a.pcm_sha.hexdigest(),hashlib.sha256(pcm).hexdigest())
            self.assertEqual(a.received_bytes,len(pcm))
            self.assertEqual(events[0]['mode'],'full')
            self.assertTrue(events[0]['useAudioWorklet'])
            self.assertEqual(events[-1]['type'],'ready_to_stop')
            self.assertEqual(events[-1]['session_language'] if 'session_language' in events[-1] else events[0]['session_language'],'en')
        self.assertEqual(results[0],results[1]);self.assertEqual(results[1],results[2])

    def test_eof_does_not_create_second_vote_or_ready(self):
        c=TradConsumer('a');a,events,raw,calls=self.make([[Word(' aldosterone',0,.5)]],consumer=c)
        a.start();self.feed(a,b'\0'*64000);a.request_stop('a');a.push('a',1,b'')
        self.assertEqual(len(calls),1)
        self.assertEqual(a.tail[0]['text'],' aldosterone')
        self.assertEqual(c.state.confirmed_text,'');self.assertEqual(c.ready,[])
        self.assertEqual(c.state.partial_text,' aldosterone')
        self.assertTrue(c.closed)

    def test_real_new_eof_samples_may_supply_legitimate_vote(self):
        a,events,raw,calls=self.make([[Word(' 140 over 19',0,.5)]])
        a.start();self.feed(a,b'\0'*64002);a.request_stop('a');a.push('a',a.sequence,b'')
        self.assertEqual(len(calls),2)
        self.assertEqual(events[-2]['lines'][0]['text'],' 140 over 19')
        self.assertEqual(events[-1]['unconfirmed_eof_tail'],[])

    def test_sequence_odd_frame_and_oversize_abort_without_terminal(self):
        for seq,pcm in [(1,b'00'),(0,b'0'),(0,b'0'*64002),(False,b'00')]:
            a,events,_,_=self.make();a.start()
            with self.assertRaises(ValueError):a.push('a',seq,pcm)
            self.assertEqual(a.state,'failed')
            self.assertFalse(any(e.get('type')=='ready_to_stop' for e in events))
            with self.assertRaises(RuntimeError):a.push('a',0,b'')

    def test_start_stop_eof_and_no_reuse(self):
        a,events,_,calls=self.make()
        with self.assertRaises(RuntimeError):a.push('a',0,b'00')
        a.start()
        with self.assertRaises(RuntimeError):a.start()
        a.request_stop('a');a.push('a',0,b'00');a.push('a',1,b'')
        self.assertEqual(a.state,'stopped');self.assertEqual(len(calls),1)
        for pcm in (b'',b'00'):
            with self.assertRaises(RuntimeError):a.push('a',2,pcm)
        self.assertEqual(sum(e.get('type')=='ready_to_stop' for e in events),1)

    def test_foreign_session_and_independent_state(self):
        a,ae,_,_=self.make([[Word(' first',0,.5)]],session='a')
        b,be,_,_=self.make([[Word(' second',0,.5)]],session='b')
        a.start();b.start()
        with self.assertRaises(ValueError):a.push('b',0,b'00')
        with self.assertRaises(ValueError):a.request_stop('b')
        for x in (a,b):self.feed(x,b'\0'*128000);x.push(x.session_id,x.sequence,b'')
        self.assertEqual(a.lines[0]['text'],' first');self.assertEqual(b.lines[0]['text'],' second')
        self.assertTrue(all(e['session_id']=='a' for e in ae));self.assertTrue(all(e['session_id']=='b' for e in be))

    def test_provisional_revision_not_committed_and_signs_preserved(self):
        bad=[Word(' treated',0,.3)]
        good=[Word(' untreated',0,.3),Word(' stage',.3,.5),Word(' two',.5,.7),Word(' hypertension.',.7,1)]
        c=TradConsumer('a');a,events,_,_=self.make([bad,good,good],consumer=c)
        a.start();self.feed(a,b'\0'*192000);a.push('a',a.sequence,b'')
        self.assertEqual(c.state.confirmed_text,'untreated stage two hypertension.')
        self.assertEqual(' '.join(s.text for s in c.ready),'untreated stage two hypertension.')
        self.assertEqual(events[1]['lines'],[])
        self.assertEqual(events[1]['buffer_transcription'],' treated')

    def test_repeated_speech_is_not_deduplicated(self):
        words=[Word(' per',0,.2),Word(' per',.21,.4),Word(' day.',.4,.6)]
        c=TradConsumer('a');a,_,_,_=self.make([words],consumer=c)
        a.start();self.feed(a,b'\0'*128000);a.push('a',a.sequence,b'')
        self.assertEqual(compact(c.state.confirmed_text),'per per day.')
        self.assertEqual(compact(' '.join(s.text for s in c.ready)),'per per day.')

    def test_callback_cannot_mutate_internal_confirmed_words(self):
        a,events,raw,_=self.make([[Word(' -5 mg',0,.5)]])
        a.start();self.feed(a,b'\0'*128000)
        events[-1]['lines'][0]['text']='changed';raw[-1]['confirmed'][0]['text']='changed'
        self.assertEqual(a.lines[0]['text'],' -5 mg')
        self.assertEqual(a.engine.recent[0].text,' -5 mg')

    def test_visual_clear_uses_actual_hub_and_does_not_reset_asr(self):
        c=TradConsumer('a');a,_,_,_=self.make([[Word(' spironolactone.',0,.5)]],consumer=c)
        a.start();self.feed(a,b'\0'*128000)
        hub=CaptionHub(SimpleNamespace());hub.begin('a');hub.set_state('a','live')
        hub.caption_history.append({'private':'placeholder'});hub.sequence=3
        before=c.state.to_dict();commits=a.engine.committed_count
        self.assertTrue(c.visual_clear(hub))
        self.assertEqual(hub.visual_generation,1);self.assertFalse(hub.caption_history)
        self.assertEqual(c.state.to_dict(),before);self.assertEqual(a.engine.committed_count,commits)
        with self.assertRaises(ValueError):hub.clear_captions('a',0)
        a.push('a',a.sequence,b'')
        self.assertEqual(' '.join(s.text for s in c.ready),'spironolactone.')

    def test_decoder_error_is_incomplete_no_fallback(self):
        events=[]
        def broken(audio,start):raise RuntimeError('decoder failure')
        a=TurboAdapter('a',broken,events.append,backend='turbo-experimental');a.start()
        with self.assertRaises(RuntimeError):a.push('a',0,b'\0'*64000)
        self.assertEqual(a.state,'failed');self.assertEqual(events[-1]['type'],'error')
        self.assertFalse(any(e.get('type')=='ready_to_stop' for e in events))

    def test_consumer_rejects_foreign_reordered_and_changed_confirmed(self):
        c=TradConsumer('a')
        with self.assertRaises(ValueError):c.receive({'session_id':'b','adapter_sequence':0},0)
        with self.assertRaises(ValueError):c.receive({'session_id':'a','adapter_sequence':1},0)
        c.receive({'session_id':'a','adapter_sequence':0,'lines':[{'text':'140 over 19','start':0,'end':1}]},0)
        with self.assertRaises(RuntimeError):
            c.receive({'session_id':'a','adapter_sequence':1,'lines':[{'text':'140 over 90','start':0,'end':1}]},1)


if __name__=='__main__':unittest.main()
