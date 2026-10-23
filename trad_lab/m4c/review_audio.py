"""Exact PCM excerpts for human adjudication, never ASR prompts/references."""
import json
from pathlib import Path
import wave
from trad_lab.audio import digest
from trad_lab.metrics import tokens
from .replay import ROOT, SAVED, ENV


def export(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    full=ROOT/'logs/trad_lab/20261020T074247Z/evaluation'
    baselines={s:json.loads((full/f'models/small/{s}/result.json').read_text(encoding='utf-8')) for s in ('cardio_01','cardio_03')}
    yeti=json.loads((SAVED/'received_full.json').read_text(encoding='utf-8'))
    manifest=[]
    def write(name,source,start,end,question,locator):
        source=Path(source)
        if source.suffix=='.wav':
            with wave.open(str(source),'rb') as f:
                assert (f.getnchannels(),f.getsampwidth(),f.getframerate())==(1,2,16000)
                total=f.getnframes();a=max(0,round(start*16000));b=min(total,round(end*16000))
                f.setpos(a);raw=f.readframes(b-a)
        else:
            total=source.stat().st_size//2;a=max(0,round(start*16000));b=min(total,round(end*16000))
            with source.open('rb') as f:f.seek(a*2);raw=f.read((b-a)*2)
        p=out/(name+'.wav')
        with wave.open(str(p),'wb') as f:
            f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000);f.writeframes(raw)
        with wave.open(str(p),'rb') as f:assert f.readframes(f.getnframes())==raw
        manifest.append({'file':str(p.resolve()),'sha256':digest(p),'source':str(source),
                         'source_sha256':digest(source),'start_sample':a,'end_sample':b,
                         'question':question,'locator':locator,'reference_status':'Unadjudicated audio excerpt, not ground truth'})
    def phrase(data,phrase):
        words=[w for s in data['segments'] for w in s.get('words',[])]
        target=tokens(phrase)
        for i in range(len(words)):
            for n in range(1,min(10,len(words)-i)+1):
                if tokens(''.join(w['word'] for w in words[i:i+n]))==target:
                    return words[i]['start']-2,words[i+n-1]['end']+2
        raise ValueError('Review locator not found: '+phrase)
    source=full/'inputs/cardio_01.16k.wav'
    for name,phrase_text,question in [
        ('cardio01_140','140 over 19','Adjudicar la cifra pronunciada: TXT provisional 140 over 90; ASR 140 over 19.'),
        ('cardio01_orthostatic','orthostatic hypertension','Adjudicar hypotension frente a hypertension después de orthostatic.')]:
        a,b=phrase(baselines['cardio_01'],phrase_text);write(name,source,a,b,question,'Existing offline word timestamps; bracket is approximate')
    write('cardio03_normotensive',full/'inputs/cardio_03.16k.wav',300,316,
          'Transcribir independientemente normotensive/primary aldosteronism y la cifra de este tramo.',
          'Fixed bracket around the failed incremental hypothesis; not a new aligned reference')
    for name,phrase_text,question in [
        ('cardio03_untreated','untreated stage two hypertension','Transcribir independientemente la condición untreated/treated en este pasaje.'),
        ('cardio03_years','four to six years','Adjudicar el intervalo pronunciado: four to six frente a 46; no tratarlo como equivalencia de formato.'),
        ('cardio03_unit','12 micrograms per deciliter','Adjudicar cifra y unidad independientemente; ni TXT ni ASR certifican la unidad médica.'),
        ('cardio03_drug','spironolactam','Adjudicar nombre del fármaco y cifra/unidad del pasaje sin corregir desde otro ASR.')]:
        a,b=phrase(baselines['cardio_03'],phrase_text)
        write(name,full/'inputs/cardio_03.16k.wav',a,b,question,'Existing offline word timestamps, used only to locate an approximate review bracket')
    source=ENV/'trad_wire/wire_01/received.s16le'
    for name,phrase_text,question in [
        ('yeti_57','57 new recommendations','Adjudicar la cifra sin usar las hipótesis como verdad.'),
        ('yeti_patients','patients with hypertension','Adjudicar el término después de patients with.'),
        ('yeti_defining','defining hypertension','Adjudicar el término después de defining.')]:
        a,b=phrase(yeti,phrase_text);write(name,source,a,b,question,'Existing offline word timestamps on the identical server PCM; nominal 16 kHz time')
    duration=source.stat().st_size/32000
    write('yeti_end',source,duration-15,duration,
          'Adjudicar el último sonido/palabra. No completar la frase por contexto ni tomar di-/diastolic como verdad.',
          'Last 15 seconds of the exact received PCM, including its recorded tail')
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')
    return manifest


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('out');args=p.parse_args()
    print(json.dumps({'exact_pcm_excerpts':len(export(args.out))}))
