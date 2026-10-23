"""Common audio front end: PyAV/Faster-Whisper decode, no loudness processing."""
import hashlib
import json
from pathlib import Path
import wave


def digest(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""):h.update(block)
    return h.hexdigest()


def corpus_pairs(root):
    root=Path(root).resolve(); result=[]
    for folder in sorted(root.iterdir()):
        if not folder.is_dir():continue
        audio=list(folder.glob("*.mp3")); refs=list(folder.glob("*.txt"))
        if len(audio)!=1 or len(refs)!=1:raise ValueError(f"Expected exactly one MP3/TXT in {folder}")
        result.append({"id":folder.name,"audio_path":str(audio[0]),"reference_path":str(refs[0]),
            "audio_sha256":digest(audio[0]),"reference_sha256":digest(refs[0]),
            "reference_status":"provisional TurboScribe reference, reviewed by user; not certified ground truth"})
    if not result:raise ValueError("No MP3/TXT pairs found")
    return result


def decode(path):
    # PyAV 19 removed av.open(metadata_errors=...), still used by FW 1.2.1.
    # Preserve its frame/group/resample/s16->float pipeline locally; never patch
    # installed packages or the LIVE PCM path. Only the obsolete kwarg is omitted.
    import av
    import gc
    import io
    import numpy as np
    from faster_whisper.audio import _ignore_invalid_frames, _group_frames, _resample_frames
    resampler=av.audio.resampler.AudioResampler(format='s16',layout='mono',rate=16000)
    buffer=io.BytesIO()
    with av.open(str(path),mode='r') as container:
        frames=_resample_frames(_group_frames(_ignore_invalid_frames(container.decode(audio=0)),500000),resampler)
        for frame in frames:buffer.write(frame.to_ndarray().tobytes())
    del resampler
    gc.collect()
    return np.frombuffer(buffer.getvalue(),dtype='<i2').astype('float32')/32768.


def describe(path,samples):
    import av
    import numpy as np
    with av.open(str(path)) as container:
        stream=container.streams.audio[0]
        original={"codec":stream.codec_context.name,"sample_rate":stream.codec_context.sample_rate,
            "channels":stream.codec_context.channels,"container_duration_s":container.duration/av.time_base if container.duration else None}
    pcm=(np.clip(np.rint(samples*32768),-32768,32767)).astype('<i2')
    return {"original":original,"decode_policy":"Lab copy of FW frame/group/resample/s16 pipeline, omitting obsolete av.open(metadata_errors); mono 16000 Hz; no VAD/denoise/gain/loudness normalization",
        "compatibility_finding":"Installed FW 1.2.1 decode_audio raises TypeError with PyAV 19.0.1 metadata_errors; local adapter only; not evidence of a LIVE PCM defect",
        "samples":len(samples),"duration_s":len(samples)/16000,"float32_sha256":hashlib.sha256(samples.astype('<f4').tobytes()).hexdigest(),
        "s16le_sha256":hashlib.sha256(pcm.tobytes()).hexdigest(),"peak_abs":float(np.max(np.abs(samples))) if len(samples) else 0.,
        "rms":float(np.sqrt(np.mean(samples.astype('float64')**2))) if len(samples) else 0.,
        "full_scale_fraction":float(np.mean(np.abs(samples)>=32767/32768)) if len(samples) else 0.,
        "nonfinite_samples":int(np.sum(~np.isfinite(samples))),"nonzero_fraction":float(np.mean(samples!=0)) if len(samples) else 0.}


def write_wav(path,samples):
    import numpy as np
    pcm=np.clip(np.rint(samples*32768),-32768,32767).astype('<i2')
    with wave.open(str(path),'wb') as f:
        f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000);f.writeframes(pcm.tobytes())


def prepare(root,out):
    """Only derives files in out; original MP3/TXT are never written."""
    import numpy as np
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    rows=corpus_pairs(root)
    for row in rows:
        samples=decode(row['audio_path']);row['audio']=describe(row['audio_path'],samples)
        wav=out/(row['id']+'.16k.wav');write_wav(wav,samples)
        back=decode(wav)
        row['wav_path']=str(wav.resolve());row['wav_sha256']=digest(wav)
        row['pcm_roundtrip_bit_exact']=bool(np.array_equal(samples,back))
        row['reference_raw']=Path(row['reference_path']).read_text(encoding='utf-8-sig')
    (out/'inputs.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    return rows
