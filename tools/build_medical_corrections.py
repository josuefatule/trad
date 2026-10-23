"""Build an independent patch and full-catalog audit from preserved inputs."""
from collections import Counter
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path

from app.terminology.rollout import GlossaryConfig,load_release
from app.terminology.correction_patch import PATCH_VERSION,OBSERVED_REPAIR,REVIEW_ONLY,audit_catalog

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'glossaries/releases'/PATCH_VERSION
OUT=ROOT/'benchmarks/glossary_patch_v1'


def main():
    if DEST.exists():raise ValueError('Immutable correction patch already exists')
    release=load_release(GlossaryConfig.release_path)
    audit=audit_catalog(release.concepts,release.forms)
    reading=OUT/'second_reading.json'
    snapshot=json.loads(reading.read_text(encoding='utf-8'))
    texts=[s['raw_text'] for e in snapshot['operator_history']['events'] if e['message']['type']=='segmentation'
           for s in e['message']['normalization']['segments']]
    if not any(OBSERVED_REPAIR[0] in text.lower() for text in texts):
        raise ValueError('The observed spelling repair lacks captured reading evidence')
    rules=dict(version=PATCH_VERSION,base_version=release.version,
        observed_repairs=[dict(source=OBSERVED_REPAIR[0],target=OBSERVED_REPAIR[1])],
        review_only=[dict(source=a,target=b) for a,b in REVIEW_ONLY],
        format_recognition=audit['format_recognition'])
    DEST.mkdir(parents=True)
    payload=json.dumps(rules,ensure_ascii=False,indent=2)+'\n'
    (DEST/'rules.json').write_text(payload,encoding='utf-8')
    data=(DEST/'rules.json').read_bytes()
    sources=[ROOT/'glossaries/releases/medical-657-v1/bundle.json',reading]
    manifest=dict(version=PATCH_VERSION,base_version=release.version,policy='bounded_mvp',
        generated_utc=datetime.now(timezone.utc).isoformat(),
        sources=[dict(path=p.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sources],
        files=[dict(name='rules.json',bytes=len(data),sha256=hashlib.sha256(data).hexdigest())])
    (DEST/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (OUT/'catalog_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(concepts=audit['concept_count'],format_recognition=dict(Counter(r['language'] for r in audit['format_recognition'])),
        lexical_collisions=len(audit['lexical_collisions']),observed_repairs=1,review_only=2)))


if __name__=='__main__':main()
