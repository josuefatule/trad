"""Audit frozen trial outputs and prepare listening examples; do not retune."""
import json
from pathlib import Path
import re
import subprocess
import sys
import wave

import evaluate_trial as trial
from trad_lab.metrics import tokens, word_alignment, TOKEN
import unicodedata

HERE = Path(__file__).resolve().parent


def audit_corrections(checked):
    reviewed = []
    for change in checked["simulated_corrections"]:
        if change["profile"] != "individualized":
            continue
        record = trial.load(trial.CACHED/"models"/change["model"]/change["sample_id"]/"result.json")
        raw, ref = record["hypothesis_raw"], record["reference_raw"]
        assert raw[change["start"]:change["end"]] == change["source"]
        once = raw[:change["start"]]+change["replacement"]+raw[change["end"]:]
        errors, edits = word_alignment(tokens(ref), tokens(once))
        delta = errors-record["metrics"]["word_errors"]
        norm = unicodedata.normalize("NFKC", raw).casefold().replace("’", "'").replace("‘", "'")
        before = unicodedata.normalize("NFKC", raw[:change["start"]]).casefold()
        until = unicodedata.normalize("NFKC", raw[:change["end"]]).casefold()
        h_indices = [i for i,m in enumerate(TOKEN.finditer(norm)) if m.start() < len(until) and m.end() > len(before)]
        mapping = trial.ref_map(tokens(ref), tokens(raw), record["metrics"]["word_edits"])
        r_indices = [r for r,h in mapping.items() if h in h_indices]
        context = " ".join(tokens(ref)[max(0,min(r_indices)-5):max(r_indices)+6]) if r_indices else None
        reviewed.append(dict(**change, word_error_delta_if_applied_alone=delta,
                             provisional_reference_context=context,
                             assessment="lexical_agreement_improved" if delta < 0 else "lexical_agreement_worsened" if delta > 0 else "lexically_neutral",
                             independent_clinician_review="not_performed"))
    return reviewed


def additional_audio_examples(selected, sources, checked):
    examples = trial.load(HERE/"audio_examples.json")
    covered = {r["concept_id"] for r in examples}
    for number, item in enumerate(selected, 1):
        if item["concept_id"] in covered:
            continue
        choices = [r for r in checked["occurrences"] if r["concept_id"] == item["concept_id"] and
                   r["profile"] == "raw" and r["model"] == "small"]
        for choice in choices:
            if not choice["hypothesis_token_indices"]:
                continue
            source = next(s for s in sources if s["id"] == choice["sample_id"])
            data = trial.load(trial.CACHED/"models/small"/choice["sample_id"]/"result.json")
            stream, times = [], []
            for segment in data["segments"]:
                part = tokens(segment["text"]); stream += part
                times += [(segment["start"], segment["end"])]*len(part)
            if stream != tokens(data["hypothesis_raw"]):
                raise ValueError("Cannot verify segment-to-token mapping")
            indices = choice["hypothesis_token_indices"]
            first_s = max(0,min(times[i][0] for i in indices)-.25)
            last_s = max(times[i][1] for i in indices)+.25
            with wave.open(source["wav_path"], "rb") as src:
                rate=src.getframerate(); first=int(first_s*rate); last=min(src.getnframes(),int(last_s*rate))
                params=src.getparams(); src.setpos(first); data_pcm=src.readframes(last-first)
            path=HERE/"audio_examples"/f"{number:02d}_{item['concept_id']}_context.wav"
            with wave.open(str(path), "wb") as dst:
                dst.setparams(params); dst.writeframes(data_pcm)
            examples.append(dict(concept_id=item["concept_id"], canonical_en=item["canonical_en"], path=str(path),
                sha256=trial.sha(path), source_wav=source["wav_path"], source_sha256=trial.sha(source["wav_path"]),
                first_sample=first, last_sample_exclusive=last, sample_rate=rate,
                expected_provisional_reference=choice["reference_form"], asr_aligned_phrase=" ".join(choice["observed_tokens"]),
                locator="Whole cached ASR segment container, not exact word boundaries; token mapping verified.",
                manipulated_prosody=False))
            break
    for example in examples:
        with wave.open(example["source_wav"], "rb") as src:
            src.setpos(example["first_sample"])
            original=src.readframes(example["last_sample_exclusive"]-example["first_sample"])
        with wave.open(example["path"], "rb") as derived:
            assert derived.readframes(derived.getnframes()) == original
    return examples


