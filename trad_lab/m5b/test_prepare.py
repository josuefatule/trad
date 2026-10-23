import json
from pathlib import Path
import tempfile
import unittest
from trad_lab.audio import digest
from .prepare import verify


class FreezeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir='C:/live-captions/logs/trad_lab')
        self.root=Path(self.temp.name).resolve()
        assert self.root.is_relative_to(Path('C:/live-captions/logs/trad_lab').resolve())
        self.copy=self.root/'copy';self.copy.mkdir();self.source=self.copy/'safe.py';self.source.write_text('initial\n')
        self.plan=self.root/'plan.json'
        self.data={'copy':str(self.copy),'backend_port':18000,'trad_port':18010,'deepl_enabled':False,
                   'microphone_enabled':False,'manifest':{'safe.py':digest(self.source)}}
        self.save()
    def save(self):self.plan.write_text(json.dumps(self.data))
    def tearDown(self):self.temp.cleanup()
    def test_changed_source_rejected_without_restoring_or_overwriting(self):
        verify(self.plan);self.source.write_text('concurrent\n')
        with self.assertRaises(ValueError):verify(self.plan)
        self.assertEqual(self.source.read_text(),'concurrent\n')
    def test_extra_env_or_executable_rejected(self):
        (self.copy/'.env').write_text('unapproved')
        with self.assertRaises(ValueError):verify(self.plan)
    def test_live_port_or_translation_rejected(self):
        for key,value in [('trad_port',8010),('deepl_enabled',True),('microphone_enabled',True)]:
            original=self.data[key];self.data[key]=value;self.save()
            with self.assertRaises(ValueError):verify(self.plan)
            self.data[key]=original
    def test_private_runtime_and_bytecode_are_not_source_overrides(self):
        for name in ('.runtime/local.txt','__pycache__/safe.pyc'):
            p=self.copy/name;p.parent.mkdir();p.write_bytes(b'test')
        verify(self.plan)

    def test_b2_credit_configuration_cannot_be_silently_changed(self):
        self.data.update(phase='M5-B2',transport_flow={'protocol':'pcm_credit_v1','pcm_frame_bytes':64000,
            'inflight_frames':1,'default_pacing':'realtime','credit_wait_seconds':37.,'file_credit_seconds':39.})
        self.save();verify(self.plan)
        self.data['transport_flow']['inflight_frames']=2;self.save()
        with self.assertRaisesRegex(ValueError,'flow configuration'):verify(self.plan)


if __name__=='__main__':unittest.main()
