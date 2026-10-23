"""Present every fixed cap and adverse finding, then seal both new trials."""
from collections import Counter
from datetime import datetime,timezone
import subprocess
import sys
import run_flexible as exp

HERE=exp.HERE
FINAL=HERE/'visible_root_refinement_v2'


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    if (HERE/'manifest.json').exists():raise SystemExit('Sealed experiment cannot be overwritten')
    summary=exp.load(FINAL/'summary.json');review=exp.load(HERE/'review_findings.json')
    corpus=exp.load(FINAL/'speech_comparison.json');terms=exp.load(FINAL/'term_results.json')
    tested=subprocess.run([sys.executable,'-B',str(FINAL/'test_outputs_refined.py')],capture_output=True,text=True,encoding='utf-8',cwd=exp.ROOT)
    exp.save('verification_tests.json',dict(returncode=tested.returncode,output=tested.stdout+tested.stderr))
    if tested.returncode:raise SystemExit(tested.stdout+tested.stderr)
    preserved=exp.preserve();exp.save('preservation_final.json',preserved)
    negative=exp.load(HERE/'negative_change_review.json');losses=exp.load(HERE/'recovery_loss_review.json')
    before=exp.load(HERE/'summary.json')
    caps=['direction_guard_cap092','direction_guard_cap090','direction_guard_cap088']
    conclusions='El control específico impide los intercambios previstos entre hypertension e hypotension. Ninguna relajación global ensayada cumple todos los controles negativos: aparecen otras reescrituras no deseadas.'
    final=dict(status='laboratory_trial_complete_original_and_evidence_unchanged',conclusion_es=conclusions,
        same_97_terms=True,active_fuzzy_terms=80,unchanged_exact_only_terms=17,
        fixed_caps=[.92,.90,.88],model_comparison=review['model_comparison'],
        pressure_controls=summary['pressure_controls'],constructed=summary['constructed'],contexts=summary['contexts'],regressions=summary['regressions'],
        negative_rewrite_eligibility=review['negative_rewrite_eligibility'],
        first_trial_retained=True,visible_root_refinement_retained=True,
        ambiguous_direction_policy='Abstain on hypetension and similarly uncertain direction; preserve explicit hyper/hypo root despite at most two suffix spelling edits.',
        same_threshold_guard_recovery_losses=[{k:v for k,v in r.items() if k!='rows'} for r in losses if r['profile']=='direction_guard_same'],
        development_tests_passed=14,output_verification_tests_passed=13,
        unique_reference_occurrences=310,correlated_model_observations=930,
        previous_research_and_original_unchanged=True,preservation=preserved,
        policies_or_caps_retuned_after_final_replay=False,independent_holdout=False,
        new_asr_inference=False,controlled_intonation_variants_tested=0,clinical_adjudication=False,integration_performed=False)
    exp.save('final_results.json',final)
    data={name:exp.load(FINAL/(name+'_comparison.json')) for name in ['pressure','constructed','context','regression']}
    lines=[
        'CONTROLES HYPERTENSION / HYPOTENSION Y TOLERANCIAS MÁS FLEXIBLES',
        '97 conceptos. Laboratorio e investigación, sin integración en TRAD.', '',
        'RESULTADO PRINCIPAL',conclusions,
        'Las métricas de palabras y los controles negativos se presentan juntos: un WER menor por sí solo no vuelve aceptable una reescritura.', '',
        'QUÉ SE CAMBIÓ',
        'Se añadió una comprobación previa a la selección de candidatos exactos y aproximados: la secuencia de direcciones HYPER/HYPO debe conservarse; no se puede cambiar, crear, borrar o invertir su orden.',
        'El alcance es la familia textual de hypertension/hypotension y sus formas hypertensive/hypotensive, con prefijos declarados y fragmentos separados que recomponen una grafía reconocida.',
        'Se aceptan reparaciones ortográficas cuando la raíz direccional permanece explícita; por ejemplo, hypertenson o hypertesion conservan hyper. No se decide una dirección por parecido general si falta esa raíz.',
        'Una forma como hypetension se conserva sin adivinar entre hypertension e hypotension. La abstención puede perder recuperaciones que el generador de erratas sí etiquetó con un destino conocido.',
        'La nueva firma es una regla de conservación de texto, no un clasificador clínico ni una validación de diagnósticos.',
        'Se mantienen los controles previos de variantes, número gramatical, conectores, negación, cifras/unidades, límites de palabra/identificador y selección entre frases largas y subexpresiones.',
        'El cambio no añade un control general para otras familias como hyperkalemic/hypokalemic; ese límite aparece en las pruebas y se documenta.', '',
        'TOLERANCIAS Y PERFILES CONGELADOS',
        'Se conservaron los mismos 97 términos y los 24 registros de variantes de investigación; no se habilitaron nuevas equivalencias ni expansiones.',
        'Para los 80 términos con fuzzy activo se calculó min(umbral previo, límite). Se fijaron límites 0.92, 0.90 y 0.88 antes de repetir los casos y las transcripciones.',
        'Los 17 términos en coincidencia exacta permanecieron en exacto. Reducir el umbral de score significa permitir más coincidencias; no expresa probabilidad o certeza.',
        '0.92 reduce 70 umbrales, 0.90 reduce 79 y 0.88 reduce los 80. No se eligió un límite ganador a partir de las grabaciones ni se retocaron los límites después.',
        'Perfiles: previous97 (reglas/umbrales anteriores); direction_guard_same (nuevo control, mismos umbrales); old_guard_cap090 (control sin nuevo bloqueo, límite 0.90); direction_guard_cap092/090/088 (nuevo control y sus límites).', '',
        'DOS EJECUCIONES CONSERVADAS',
        'La primera ejecución trató como ambiguas algunas grafías que aún conservaban hyper/hypo, porque exigía un comienzo de sufijo demasiado estrecho.',
        'Se conservaron todos sus resultados y su código en esta carpeta principal. first_replay_manifest.json registra sus huellas.',
        'La segunda ejecución, en visible_root_refinement_v2, solo convierte esas marcas ambiguas en una dirección explícita cuando la raíz está intacta y hay como máximo dos errores de sufijo.',
        'Se congeló la revisión antes de repetir la comparación, manteniendo los mismos términos, datos y límites. Las formas sin dirección clara siguen sin corregirse.',
        'Los casos construidos que tuvieron algún veto direccional se recalcularon; los demás se reutilizaron porque el único cambio no puede alterar su filtrado.',
        'Para voz se revisó la auditoría completa de vetos y se repitió la selección cuando un candidato antes vetado pasó a admisible. Con filtrado idéntico se reutilizó la salida; las métricas solo se reutilizaron cuando el texto coincidía byte por byte.',
        'Estas pruebas verifican explícitamente la reutilización. No se presentan como datos nuevos o independientes.', '',
        'CONTROLES ESPECÍFICOS DE PRESIÓN',
        'Son 97 casos construidos distintos de los 97 conceptos: 7 positivos y 90 negativos previstos. Incluyen ambas direcciones, mayúsculas, prefijos, fragmentos separados, negación, cifras, identificadores y formas ambiguas.',
        'Perfil | Positivos recuperados | Negativos modificados | Total correcto']
    for r in summary['pressure_controls']:
        lines.append(f"{r['profile']} | {r['positive_correct']}/{r['positive_cases']} | {r['negative_changed']}/{r['negative_cases']} | {r['passed']}/{r['cases']}")
    lines += [
        'Los tres fallos conocidos primary hypotension -> primary hypertension, orthostatic hypertension -> orthostatic hypotension y secondary hypotension -> secondary hypertension quedan bloqueados antes de la selección.',
        'Los perfiles flexibles recuperan antihypertension medication -> antihypertensive medication sin cambiar la dirección HYPER y sin perder los controles anteriores.', '',
        'ERROR LÉXICO EN LAS MISMAS TRANSCRIPCIONES COMPLETAS',
        'WER = errores de palabras / 4.204 palabras de referencia por modelo; menor es mejor. Referencias provisionales.',
        'Modelo | 97 anteriores | Nuevo control, mismos umbrales | Nuevo control 0.92 | Nuevo control 0.90 | Nuevo control 0.88']
    for model in ['small','medium','large-v3-turbo']:
        rows={r['profile']:r for r in corpus['aggregate'] if r['model']==model}
        ps=['previous97','direction_guard_same']+caps
        lines.append(model+' | '+' | '.join(f"{rows[p]['wer']:.2%} ({rows[p]['word_errors']})" for p in ps))
    lines += ['', 'CONTROL DE ABLACIÓN: MISMO LÍMITE 0.90 CON Y SIN EL NUEVO BLOQUEO',
        'Modelo | Bloqueo anterior a 0.90 | Bloqueo reforzado a 0.90']
    for model in ['small','medium','large-v3-turbo']:
        rows={r['profile']:r for r in corpus['aggregate'] if r['model']==model}
        lines.append(model+f" | {rows['old_guard_cap090']['word_errors']} | {rows['direction_guard_cap090']['word_errors']}")
    lines += [
        'Son errores del corpus completo, no una tasa limitada a los términos. El perfil anterior se reprodujo frente a sus salidas guardadas; no se normalizaron las referencias.',
        '', 'ERRATAS Y NEGATIVOS GENERALES',
        'Se repitieron los 1.807 casos anteriores: 484 positivos y 1.323 negativos. Son casos etiquetados por concepto y algunos textos se repiten entre conceptos; no son 1.807 observaciones independientes.',
        'Perfil | Positivos recuperados | Negativos modificados']
    for r in summary['constructed']:
        lines.append(f"{r['profile']} | {r['positive_correct']}/{r['positive_cases']} | {r['negative_changed']}/{r['negative_cases']}")
    lines += [
        'Cada límite flexible introduce cambios no deseados fuera de hypertension/hypotension. negative_change_review.json agrupa también los pares entrada/salida únicos para no confundir repeticiones con diversidad de fallos.',
        'Ejemplos que permanecen visibles: physical inactivity -> physical activity; aldosterone-producing adenoma -> aldosterone production adenoma; hyperkalemic metabolic alkalosis -> hypokalemic metabolic alkalosis.',
        'A límites menores se añade seated blood pressure -> elevated blood pressure. No se corrigieron estos controles después de ver el resultado ni se omitieron del resumen.', '',
        'NÚMERO DE PARES NEGATIVOS DISTINTOS, AGRUPADOS POR ENTRADA Y SALIDA']
    for r in negative:
        if r['dataset']=='constructed':lines.append(f"{r['profile']} | {r['cases']} casos | {r['unique_input_output_pairs']} pares distintos")
    lines += ['', 'CONTEXTO, LÍMITES Y COSTE DE ABSTENERSE',
        'Se repitieron 682 positivos de contexto y 485 negativos. La nueva protección conserva una grafía ambigua aunque el caso sintético la etiquetara como errata de hypertension.',
        'Perfil | Positivos correctos | Negativos modificados']
    for r in summary['contexts']:
        lines.append(f"{r['profile']} | {r['positive_correct']}/{r['positive_cases']} | {r['negative_changed']}/{r['negative_cases']}")
    for name in ['constructed','context']:
        lost=next(r for r in losses if r['dataset']==name and r['profile']=='direction_guard_same')
        lines.append(f"Coste del nuevo control con umbrales intactos en {name}: {lost['lost_cases']} casos antes recuperados dejan de recuperarse.")
    lines += [
        'recovery_loss_review.json conserva todas esas pérdidas con entrada, salida y cambios. No se equipara una abstención deliberada con una corrección demostrada; se registra como pérdida de recuperación.',
        'Los 153 controles previos de variantes/plurales, by, contexto y solapamientos se mantienen en regression_comparison.json.', '',
        'AUDITORÍA Y DECISIÓN',
        'correction_review.json registra cada cambio de los perfiles reforzados, si es nuevo respecto al perfil de 97 anterior y su efecto léxico al retirarlo del perfil.',
        'Un cambio puede acercarse a una referencia provisional y seguir siendo una reescritura que requiera revisión. No hubo adjudicación clínica ni escucha independiente nueva.',
        'El nuevo bloqueo específico funciona en los controles ensayados. Los límites globales 0.92/0.90/0.88 no se consideran aprobados, aunque alguna métrica de palabras mejore.',
        'La evidencia aconseja estudiar flexibilidad por término manteniendo controles de conceptos próximos; cualquier corrección adicional de otros contrastes pertenece a otro ensayo, no a una modificación retrospectiva de este.', '',
        'LOS 97 CONCEPTOS Y SUS UMBRALES',
        'Exacto = fuzzy deshabilitado. Los valores siguientes son los mismos para todos los casos de cada perfil.',
        'N.º | Inglés / Español | Anterior | Límite 0.92 | Límite 0.90 | Límite 0.88']
    for i,r in enumerate(terms,1):
        values=[r['thresholds'][p] for p in ['previous97']+caps]
        lines.append(f"{i:02d} | {r['canonical_en']} / {r['preferred_es']} | "+' | '.join('Exacto' if v is None else f'{v:.2f}' for v in values))
    lines += ['', 'ALCANCE Y CONSERVACIÓN',
        'Tres archivos de voz natural y nueve hipótesis guardadas: 310 apariciones de los términos y 930 observaciones de modelos correlacionadas. Los archivos 02/03 podrían pertenecer a una misma charla.',
        'No hubo nuevas inferencias ASR, voces o variaciones de tono/acento/velocidad. Los casos construidos son texto, no pronunciaciones verificadas.',
        'El corpus y las recetas de errores ya se habían explorado; la revisión usó defectos observados durante el desarrollo. No es un conjunto independiente ni una validación clínica.',
        'No se extrapola el resultado a los 657 conceptos, español u otros hablantes. Todos los valores son candidatos o controles de laboratorio.',
        'Pasaron 14 pruebas de las reglas refinadas y 13 verificaciones de salidas, conservación, perfiles, reconstrucción y reutilización demostrada.',
        f"Se comprobaron {preserved['files_checked']} archivos previos, {preserved['strictly_protected_files_checked']} protegidos estrictamente; observaciones ajenas a esta tarea: {len(preserved['other_workspace_observations'])}.",
        'El glosario original, las evidencias, todos los ensayos anteriores, el paquete depurado, los audios/referencias, ASR guardados y el código de aplicación usado mantienen sus huellas.',
        'Solo se escribieron archivos nuevos en polarity_flexible_trial_97_v1. La primera ejecución y visible_root_refinement_v2 permanecen conservadas por separado.',
        'No se conectó, modificó ni integró nada en TRAD. No se cambió el estado de aprobación del glosario.', '',
        'ARCHIVOS DE REVISIÓN',
        'final_results.json y review_findings.json: resumen, comparación y decisión.',
        'visible_root_refinement_v2/speech_comparison.json y term_results.json: siete perfiles, texto simulado, cambios, evidencias de reutilización y los 97 conceptos.',
        'visible_root_refinement_v2/pressure_comparison.json, constructed_comparison.json, context_comparison.json y regression_comparison.json: resultados por caso.',
        'negative_change_review.json, recovery_loss_review.json y correction_review.json: errores nuevos, pérdidas y efectos de los cambios.',
        'Los dos protocol.json fijan reglas, límites y entradas; first_replay_manifest.json conserva la primera ejecución; manifest.json sella todo el trabajo nuevo.',
    ]
    (HERE/'REPORT.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (HERE/'README.txt').write_text(
        'Leer REPORT.txt y final_results.json. Ensayo de laboratorio sobre los mismos 97 términos.\n'
        'Se reforzó hypertension/hypotension y se compararon límites 0.92, 0.90 y 0.88.\n'
        'La revisión final está en visible_root_refinement_v2; el primer ensayo se conserva.\n'
        'Ningún límite global flexible satisface todos los controles negativos. No se aprueba integración.\n'
        'Los protocolos y programas se niegan a sobrescribir ensayos congelados.\n'
        'No hay nuevos audios, entonaciones ni validación clínica independiente.\n',encoding='utf-8')
    exp.verify_prior()
    for r in exp.load(HERE/'first_replay_manifest.json')['files']:assert exp.sha(HERE/r['name'])==r['sha256']
    for directory in [FINAL,HERE]:
        manifest=directory/'manifest.json'
        manifest.write_text(exp.json.dumps(dict(sealed_at_utc=datetime.now(timezone.utc).isoformat(),
            files=[dict(name=p.relative_to(directory).as_posix(),bytes=p.stat().st_size,sha256=exp.sha(p)) for p in sorted(directory.rglob('*')) if p.is_file() and p!=manifest],
            original_and_prior_evidence_unchanged=True,integration_performed=False),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(exp.json.dumps(dict(conclusion_es=conclusions,model_comparison=review['model_comparison'],
        controls=review['negative_rewrite_eligibility'],preservation=preserved,report=str(HERE/'REPORT.txt')),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