def checking_overlap(cases):
    calibration={(c["concept_id"],c["positive"],c["text"]) for c in cases if c["split"] == "calibration"}
    duplicated=[c["case_id"] for c in cases if c["split"] == "synthetic_checking" and
                (c["concept_id"],c["positive"],c["text"]) in calibration]
    checking=trial.load(HERE/"synthetic_checking.json")
    clean=[]
    for row in checking:
        selected=[r for r in row["results"] if r["case_id"] not in duplicated]
        clean.append(dict(concept_id=row["concept_id"],profile=row["profile"],threshold=row["threshold"],
                          **trial.score_cases(selected,cases)))
    return dict(exact_duplicate_checking_case_ids=duplicated, excluded_from_nonoverlap_summary=True,
                reason="The merged-word generator repeats the same input across splits. Original outputs are retained; no threshold is changed after checking.",
                nonoverlap_checking=clean,
                independence_limit="Other variants still share a construction recipe. This is not independent speech validation.")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    frozen_hashes={name:trial.sha(HERE/name) for name in ["selection.json","protocol.json","threshold_decisions.json","real_speech_checking.json","term_results.json"]}
    selected=trial.load(HERE/"selection.json")["selected"]
    checked=trial.load(HERE/"real_speech_checking.json")
    audit=audit_corrections(checked);trial.save("correction_review.json",audit)
    examples=additional_audio_examples(selected,trial.load(trial.CACHED/"inputs/inputs.json"),checked)
    trial.save("audio_review_examples.json",examples)
    overlap=checking_overlap(trial.load(HERE/"constructed_cases.json"));trial.save("checking_overlap_audit.json",overlap)
    cmd=[sys.executable,"-B",str(HERE/"test_trial.py")]
    tested=subprocess.run(cmd,capture_output=True,text=True,encoding="utf-8",cwd=trial.ROOT)
    trial.save("test_results.json",dict(command=cmd,returncode=tested.returncode,output=tested.stdout+tested.stderr))
    if tested.returncode:
        raise SystemExit(tested.stdout+tested.stderr)
    for name,digest in frozen_hashes.items():
        if trial.sha(HERE/name) != digest:
            raise ValueError("A frozen selection, protocol or result changed")
    preserved=trial.preserve();trial.save("preservation_final.json",preserved)
    term_results=trial.load(HERE/"term_results.json")
    synth={}
    for profile in ("uniform_090","individualized"):
        rows=[r for r in overlap["nonoverlap_checking"] if r["profile"] == profile]
        synth[profile]={key:sum(r[key] for r in rows) for key in ["positive_cases","recovered","negative_cases","negative_triggers"]}
    review_counts={label:sum(r["assessment"] == label for r in audit) for label in
                   ["lexical_agreement_improved","lexical_agreement_worsened","lexically_neutral"]}
    final=dict(random_terms=10, random_pool=97, unique_recorded_occurrences=34, model_observations=102,
               exact_form_occurrences={profile:sum(r["real_speech"][profile]["exact_reference_form"] for r in term_results)
                                      for profile in ["raw","uniform_090","individualized"]},
               synthetic_nonoverlap_checking=synth, exact_duplicate_checking_cases=len(overlap["exact_duplicate_checking_case_ids"]),
               simulated_individualized_corrections=len(audit), correction_review=review_counts,
               naturally_recorded_audio_examples=len(examples), controlled_intonation_variations_tested=0,
               unchanged_original_and_evidence_hashes=True, thresholds_retuned_after_speech_checking=False,
               live_application_performed=False, clinical_certification=False,
               conclusion="Exploratory improvement in small and medium, no WER change in turbo; individual context-boundary mistakes remain.")
    trial.save("final_results.json",final)
    lines=["ENSAYO INICIAL DE TOLERANCIA POR TÉRMINO — 10 CONCEPTOS ALEATORIOS", "",
        "Resultado: se obtuvo mejora léxica en small y medium sobre las transcripciones guardadas; turbo quedó igual.",
        "Los cambios son simulaciones locales posteriores al ASR. No se modificó ningún resultado anterior ni se integró nada en TRAD.", "",
        "SELECCIÓN Y MÉTODO",
        "Se eligieron 10 conceptos sin reemplazo entre 97 presentes en las referencias inglesas, antes de revisar sus errores ASR.",
        "Semilla registrada: 12339650134334788941. La selección incluye dos nombres de organizaciones; no se repitió el sorteo.",
        "Se compararon puntos del score heurístico entre 0.86 y 1.00. El valor no representa probabilidad ni porcentaje de confianza.",
        "Se eligió cada umbral con ejemplos construidos de erratas y negativos cercanos: máxima recuperación con cero disparos negativos, desempate hacia mayor umbral.",
        "La selección se congeló antes del checking de voz. No se ajustó después de ver las transcripciones reales.",
        "Los casos construidos no son pronunciaciones. Se conservan los datos originales y sus particiones.",
        "",
        "RESULTADOS SOBRE AUDIO NATURAL YA RECONOCIDO",
        "Tres archivos de audio, nueve hipótesis de tres modelos y referencias provisionales. Los archivos 02/03 podrían ser partes de una misma charla.",
        "34 apariciones únicas de los términos, observadas por tres modelos: 102 observaciones correlacionadas.",
        "WER = proporción de errores de palabras frente a las referencias provisionales, calculada sobre las 4.204 palabras completas por modelo.",
        "Modelo | Sin corrección | Umbral uniforme 0.90 | Umbrales por término",
    ]
    for model in ("small","medium","large-v3-turbo"):
        rows={r["profile"]:r for r in checked["aggregate"] if r["model"] == model}
        lines.append(f"{model} | {rows['raw']['wer']:.2%} ({rows['raw']['word_errors']} errores) | "
                     f"{rows['uniform_090']['wer']:.2%} ({rows['uniform_090']['word_errors']}) | "
                     f"{rows['individualized']['wer']:.2%} ({rows['individualized']['word_errors']})")
    lines += ["", "TÉRMINOS Y PUNTOS SELECCIONADOS",
              "Apariciones: coincidencia literal con la forma de referencia, antes -> después, sobre los tres modelos; no es exactitud clínica."]
    for r in term_results:
        real=r["real_speech"]; target=r["selected_auto_threshold"]
        lines.append(f"- {r['canonical_en']} / {r['preferred_es']}: {target}; "
                     f"{real['raw']['exact_reference_form']} -> {real['individualized']['exact_reference_form']} de {real['raw']['observations']}.")
    lines += ["El punto 1.00 se seleccionó para tres términos como la opción más restrictiva empatada en recuperación; no certifica seguridad.",
        "La mayor ganancia procede de primary aldosteronism: 12 -> 29 coincidencias de 30.",
        "Ejemplos observados: primary aldous gerinism -> primary aldosteronism (score 0.940317); primary allosteronism -> primary aldosteronism (0.956071).",
        "Los otros nueve términos no mejoraron su conteo literal; casi todos ya estaban bien reconocidos.",
        "Para ten-year ASCVD risk, el uniforme 0.90 absorbía el artículo de the 10-year ASCVD risk. El umbral 0.94 evitó esa modificación.",
        "No se presenta ten/10 como diferencia clínica: el problema observado incluye la pérdida de palabras y el cambio de grafía.",
        "",
        "REVISIÓN DE LOS CAMBIOS Y COSTES",
        f"Se simularon {len(audit)} cambios con umbrales individuales: {review_counts['lexical_agreement_improved']} mejoran la concordancia con la referencia al evaluarlos por separado, "
        f"{review_counts['lexical_agreement_worsened']} la empeoran y {review_counts['lexically_neutral']} son neutros.",
        "La mejora neta no vuelve aceptables todos los cambios. Ejemplo: primary allosteronism by -> primary aldosteronism elimina by.",
        "Ese caso tiene delta WER cero: corregir el término compensa perder by. Por eso una métrica global puede ocultar una pérdida local.",
        "El cambio clasificado como peor concordancia literal coincide con una referencia que también escribe primary allosteronism; podría ser una errata de la referencia y exige escucha, no una conclusión clínica automática.",
        "La revisión frente a la referencia provisional está en correction_review.json; no hubo adjudicación clínica independiente.",
        "Con umbrales individuales no cambió el canal medido de negaciones/cifras, pero este canal no detecta todos los cambios de significado.",
        "En los casos sintéticos de checking sin duplicados exactos:",
    ]
    for profile,label in [("uniform_090","Uniforme 0.90"),("individualized","Individualizados")]:
        r=synth[profile]
        lines.append(f"- {label}: {r['recovered']}/{r['positive_cases']} erratas recuperadas y {r['negative_triggers']}/{r['negative_cases']} negativos disparados.")
    lines += [f"Se detectaron {len(overlap['exact_duplicate_checking_case_ids'])} inputs de checking idénticos a calibración, producidos por la receta de palabras unidas. Se excluyen de ese resumen, sin cambiar umbrales ni ocultar resultados originales.",
        "La configuración más restrictiva evita confusiones, a costa de recuperar menos erratas construidas. No hay mejora universal de todas las métricas.",
        "",
        "ENTONACIÓN Y ESCUCHA",
        "Se prepararon 10 ejemplos WAV del audio natural para escuchar los términos; varios contienen el segmento completo para no inventar límites de palabra.",
        "Sus muestras PCM coinciden exactamente con los intervalos originales. La localización usa timestamps ASR aproximados, no revisión auditiva independiente.",
        "No se variaron tono, acento ni velocidad; no se ensayaron entonaciones controladas ni nuevos hablantes.",
        "Comparar tres modelos sobre una misma grabación no equivale a tres entonaciones. Los errores de texto no constituyen variantes fonéticas verificadas.",
        "audio_review_examples.json identifica cada clip, su origen, huella e intervalo. Harían falta grabaciones nuevas de pronunciaciones distintas para validar esa generalización.",
        "",
        "DECISIÓN",
        "Sí conviene continuar con tolerancias por término: hay ganancia observada y menos modificaciones que con el umbral uniforme.",
        "Los puntos elegidos son candidatos de investigación. El score, el tamaño de ventana y el contexto deben estudiarse juntos: un umbral por sí solo todavía puede absorber palabras vecinas.",
        "Esta muestra es pequeña y previamente explorada; no se extrapola a los 657 conceptos, a español, a otros hablantes o a TRAD en vivo.",
        "Los originales, el paquete depurado, las evidencias, los audios y las inferencias previas conservan sus huellas. Solo se escribieron archivos en esta carpeta nueva.",
    ]
    (HERE/"REPORT.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    trial.save("manifest.json",dict(files=[dict(name=p.relative_to(HERE).as_posix(),bytes=p.stat().st_size,sha256=trial.sha(p))
                                            for p in sorted(HERE.rglob('*')) if p.is_file() and p.name != "manifest.json" and "__pycache__" not in p.parts],
                                   integration_performed=False, frozen_input_hashes=frozen_hashes))
    print(json.dumps(final,ensure_ascii=False,indent=2))


if __name__ == "__main__":
    main()
