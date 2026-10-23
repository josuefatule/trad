from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app.service_host import asr_arguments


class ASRMemoryTests(unittest.TestCase):
    def test_bounded_profile_keeps_small_backend_pcm_language_adapter_and_limits_context(self):
        args=asr_arguments('bounded')
        for name,value in [('--model','small'),('--backend','faster-whisper'),('--host','localhost'),
                           ('--port','8000'),('--audio-max-len','10'),('--max-context-tokens','96')]:
            self.assertEqual(value,args[args.index(name)+1])
        self.assertIn('--pcm-input',args)

    def test_legacy_profile_restores_previous_exact_arguments(self):
        self.assertEqual(['wlk_server','--backend','faster-whisper','--model','small','--lan','en',
                          '--pcm-input','--host','localhost','--port','8000'],asr_arguments('legacy'))

    def test_profile_environment_and_invalid_input(self):
        with patch.dict('os.environ',{'TRAD_ASR_MEMORY_PROFILE':'legacy'}):
            self.assertNotIn('--max-context-tokens',asr_arguments())
        with self.assertRaises(ValueError):asr_arguments('unknown')
