"""Copy-only mock translation and owner-controlled presentation hold."""
import asyncio
from pathlib import Path
from app.translation.engine import TranslationStatus


def configure_environment():
    import os
    from trad_lab.m5b.runtime import configure_environment as base
    base()
    os.environ.update(TRANSLATION_ENABLED='1', TRANSLATION_PROVIDER='mock',
                      TRANSLATION_SOURCE_LANGUAGE='en', TRANSLATION_TARGET_LANGUAGE='es')
    # Never inherit a physical or real-provider enable switch in C1.
    os.environ.pop('M5C_PHYSICAL_ENABLED', None)


class SimulationProvider:
    """Explicit simulation marker accepted by the unchanged presentation layer.

    Standard provider='mock' remains filtered by Hub/renderer. This dedicated lab
    provider is never labelled DeepL and produces no Spanish medical translation.
    """
    name='m5c-simulation'
    def __init__(self, delay=0., fail_ids=()):
        self.requests=[]; self.delay=delay; self.fail_ids=set(fail_ids)
    async def translate(self, request):
        if (request.source_language, request.target_language)!=('en','es'):
            raise ValueError('M5-C requires EN→ES')
        if len(self.requests)>=4096:raise ValueError('C1 simulation request budget exhausted')
        self.requests.append(request)
        if self.delay: await asyncio.sleep(self.delay)
        if request.segment_id in self.fail_ids: raise RuntimeError('simulation_provider_error')
        return '[SIMULACIÓN ES — NO CLÍNICA] '+request.normalized_text


def provider_from_config(config):
    if not config.enabled or config.provider!='mock' or config.deepl_auth_key:
        raise RuntimeError('C1 only permits the credential-free simulation provider')
    return SimulationProvider(), TranslationStatus('ready', 'm5c-simulation', 'SIMULACIÓN; no DeepL ni traducción médica')


def install(app):
    from fastapi import HTTPException, Request
    from fastapi.responses import FileResponse
    import app.main as main
    import app.translation.engine as engine
    from app.operator_control import local_request
    engine.provider_from_config=provider_from_config
    hub=app.state.caption_hub
    hub._m5c_hidden=False
    authority=app.state.operator_authority

    @app.get('/m5c/physical-capture')
    async def capture(): return FileResponse(main.ROOT/'templates/m5c_capture.html')

    @app.get('/m5c/capabilities')
    async def capabilities():
        return {'phase':'M5-C1','physical_enabled':False,'real_deepl_enabled':False,
                'direction':'en-es','resampler':'fir127-candidate','credit':'pcm_credit_v1'}

    @app.post('/api/m5c/presentation')
    async def presentation(request: Request):
        token=request.headers.get('x-operator-token')
        def authorized():return local_request(request,require_origin=True) and authority.valid(token) and authority.owner==token
        if not authorized():raise HTTPException(403,'Current owner required')
        body=await request.json()
        if not authorized():raise HTTPException(403,'Owner changed')
        if (not isinstance(body,dict) or body.get('session_id')!=hub.session_id or
            type(body.get('hidden')) is not bool or hub.state!='live' or
            body.get('visual_generation')!=hub.visual_generation):
            raise HTTPException(409,'Stale presentation control or non-live state')
        # Atomically clear before future publications. ASR/translation journal stays.
        hub._m5c_hidden=body['hidden']
        hub.clear_captions(hub.session_id,hub.visual_generation)
        return {'hidden':hub._m5c_hidden,'session_id':hub.session_id,
                'visual_generation':hub.visual_generation,'replay_hidden_captions':False}

    @app.get('/api/m5c/presentation')
    async def presentation_status(request: Request):
        token=request.headers.get('x-operator-token')
        if not local_request(request) or not authority.valid(token):raise HTTPException(403,'Operator authorization required')
        return {'hidden':hub._m5c_hidden,'session_id':hub.session_id}

