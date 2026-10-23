"""Opt-in isolated WLK server with actual decoder evidence, never production.

Requires explicit user authorization before launch. No package/file patches.
Use loopback port 18000, small and the same flags as app.asr.wlk_server.
"""
from contextvars import ContextVar
import json

from app.asr.wlk_server import isolated_factory, LanguageHandshake

EVIDENCE=ContextVar('trad_lab_decoder_evidence',default=None)


class DecoderEvidence:
    def __init__(self,app):self.app=app
    async def __call__(self,scope,receive,send):
        token=EVIDENCE.set(None)
        async def annotated(message):
            if scope['type']=='websocket' and message['type']=='websocket.send' and message.get('text'):
                payload=json.loads(message['text'])
                if payload.get('type')=='config':
                    payload['lab_decoder_evidence']=EVIDENCE.get()
                    message={**message,'text':json.dumps(payload)}
            await send(message)
        try:await self.app(scope,receive,annotated)
        finally:EVIDENCE.reset(token)


def main():
    from importlib.metadata import version
    if version('whisperlivekit')!='0.2.26':raise RuntimeError('Re-audit required for this WLK version')
    from whisperlivekit import core,audio_processor,basic_server
    cfg=basic_server.config
    if cfg.host not in {'localhost','127.0.0.1'} or cfg.port!=18000:
        raise ValueError('Lab probe server is restricted to loopback port 18000')
    if cfg.model_size!='small' or cfg.backend!='faster-whisper' or cfg.backend_policy!='simulstreaming':
        raise ValueError('Lab streaming probe requires unchanged small/faster-whisper/simulstreaming')
    base=isolated_factory(core.online_factory)
    def factory(args,asr,language=None):
        processor=base(args,asr,language)
        decoder=processor.model
        encoder=getattr(processor.asr,'fw_encoder',None)
        parameter=next(processor.asr.shared_model.parameters())
        EVIDENCE.set({'requested_language':language,'cfg_language':decoder.cfg.language,
            'tokenizer_language':decoder.tokenizer.language,'decode_options_language':decoder.decode_options.language,
            'model_name':processor.asr.model_name,'backend_policy':args.backend_policy,
            'encoder_compute_type':getattr(getattr(encoder,'model',None),'compute_type',None),
            'decoder_dtype':str(parameter.dtype),'decoder_device':str(parameter.device),
            'beam_size':decoder.cfg.beam_size,'decoder_type':decoder.cfg.decoder_type,
            'scope':'actual constructed decoder configuration; no transcript/credentials'})
        return processor
    core.online_factory=audio_processor.online_factory=factory
    basic_server.app.add_middleware(LanguageHandshake)
    basic_server.app.add_middleware(DecoderEvidence)
    basic_server.main()


if __name__=='__main__':main()
