"""Keep the B provider and ASR; select the existing paginated presentation mode."""
import os


def configure_environment():
    from trad_lab.m5c2b.runtime import configure_environment as base
    base()
    os.environ['CAPTION_MODE'] = 'timed_queue'


from trad_lab.m5c2b.runtime import provider_from_config


def install(app):
    from trad_lab.m5c2b.runtime import install as base
    base(app)
    app.router.routes[:] = [r for r in app.router.routes if getattr(r, 'path', None) != '/m5c/capabilities']

    @app.get('/m5c/capabilities')
    async def capabilities():
        return {'phase': 'M5-C2-B-R1', 'physical_enabled': True, 'real_deepl_enabled': True,
                'translation_enabled': True, 'direction': 'en-es', 'resampler': 'fir127-candidate',
                'credit': 'pcm_credit_v1', 'evidence': 'incremental_owner_upload_v1',
                'caption_mode': 'timed_queue', 'max_provider_calls': 128, 'max_provider_characters': 20000}
