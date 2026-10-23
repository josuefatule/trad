"""Candidate temporal references from the user's TXT, never ASR hypotheses.

ASR word times are boundary aids only. Human acceptance of each exact WAV/TXT
hash pair is required before reporting fragment WER/CER.
"""
from difflib import SequenceMatcher
import json
from pathlib import Path
import re
import statistics

from trad_lab.audio import digest,write_wav
from trad_lab.metrics import tokens
from trad_lab.runner import save
from .audio_analysis import read_pcm


def time_map(result,reference):
    words=[];times=[]
    for segment in result['segments']:
        for word in segment['words']:
            for token in tokens(word['word']):
                words.append(token);times.append((word['start'],word['end']))
    mapping={}
    for block in SequenceMatcher(None,reference,words,autojunk=False).get_matching_blocks():
        for offset in range(block.size):mapping[block.a+offset]=times[block.b+offset]
    return mapping


def validated_reference(sample,validation):
    accepted=validation.get('accepted',{}).get(sample['id'])
    if not accepted:return None
    if (accepted.get('wav_sha256')!=digest(sample['wav_path'])
            or accepted.get('reference_sha256')!=digest(sample['reference_path'])):
        raise ValueError('Reference validation hashes no longer match')
    if accepted.get('temporal_validation')!='user_accepted':return None
    return Path(sample['reference_path']).read_text(encoding='utf-8-sig')


def prepare(m3,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=False);rows=[]
    for sample_id,target in [('cardio_01',0),('cardio_02',420),('cardio_03',240)]:
        paths=[Path(m3)/'evaluation/models'/model/sample_id/'result.json' for model in ['small','medium','large-v3-turbo']]
        results=[json.loads(p.read_text(encoding='utf-8')) for p in paths]
        raw=results[0]['reference_raw'];ref=tokens(raw)
        sentences=[];cursor=0
        for match in re.finditer(r'.+?(?:[.!?](?=\s)|$)',raw,re.S):
            text=match.group().strip()
            if not text:continue
            count=len(tokens(text));sentences.append({'text':text,'start':cursor,'end':cursor+count});cursor+=count
        if cursor!=len(ref):raise ValueError('Sentence/token indexing mismatch')
        maps=[time_map(r,ref) for r in results]
        def boundary(index):
            if index==0:return 0.,[0.]*3
            values=[]
            for mapping in maps:
                if index not in mapping or index-1 not in mapping:return None,None
                # Require lexical anchors on both sides of an internal cut.
                if any(j not in mapping for j in range(max(0,index-3),min(len(ref),index+3))):return None,None
                values.append((mapping[index-1][1]+mapping[index][0])/2)
            return statistics.median(values),values
        starts=[]
        for i,s in enumerate(sentences):
            t,values=boundary(s['start'])
            if t is not None and abs(t-target)<45:starts.append((abs(t-target),i,t,values))
        _,i,start,start_votes=min(starts)
        ends=[]
        for j in range(i+1,len(sentences)):
            t,values=boundary(sentences[j]['end'])
            if t is not None and 60<=t-start<=120:ends.append((abs(t-start-90),j,t,values))
        _,j,end,end_votes=min(ends)
        text=' '.join(s['text'] for s in sentences[i:j+1])
        source=Path(m3)/'evaluation/inputs'/(sample_id+'.16k.wav')
        audio=read_pcm(source);a,b=round(start*16000),round(end*16000)
        folder=out/sample_id;folder.mkdir();wav=folder/'clip.wav';txt=folder/'reference.candidate.txt'
        write_wav(wav,audio[a:b]);txt.write_text(text,encoding='utf-8')
        row={'id':sample_id,'source_wav':str(source.resolve()),'source_sha256':digest(source),
            'wav_path':str(wav.resolve()),'wav_sha256':digest(wav),'reference_path':str(txt.resolve()),'reference_sha256':digest(txt),
            'start_sample':a,'end_sample':b,'start_s':a/16000,'end_s':b/16000,'duration_s':(b-a)/16000,
            'reference_word_range':[sentences[i]['start'],sentences[j]['end']],
            'start_model_times_s':start_votes,'end_model_times_s':end_votes,
            'boundary_spread_s':max(max(start_votes)-min(start_votes),max(end_votes)-min(end_votes)),
            'status':'pending_user_temporal_validation','reference_origin':'Exact sentences from user-reviewed full TXT, no ASR correction',
            'alignment_limit':'Three ASR time maps agree on lexical anchors, but do not independently validate the spoken boundary or medical truth'}
        rows.append(row)
    save(out/'clips.json',rows)
    save(out/'reference_validation.json',{'accepted':{},'policy':'Only populate after explicit user acceptance of the exact fragment WAV/TXT hashes'})
    md='# Referencias temporales M4 — revisión pendiente\n\nEscuchar cada WAV y comprobar la primera/última oración y cifras/unidades/negaciones. El texto procede del TXT del usuario; los tiempos asistidos por ASR no son validación humana. No se reportará WER/CER del fragmento hasta aceptar el par por hash.\n\n'
    for row in rows:
        md+=f"## {row['id']} — {row['start_s']:.3f}–{row['end_s']:.3f} s\n\n"
        md+=f"![Clip]({row['wav_path'].replace(chr(92),'/')})\n\n"
        md+=Path(row['reference_path']).read_text(encoding='utf-8')+'\n\n'
    (out/'REFERENCE_REVIEW.md').write_text(md,encoding='utf-8')
    return rows
