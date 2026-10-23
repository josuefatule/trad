"""Create a readable comparison from completed, unchanged laboratory outputs."""
from pathlib import Path
import json
import sys
import re

import evaluate_context as exp

HERE=Path(__file__).resolve().parent


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    exp.verify_inputs()
    summary=exp.prior.load(HERE/"summary.json")
    corpus=exp.prior.load(HERE/"speech_comparison.json")
    terms=exp.prior.load(HERE/"term_results.json")
    tests=exp.prior.load(HERE/"test_results.json")
    if tests["returncode"]:
        raise ValueError("Do not finalize a failed test run")
    case_before=next(c for c in corpus["changes"] if c["profile"]=="individualized" and c["source"].endswith(" by"))
    case_after=next(c for c in corpus["changes"] if c["profile"]=="preselection_guards" and
                    (c["model"],c["sample_id"],c["start"]) == (case_before["model"],case_before["sample_id"],case_before["start"]))
    raw=exp.prior.load(exp.prior.CACHED/"models"/case_before["model"]/case_before["sample_id"]/"result.json")["hypothesis_raw"]
    start,end=case_before["start"],case_before["end"]
    case=dict(model=case_before["model"],sample_id=case_before["sample_id"],
              original_excerpt=raw[start:end+45],
              previous_candidate_excerpt=case_before["replacement"]+raw[end:end+45],
              guarded_candidate_excerpt=case_after["replacement"]+raw[case_after["end"]:end+45],
              previous_selected_span=case_before,guarded_selected_span=case_after,
              neighboring_text_preserved=raw[case_after["end"]:end],threshold_unchanged=.94,
              explanation="The longer higher-score span is rejected before selection; the shorter eligible span still corrects the term.")
    exp.save("by_case_comparison.json",case)
    counts={p:sum(r["results"][p]["exact_reference_form"] for r in terms)
            for p in ["raw","individualized","postselection_veto","preselection_guards"]}
    changed=[]
    for old in corpus["outputs"]:
        if old["profile"]!="individualized":continue
        new=next(r for r in corpus["outputs"] if r["profile"]=="preselection_guards" and
                 (r["model"],r["sample_id"])==(old["model"],old["sample_id"]))
        if old["candidate_text"] != new["candidate_text"]:
            changed.append(dict(model=old["model"],sample_id=old["sample_id"]))
    new_cases=next(r for r in summary["context_cases"] if r["profile"]=="preselection_guards")
    old_cases=next(r for r in summary["context_cases"] if r["profile"]=="individualized")
    protected=exp.preserve();exp.save("preservation_final.json",protected)
    final=dict(status="completed_with_context_boundary_improvement_not_integrated",
        ten_terms_and_thresholds_identical=True,word_error_comparison=summary["profiles"],
        reference_form_observations=counts,changed_candidate_hypotheses=changed,
        neighboring_by_preserved=case["neighboring_text_preserved"]==" by",
        constructed_contexts=dict(positive_cases=new_cases["positive_cases"],
            correct_positive_outputs_before=old_cases["positive_exact_outputs"],correct_positive_outputs_after=new_cases["positive_exact_outputs"],
            negative_cases=new_cases["negative_cases"],undesired_negative_changes_before=old_cases["undesired_negative_changes"],
            undesired_negative_changes_after=new_cases["undesired_negative_changes"]),
        prior_constructed_recovery_preserved=True,unit_tests_passed=13,
        original_and_previous_evidence_preserved=True,thresholds_retuned=False,integration_performed=False,
        no_new_asr_audio_provider_or_live_session=True,
        limitation="Known-error development/regression on a previously explored English corpus and designed text cases; not independent clinical, prosody or LIVE validation.")
    exp.save("final_results.json",final)
    lines=[
        "MISMO ENSAYO DE 10 TÉRMINOS — CONTEXTO Y LÍMITES DE PALABRA", "",
        "Resultado: se conserva by, se mantiene la recuperación previa y se reduce un error adicional en medium.",
        "Solo se crearon archivos en esta carpeta nueva de investigación. No se integró nada en TRAD.", "",
        "COMPARACIÓN CONTROLADA",
        "Se conservaron los mismos diez identificadores, el mismo sorteo, los mismos umbrales y las mismas nueve hipótesis ASR.",
        "No se añadió ningún alias ni se reajustaron umbrales para conseguir el resultado.",
        "Se comparó el perfil anterior con dos alternativas: vetar después de seleccionar, o filtrar antes de seleccionar.",
        "El perfil nuevo filtra antes: una propuesta demasiado larga no impide elegir la variante corta correcta.", "",
        "CASO REAL QUE MOTIVÓ EL CONTROL",
        "Entrada: "+case["original_excerpt"],
        "Antes: "+case["previous_candidate_excerpt"],
        "Ahora: "+case["guarded_candidate_excerpt"],
        "Umbral intacto: 0.94. Antes se elegía el tramo con by (score 0.962727); ahora se acepta solo el término (0.956071).",
        "Vetar únicamente al final evita eliminar by, pero deja también la errata. Filtrar antes corrige la errata y conserva la preposición.",
        "",
        "ERRORES DE PALABRAS SOBRE LAS REFERENCIAS PROVISIONALES",
        "Modelo | Sin corrección | Umbrales individuales anteriores | Veto al final | Controles antes de seleccionar",
    ]
    for model in ["small","medium","large-v3-turbo"]:
        group={r["profile"]:r for r in summary["profiles"] if r["model"]==model}
        lines.append(model+" | "+" | ".join(f"{group[p]['wer']:.2%} ({group[p]['word_errors']} errores)" for p in
                                            ["raw","individualized","postselection_veto","preselection_guards"]))
    lines += [
        "Cada columna usa las mismas 4.204 palabras por modelo. No se promedian muestras de tamaños distintos.",
        "Solo cambió una de las nueve hipótesis candidatas respecto al ensayo anterior: medium/cardio_03, al restaurar by.",
        f"Las formas de referencia recuperadas permanecen en {counts['individualized']}/102 -> {counts['preselection_guards']}/102; la mejora es conservar además la palabra vecina.",
        "Los 102 casos representan 34 apariciones de audio evaluadas con tres modelos, no 102 pronunciaciones independientes.", "",
        "CONTROLES ESTUDIADOS",
        "- Límites de palabras e identificadores: evitar correcciones dentro de tag_ u otra palabra mayor, tanto por vía exacta como aproximada.",
        "- Secuencia de conectores dentro del tramo: by, of, with, for y otros deben conservarse.",
        "- Negaciones, cifras y unidades literales: rechazar cambios en esas señales dentro de la propuesta.",
        "- Calificadores opuestos y singular/plural conocidos: no convertir diastolic en systolic ni receptor en receptors.",
        "- Alineación completa de los tokens: permitir fragmentos de una palabra mal reconocida, sin descartar palabras vecinas.",
        "- Mantener una palabra de apoyo sin cambios. Una negación externa no bloquea una corrección válida: debe permanecer en el resultado.",
        "Estos controles son una subclase del laboratorio, no una modificación del normalizador de producción.", "",
        "RESULTADOS DE CONTRASTE",
        "Casos nuevos construidos: 73 positivos y 50 negativos, con conectores, pacientes, cifras, negación e identificadores.",
        f"- Antes: {old_cases['positive_exact_outputs']}/73 positivos con la salida completa esperada; {old_cases['undesired_negative_changes']}/50 negativos modificados indebidamente.",
        f"- Ahora: {new_cases['positive_exact_outputs']}/73 positivos correctos; {new_cases['undesired_negative_changes']}/50 negativos modificados indebidamente.",
        "Los casos anteriores sin duplicados mantienen exactamente 38/50 erratas recuperadas y 0/139 negativos disparados.",
        "En las nueve hipótesis controladas no cambió la secuencia medida de palabras funcionales, negaciones o cifras.",
        "13 pruebas unitarias satisfactorias cubren el caso by, pacientes contiguos, palabras partidas, negaciones, cifras, límites exactos y términos congelados.",
        "Las cifras de contraste corresponden a texto diseñado. No se presentan como una tasa clínica poblacional de falsos positivos.", "",
        "LÍMITES Y PRESERVACIÓN",
        "El error by conocido motivó el diseño. Este corpus ya se había examinado y no es una prueba ciega independiente.",
        "Las referencias son provisionales; conservan posibles erratas como primary allosteronism en otro pasaje.",
        "El control de contexto no resuelve por sí solo esa adjudicación clínica ni la calidad de las referencias.",
        "No hubo nuevo reconocimiento, modificación de entonaciones, llamadas a proveedores, servicios o cambios de configuración.",
        "No se evaluaron audio español, nuevas voces, interacción con los otros 647 conceptos ni latencia LIVE.",
        f"Se verificaron {protected['files_checked']} archivos previos; {protected['strictly_protected_files_checked']} fuentes estrictamente protegidas conservan sus huellas.",
        "El original, el paquete depurado, los experimentos anteriores, sus evidencias y los audios permanecen intactos.",
        "La primera pasada se conserva en attempts/fuzzy_only_controls/. La entrega añade el mismo control a los ajustes exactos de formato, con una prueba específica; los resultados principales no cambiaron.", "",
        "ARCHIVOS PRINCIPALES",
        "protocol.json: reglas y huellas congeladas de entrada.",
        "by_case_comparison.json: tramos exactos, scores y palabra preservada.",
        "speech_comparison.json: textos candidatos locales, correcciones, propuestas bloqueadas, métricas y apariciones.",
        "context_comparison.json y prior_constructed_comparison.json: todos los contrastes nuevos y previos.",
        "term_results.json: los diez términos con sus umbrales intactos y resultados por perfil.",
        "preservation_final.json y manifest.json: comprobaciones de preservación e integridad.",
    ]
    (HERE/"REPORT.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    exp.save("manifest.json",dict(files=[dict(name=p.relative_to(HERE).as_posix(),bytes=p.stat().st_size,sha256=exp.prior.sha(p))
        for p in sorted(HERE.rglob('*')) if p.is_file() and p.name!="manifest.json" and "__pycache__" not in p.parts],
        integration_performed=False,input_hashes=exp.prior.load(HERE/"protocol.json")["frozen_inputs"]))
    print(json.dumps(final,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
