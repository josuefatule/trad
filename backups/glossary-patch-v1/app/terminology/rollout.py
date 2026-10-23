"""Pinned, reversible glossary release for operator-controlled MVP trials."""
from collections import Counter
from dataclasses import asdict,dataclass,field
from functools import lru_cache
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import tempfile
import time

from app.captions.terminology_normalizer import NormalizedSegment,Correction,Suggestion
from .guarded_matcher import candidate
from .streaming_policy import POLICY_VERSION, pressure_split_corrections

ROOT=Path(__file__).resolve().parents[2]
MODES={'off','shadow','soft'}
LOGGER=logging.getLogger('captions')


@dataclass(frozen=True)
class GlossaryConfig:
    mode:str='soft'
    release_path:str=str(ROOT/'glossaries/releases/medical-657-v1')
    state_path:str=str(ROOT/'.runtime/glossary-rollout.json')

    def __post_init__(self):
        if self.mode not in MODES:raise ValueError('Invalid glossary mode')

    @classmethod
    def from_env(cls):
        return cls(mode=os.getenv('TRAD_GLOSSARY_MODE','soft'),
            release_path=os.getenv('TRAD_GLOSSARY_RELEASE',cls.release_path),
            state_path=os.getenv('TRAD_GLOSSARY_STATE',cls.state_path))


def literal_pattern(text):
    body=re.escape(text)
    body=body.replace(r'\ ',r'\s+')
    return re.compile(r"(?<![\w'’])"+body+r"(?![\w'’])",re.I)


class MedicalRelease:
    def __init__(self,directory):
        folder=Path(directory).resolve();manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
        if manifest.get('policy')!='soft_testing':raise ValueError('Not a soft-testing release')
        files=manifest.get('files',[])
        if len(files)!=1 or files[0].get('name')!='bundle.json':raise ValueError('Invalid release members')
        payload=(folder/'bundle.json').read_bytes()
        if len(payload)>4_000_000 or len(payload)!=files[0]['bytes'] or hashlib.sha256(payload).hexdigest()!=files[0]['sha256']:
            raise ValueError('Release integrity mismatch')
        bundle=json.loads(payload)
        self.version=manifest['version']
        if bundle.get('version')!=self.version:raise ValueError('Release version mismatch')
        self.concepts=tuple(bundle['concepts']);self.forms=tuple(bundle['preservation_forms'])
        if len(self.concepts)!=657 or len({c['id'] for c in self.concepts})!=657:raise ValueError('Incomplete glossary release')
        for c in self.concepts:
            if not all(isinstance(c.get(k),str) and 0<len(c[k])<=512 for k in ['id','en','es']):raise ValueError('Invalid bilingual concept')
            threshold=c.get('fuzzy_threshold_en')
            if threshold is not None and (not c['asr_evaluated'] or not .90<=threshold<=1):raise ValueError('Unapproved fuzzy policy')
        self.evaluated=tuple(dict(concept_id=c['id'],canonical_en=c['en']) for c in self.concepts if c['asr_evaluated'])
        self.thresholds={c['id']:c['fuzzy_threshold_en'] for c in self.concepts if c['asr_evaluated']}
        if len(self.evaluated)!=97 or sum(v is not None for v in self.thresholds.values())!=80:raise ValueError('Unexpected evaluated policy')
        self.variants=tuple(f for f in self.forms if f['language']=='en' and f['bucket']=='reviewable_variant')
        self.patterns={lang:tuple((c,literal_pattern(c[lang])) for c in self.concepts) for lang in ['en','es']}

    def matches(self,text,language):
        if language not in self.patterns:return []
        hits=[]
        for c,pattern in self.patterns[language]:
            for m in pattern.finditer(text):
                # Do not extract a positive term from an attached negative prefix.
                if re.search(r'(?:non|un|in)[-‐‑–—]$',text[max(0,m.start()-5):m.start()],re.I):continue
                hits.append(dict(concept=c,start=m.start(),end=m.end()))
        return hits

    def translation_context(self,text,source,target):
        if {source,target}!={'en','es'}:return ''
        hits=sorted(self.matches(text,source),key=lambda h:(-(h['end']-h['start']),h['start']))
        selected=[];used=set()
        for h in hits:
            c=h['concept']
            if c['id'] in used or c['context_required']:continue
            if any(h['start']<p['end'] and h['end']>p['start'] for p in selected):continue
            # Duplicate target surfaces require contextual review, not a choice.
            if sum(other[source].casefold()==c[source].casefold() for other in self.concepts)!=1:continue
            selected.append(h);used.add(c['id'])
            if len(selected)==12:break
        lines=[f"{h['concept'][source]} = {h['concept'][target]}" for h in sorted(selected,key=lambda h:h['start'])]
        if not lines:return ''
        return ('Medical terminology reference for this passage ('+source.upper()+' → '+target.upper()+'):\n'+'\n'.join(lines))[:1800]


@lru_cache(maxsize=4)
def load_release(directory):return MedicalRelease(directory)


