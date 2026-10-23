import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
import wave
import numpy as np
from trad_lab.audio import digest
from trad_lab.m4c.incremental import Config
from trad_lab.m4c.replay import run_sample
from trad_lab.m4c.verify import verify_result


class ReplayTests(unittest.TestCase):
    def test_decoder_failure_is_preserved_and_never_retried(self):
        class Model:
            calls=0
            def transcribe(self,*args,**kwargs):
                self.calls+=1
                raise RuntimeError('Synthetic CUDA allocation failure')
        workspace=Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory(dir=workspace/'logs/trad_lab',prefix='m4c_test_') as tmp:
            assert Path(tmp).resolve().is_relative_to(workspace/'logs/trad_lab')
            root=Path(tmp);p=root/'pcm.s16le';p.write_bytes(bytes(32000))
            model=Model();sample={'path':str(p),'sha256':digest(p),'format':'s16le','id':'failure','reference':None}
            with self.assertRaisesRegex(RuntimeError,'Synthetic CUDA'):
                run_sample(model,sample,Config(window_s=5,update_s=1),root/'out',SimpleNamespace(check=lambda:None,unsafe=None))
            self.assertEqual(model.calls,1)
            self.assertTrue((root/'out/abort.json').is_file())

    def test_reader_feeds_exact_causal_pcm_without_reference_prompt(self):
        class Model:
            def transcribe(self,audio,**options):
                assert options['initial_prompt'] is None and options['hotwords'] is None
                return iter([]),SimpleNamespace(duration=len(audio)/16000,duration_after_vad=len(audio)/16000,language='en')
        workspace=Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory(dir=workspace/'logs/trad_lab',prefix='m4c_test_') as tmp:
            assert Path(tmp).resolve().is_relative_to(workspace/'logs/trad_lab')
            root=Path(tmp);p=root/'input.wav'
            raw=(np.arange(112000)%30000).astype('<i2').tobytes()
            with wave.open(str(p),'wb') as f:
                f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000);f.writeframes(raw)
            sample={'path':str(p),'sha256':digest(p),'format':'wav','id':'test','reference':None}
            run_sample(Model(),sample,Config(window_s=5,update_s=1),root/'out',SimpleNamespace(check=lambda:None))
            checked=verify_result(root/'out/result.json')
            self.assertEqual(checked['verified_windows'],7)
            self.assertEqual(checked['available_samples'],112000)
            self.assertEqual(checked['eofs'],1)
            trace=root/'out/events.jsonl'
            lines=trace.read_text().splitlines();event=json.loads(lines[0]);event['window_end_sample']+=16000
            lines[0]=json.dumps(event);trace.write_text('\n'.join(lines))
            with self.assertRaisesRegex(ValueError,'Noncausal'):verify_result(root/'out/result.json')


if __name__=='__main__':unittest.main()
