"""Freeze an isolated executable copy without secrets or starting services."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess


def digest(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda: f.read(1048576), b''): h.update(b)
    return h.hexdigest()


def private_path(p):
    p = Path(p).resolve()
    allowed = Path(__file__).resolve().parents[2]/'logs'/'trad_lab'
    if not p.is_relative_to(allowed) or p == allowed: raise ValueError('Use a new private logs/trad_lab subdirectory')
    return p


def prepare(out):
    root = Path(__file__).resolve().parents[2]; out = private_path(out)
    out.mkdir(parents=True, exist_ok=False)
    copy = out/'copy'; copy.mkdir()
    manifest = {}
    for folder in ('app', 'glossaries', 'trad_lab'):
        for p in (root/folder).rglob('*'):
            if not p.is_file() or '__pycache__' in p.parts: continue
            if p.suffix not in {'.py', '.js', '.cjs', '.css', '.html', '.json', '.md'}: continue
            relative = p.relative_to(root); dest = copy/relative
            dest.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(p,dest)
            manifest[relative.as_posix()] = digest(p)
    # Preserve only nonsecret audio/segmentation/reliability environment settings.
    # The .env file itself and all credentials are excluded from the copy.
    selected = {}
    for line in (root/'.env').read_text(encoding='utf-8-sig').splitlines():
        m = re.fullmatch(r'\s*(?:export\s+)?([A-Z_0-9]+)\s*=\s*(.*?)\s*',line)
        if not m: continue
        key, value = m.groups()
        if (key.startswith(('SEGMENT_', 'RELIABILITY_', 'OPERATOR_', 'CAPTION_')) or key in {
            'NORMALIZER_AUTO_THRESHOLD','NORMALIZER_SUGGEST_THRESHOLD','NORMALIZER_MAX_TOKEN_DELTA',
            'NORMALIZER_CONTEXT_WORDS','NORMALIZER_COLLAPSED_MIN_CHARACTERS','NORMALIZER_COLLAPSED_MAX_EDITS',
            'CAPTIONS_CONNECT_TIMEOUT', 'CAPTIONS_STOP_TIMEOUT'}):
            value=value.split(' #',1)[0].strip().strip('\'"')
            if key in {'CAPTION_MODE','CAPTION_POSITION'}:
                if value not in {'persistent_rolling','timed_queue','top','center','bottom'}:raise ValueError('Unexpected enum: '+key)
            elif not re.fullmatch(r'[\d.\s+-]+',value): raise ValueError('Non-numeric setting requires review: '+key)
            selected[key] = value
    selected.update(TRANSLATION_ENABLED='0', WLK_WS_URL='ws://127.0.0.1:18000/asr',
                    CAPTIONS_LOG_RAW='0', CAPTIONS_LANGUAGE='en',
                    CAPTIONS_LOG_DIR=str(out/'server_logs'))
    (copy/'.env').write_text('\n'.join(f'{k}="{v}"' for k,v in sorted(selected.items()))+'\n',encoding='utf-8')
    # Add only metadata, ahead of the original sample message. A preinstalled
    # listener consumes metadata before the unchanged CAPTURE handler sees it.
    worklet = copy/'app/static/pcm_worklet.js'
    text = worklet.read_text(encoding='utf-8')
    anchor = '      const channelData = input[0];'
    if text.count(anchor) != 1: raise ValueError('Worklet source changed; re-audit required')
    text = text.replace(anchor, '      this.port.postMessage({m4b: true, frame: currentFrame, rate: sampleRate, channels: input.length});\n'+anchor)
    worklet.write_text(text, encoding='utf-8')
    (out/'plan.json').write_text(json.dumps({'copy':str(copy),'original_sources':manifest,
        'modified_copy_only':{'app/static/pcm_worklet.js':digest(worklet)},'config':selected,
        'reference':{'path':'C:/TRAD-LAB/corpus/cardio_01/audio.mp3',
                     'sha256':digest('C:/TRAD-LAB/corpus/cardio_01/audio.mp3'),
                     'start_s':0,'duration_s':100,'wer_reference':'pending exact boundary review'},
        'physical_sessions_max':3,'authorization':'PENDING M4-B explicit authorization',
        'credentials_copied':False,'services_started':False},indent=2),encoding='utf-8')
    return out