class RolloutController:
    def __init__(self,config):
        self.config=config;self.mode=config.mode;self.generation=0;self.error=None
        path=Path(config.state_path) if config.state_path else None
        if path and path.is_file():
            try:
                saved=json.loads(path.read_text(encoding='utf-8'))
                if saved['mode'] not in MODES or type(saved['generation']) is not int:raise ValueError('Invalid saved state')
                self.mode=saved['mode'];self.generation=max(0,saved['generation'])
            except (OSError,ValueError,KeyError,TypeError):self.mode='off';self.error='El estado guardado es inválido; se usa el modo anterior.'
        # Explicit environment switch is the emergency override after restart.
        self.forced=os.getenv('TRAD_GLOSSARY_MODE') is not None
        if self.forced:self.mode=config.mode

    def release(self):
        try:
            result=load_release(self.config.release_path);self.error=None;return result
        except (OSError,ValueError,KeyError,TypeError):
            self.error='No se pudo validar el paquete; se usa el modo anterior.'
            LOGGER.warning('glossary_release_unavailable fallback=legacy')
            return None

    def status(self):
        package=self.release() if self.mode!='off' else None
        return dict(mode=self.mode,effective_mode=self.mode if package else 'off',generation=self.generation,
            policy_version=POLICY_VERSION if package else None,
            version=package.version if package else None,concepts=len(package.concepts) if package else 0,
            evaluated_english=97 if package else 0,fuzzy_english=80 if package else 0,
            exact_only_english=577 if package else 0,error=self.error,forced_by_environment=self.forced)

    def change(self,mode,generation):
        if self.forced:raise ValueError('Mode is fixed by TRAD_GLOSSARY_MODE')
        if not isinstance(mode,str) or mode not in MODES or type(generation) is not int:raise ValueError('Invalid glossary mode/revision')
        if generation!=self.generation:raise RuntimeError('Glossary configuration changed; refresh')
        if mode!='off' and self.release() is None:raise ValueError('Glossary release unavailable')
        next_generation=self.generation+1
        if self.config.state_path:
            path=Path(self.config.state_path);path.parent.mkdir(parents=True,exist_ok=True)
            temporary=None
            try:
                with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,delete=False,suffix='.tmp') as stream:
                    temporary=Path(stream.name);json.dump(dict(mode=mode,generation=next_generation),stream)
                    stream.flush();os.fsync(stream.fileno())
                os.replace(temporary,path)
            finally:
                if temporary and temporary.exists():temporary.unlink()
        self.mode=mode;self.generation=next_generation;self.error=None
        return self.status()


@dataclass(frozen=True)
class GlossarySegment(NormalizedSegment):
    glossary:dict=field(default_factory=dict)


class SoftNormalizer:
    def __init__(self,release,mode,language,legacy):
        self.release=release;self.mode=mode;self.language=language;self.legacy=legacy

    def translation_context(self,text,source,target):
        return self.release.translation_context(text,source,target) if self.mode=='soft' else ''

    def normalize(self,segment_id,text):
        started=time.perf_counter_ns();known=self.release.matches(text,self.language)
        original=self.legacy.normalize(segment_id,text) if self.language=='es' or self.mode=='shadow' else None
        changes=[];suggestions=[];blocked={}
        if self.language=='en':
            joins=pressure_split_corrections(text)
            if self.mode=='soft':changes.extend(joins)
            else:
                suggestions.extend(Suggestion(c.source,c.replacement,c.start,c.end,'soft_glossary_shadow',c.confidence) for c in joins)
            result=candidate(text,self.release.evaluated,self.release.thresholds,self.release.variants)
            # A complete canonical phrase from the 657-term catalog is immutable.
            # Short exact subphrases may still support a longer guarded repair.
            for c in result['changes']:
                if c['rule']!='glossary_fuzzy':continue
                if any(c['start']<j.end and c['end']>j.start for j in joins):continue
                if any(h['start']<=c['start'] and h['end']>=c['end'] for h in known):continue
                if self.mode=='soft':changes.append(Correction(**c))
                else:suggestions.append(Suggestion(c['source'],c['replacement'],c['start'],c['end'],'soft_glossary_shadow',c['confidence']))
            blocked=dict(Counter(reason for b in result['blocked'] for reason in b['reasons']))
        output=original.normalized_text if original else text
        if self.language=='en' and self.mode=='soft':
            changes.sort(key=lambda c:c.start)
            for c in reversed(changes):output=output[:c.start]+c.replacement+output[c.end:]
        if original:
            changes=list(original.corrections);suggestions=list(original.suggestions)+suggestions
        if output!=text:known+=self.release.matches(output,self.language)
        return GlossarySegment(str(segment_id),text,output,tuple(changes),tuple(suggestions),
            tuple(dict.fromkeys(h['concept']['en' if self.language=='en' else 'es'] for h in known)),
            (time.perf_counter_ns()-started)/1_000_000,
            dict(mode=self.mode,version=self.release.version,policy_version=POLICY_VERSION,concept_ids=list(dict.fromkeys(h['concept']['id'] for h in known)),
                 blocked_counts=blocked,applied=len(changes),translation_context_enabled=self.mode=='soft'))


def session_normalizer(config,language,legacy):
    if config.mode=='off':return legacy
    try:release=load_release(config.release_path)
    except (OSError,ValueError,KeyError,TypeError):
        LOGGER.warning('glossary_session_fallback mode=legacy');return legacy
    return SoftNormalizer(release,config.mode,language,legacy)
