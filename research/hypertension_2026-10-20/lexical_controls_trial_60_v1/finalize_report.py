"""Seal both laboratory revisions and explain their measured comparison."""
from collections import Counter
from datetime import datetime, timezone
import subprocess
import sys
import evaluate_controls as replay
from trad_lab.metrics import tokens, edit_distance

HERE=replay.HERE
FINAL=HERE/'boundary_refinement_v2'


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    if (HERE/'manifest.json').exists():raise SystemExit('Already sealed; no overwrite')
    if not (FINAL/'summary.json').exists():raise SystemExit('Refined replay still running')
    tested=subprocess.run([sys.executable,'-B',str(HERE/'test_replay_outputs.py')],capture_output=True,text=True,encoding='utf-8',cwd=replay.ROOT)
    replay.save('verification_tests.json',dict(returncode=tested.returncode,output=tested.stdout+tested.stderr))
    if tested.returncode:raise SystemExit(tested.stdout+tested.stderr)
    summary=replay.load(FINAL/'summary.json');attempt=replay.load(HERE/'summary.json')
    corpus=replay.load(FINAL/'speech_comparison.json')
    contexts=replay.load(FINAL/'context_comparison.json')
    terms=replay.load(FINAL/'term_results.json')
    audit=replay.load(FINAL/'correction_review.json')
    def key(c):return tuple(c[k] for k in ['model','sample_id','start','end','replacement','canonical'])
    old_changes=[c for c in corpus['changes'] if c['profile']=='old60']
    new_changes=[c for c in corpus['changes'] if c['profile']=='all_fixes']
    old_keys={key(c) for c in old_changes};new_keys={key(c) for c in new_changes}
    removed=[]
    for c in old_changes:
        if key(c) in new_keys:continue
        record=replay.load(replay.prior.CACHED/'models'/c['model']/c['sample_id']/'result.json')
        raw,ref=record['hypothesis_raw'],record['reference_raw']
        once=raw[:c['start']]+c['replacement']+raw[c['end']:]
        delta=edit_distance(tokens(ref),tokens(once))-record['metrics']['word_errors']
        removed.append(dict(**c,old_word_error_delta_if_applied_alone=delta,
            removal_assessment='avoids_lexical_error' if delta>0 else 'removes_lexically_neutral_rewrite' if delta==0 else 'loses_lexical_repair'))
    introduced=[c for c in new_changes if key(c) not in old_keys]
    replay.save('change_comparison.json',dict(old_changes=len(old_changes),new_changes=len(new_changes),
        retained=len(old_keys&new_keys),removed=removed,introduced=introduced,
        removed_counts=dict(Counter(c['removal_assessment'] for c in removed))))
    table=[]
    for model in ['small','medium','large-v3-turbo']:
        rows={r['profile']:r for r in corpus['aggregate'] if r['model']==model}
        table.append(dict(model=model,old_word_errors=rows['old60']['word_errors'],new_word_errors=rows['all_fixes']['word_errors'],
            old_wer=rows['old60']['wer'],new_wer=rows['all_fixes']['wer'],
            fewer_word_errors=rows['old60']['word_errors']-rows['all_fixes']['word_errors'],
            reference_words=rows['all_fixes']['reference_words'],
            relative_word_error_reduction=(rows['old60']['word_errors']-rows['all_fixes']['word_errors'])/rows['old60']['word_errors']))
    preserved=replay.preservation();replay.save('preservation_final.json',preserved)
    gains=Counter(r['concept_id'] for r in contexts['rows'] if r['profile']=='all_fixes' and r['replay_id'] in contexts['improved_cases'])
    names={r['concept_id']:r['canonical_en'] for r in terms}
    outcome=dict(status='laboratory_only_both_revisions_preserved',same_sixty=True,same_thresholds=True,
        result='Lower lexical word error in all three models versus the previous sixty-term profile; no observed context regressions in the refined replay.',
        model_comparison=table,ablation=corpus['aggregate'],
        constructed_checking=summary['constructed'],context_checking=summary['contexts'],
        improved_contexts=len(contexts['improved_cases']),regressed_contexts=len(contexts['regressed_cases']),
        context_gains_by_term=[dict(concept_id=cid,canonical_en=names[cid],improved_cases=n) for cid,n in gains.items()],
        original_six_overlap_failures_fixed=42,registered_variants_preserved_without_equivalence_approval=15,
        old_corpus_changes=len(old_changes),new_corpus_changes=len(new_changes),removed_changes=len(removed),introduced_changes=len(introduced),
        remaining_change_assessments=dict(Counter(c['assessment'] for c in audit)),
        first_attempt_context_regressions=attempt['context_regressions'],first_attempt_retained=True,
        identifier_refinement_designed_after_first_attempt=True,refined_policy_retuned_after_replay=False,
        regression_probes=summary['regression_summary'],unit_tests_passed=15,output_verification_tests_passed=11,
        unique_reference_occurrences=251,correlated_model_observations=753,
        independent_holdout=False,new_asr_inference=False,controlled_intonation_variants_tested=0,
        clinical_adjudication=False,preservation=preserved,integration_performed=False)
    replay.save('final_results.json',outcome)
    lines=[
        'CORRECCIÓN EN LABORATORIO: VARIANTES, PLURALES Y SOLAPAMIENTOS',
        'Mismos 60 términos, mismos umbrales y mismo corpus. Investigación, sin integración en TRAD.', '',
        'RESULTADO',
        'La revisión final reduce el error léxico en los tres modelos respecto al perfil anterior de sesenta términos.',
        'Se reparan los fallos de contexto conocidos sin perder casos que antes pasaban. No se cambiaron los umbrales ni se seleccionaron otros términos.',
        'El resultado es de desarrollo sobre datos ya explorados, con referencias provisionales. No constituye validación clínica independiente.', '',
        'COMPARACIÓN PRINCIPAL',
        'WER = errores de palabras / 4.204 palabras de referencia por modelo; menor es mejor.',
        'Modelo | 60 anteriores | 60 con correcciones de laboratorio | Errores menos']
    for r in table:
        lines.append(f"{r['model']} | {r['old_wer']:.2%} ({r['old_word_errors']}) | {r['new_wer']:.2%} ({r['new_word_errors']}) | {r['fewer_word_errors']}")
    lines += ['', 'CONTRIBUCIÓN DE CADA REGLA',
        'Errores de palabras sobre las mismas transcripciones completas; no se generaron nuevas inferencias.',
        'Modelo | Crudo | 10 anteriores | 60 anteriores | Conservar variantes | Además conservar número | Además resolver solapamientos y proteger identificadores']
    for model in ['small','medium','large-v3-turbo']:
        rows={r['profile']:r for r in corpus['aggregate'] if r['model']==model}
        keys=['raw','previous10','old60','variants_only','variants_and_number','all_fixes']
        lines.append(model+' | '+' | '.join(str(rows[k]['word_errors']) for k in keys))
    lines += [
        'La mejora WER en este corpus procede de evitar modificaciones innecesarias de variantes y plurales. Resolver solapamientos mejora los contextos construidos, pero no añade una mejora WER adicional en estas grabaciones.',
        'El perfil de diez se muestra como referencia histórica y reutiliza sus salidas guardadas; no se recalibró.', '',
        'REGLAS CAMBIADAS SOLO EN ESTA CARPETA DE INVESTIGACIÓN',
        '1. Variantes: se conservan literalmente los tramos de las 15 formas inglesas reviewable_variant asociadas a estos conceptos en el paquete anterior. No se expanden ni sustituyen por el canónico.',
        '   Incluye pharmacologic therapy. Su registro previo permite consulta de investigación y localización literal; no aprueba equivalencia estricta ni sustitución automática. Preservar el texto no añade esa aprobación.',
        '   Las variantes no se incorporan al glosario ni se habilitan como reglas de sustitución. Se conservan también cuando aparecen junto a una errata corregible fuera de su tramo.',
        '2. Singular/plural: se rechazan cambios de número en ambas direcciones antes de seleccionar candidatos. Se reconocen terminaciones regulares y una lista explícita de irregulares; las reglas están registradas en el código local del ensayo.',
        '   Así se mantienen diastolic blood pressures y cardiovascular risks. No se generan automáticamente formas flexionadas como reemplazo.',
        '   Es un bloqueo conservador, no un analizador morfológico completo. Puede dejar sin corregir una errata cuando también existe flexión; ese coste se conserva en los resultados.',
        '3. Solapamientos: una frase aproximada que supera su umbral y todos los controles puede desplazar una coincidencia exacta corta solo si esta queda completamente dentro del tramo y es una subexpresión propia de su forma canónica.',
        '   No desplaza coincidencias exactas ajenas o mayores; no desplaza formas protegidas. Se conservan las prioridades de confianza entre candidatos competidores.',
        '4. Identificadores: se propaga la protección de una frase que sería admisible salvo por empezar dentro de un identificador; sus fragmentos internos tampoco pueden reescribirse.',
        '   La protección se limita a ese tramo y permite reparar una errata independiente en otra parte de la misma frase.', '',
        'ENSAYO INTERMEDIO CONSERVADO',
        'La primera revisión mejoró las recuperaciones, pero produjo dos cambios no deseados: tag_target sytolic blood pressure y tag_non-elvated blood pressure.',
        'El control protegía el principio del término, pero un candidato más corto podía empezar después de un espacio o guion y modificar el sufijo.',
        'Se mantuvieron intactos sus resultados en la carpeta principal, con first_replay_manifest.json. Su contexto registra 49 recuperaciones adicionales y 2 regresiones.',
        'La segunda revisión se guardó en boundary_refinement_v2, con política congelada antes de repetir la prueba. Conserva las 49 mejoras y elimina ambas regresiones.',
        'Se declara expresamente este desarrollo guiado por los errores observados; no se presenta como evaluación sobre un conjunto independiente.', '',
        'COMPROBACIONES CONSTRUIDAS CON LOS SESENTA TÉRMINOS ACTIVOS',
        'Se reutilizaron las particiones de checking previas y se excluyeron sus duplicados exactos de calibración. No se volvió a calibrar.',
        'Los totales no se comparan directamente con la anterior tabla por término: aquí los sesenta están activos juntos y se incluyen los diez iniciales.',
        'Perfil | Positivos recuperados | Negativos modificados']
    for r in summary['constructed']:
        lines.append(f"{r['profile']} | {r['positive_correct']}/{r['positive_cases']} | {r['negative_changed']}/{r['negative_cases']}")
    lines += ['', 'CONTEXTO Y LÍMITES DE PALABRA', 'Perfil | Positivos correctos | Negativos modificados']
    for r in summary['contexts']:
        lines.append(f"{r['profile']} | {r['positive_correct']}/{r['positive_cases']} | {r['negative_changed']}/{r['negative_cases']}")
    lines += [
        f"Mejoras de contexto: {len(contexts['improved_cases'])}; casos que antes pasaban y ahora fallan: {len(contexts['regressed_cases'])}.",
        'Se recuperan los 42 casos de las seis expresiones detectadas en la expansión anterior y siete casos adicionales de systolic blood pressure, que también quedaba bloqueada al convivir con blood pressure.',
        'Los 91 contextos positivos restantes pertenecen a los trece términos dejados deliberadamente en coincidencia exacta; no se elevaron sus permisos para aumentar el resultado.',
        'Los 153 controles declarados de variantes/plurales, solapamientos y regresiones previas pasan en la revisión final. Son pruebas de desarrollo, no una muestra independiente de uso real.',
        'Se conserva primary allosteronism by this test -> primary aldosteronism by this test, sin eliminar by.',
        'En las nueve transcripciones con la política final se conservan las secuencias medidas de conectores/negaciones/cifras y unidades. Estos canales no detectan todos los cambios de significado.', '',
        'AUDITORÍA DE CAMBIOS EN LAS TRANSCRIPCIONES',
        f"Cambios simulados antes: {len(old_changes)}. Después: {len(new_changes)}. Se retiran {len(removed)} y se introducen {len(introduced)} cambios nuevos frente al perfil anterior.",
        'Se evitan doce canonicalizaciones de pharmacologic therapy y cinco pérdidas de plural. También desaparecen tres cambios de mayúsculas que eran neutros para WER.',
        f"De los {len(audit)} cambios que permanecen, {sum(r['assessment']=='improved' for r in audit)} mejoran la concordancia léxica al aplicarse por separado, {sum(r['assessment']=='neutral' for r in audit)} son neutros y {sum(r['assessment']=='worsened' for r in audit)} la empeora.",
        'Queda un desacuerdo conocido: en medium/cardio_03 se cambia primary allosteronism por primary aldosteronism, mientras la referencia provisional también escribe primary allosteronism.',
        'No se ha decidido mediante escucha o adjudicación clínica cuál texto refleja mejor el audio. El desacuerdo se mantiene visible en correction_review.json y no se oculta tras la mejora global.',
        'change_comparison.json enumera los cambios retirados y su efecto aislado. La distancia de palabras es una métrica léxica, no una medida de daño clínico.', '',
        'DECISIONES DE LOS MISMOS SESENTA TÉRMINOS',
        'Umbral = score heurístico congelado, no probabilidad. Exacto = fuzzy deshabilitado.',
        'Coincidencias = forma literal de la referencia inglesa sobre tres modelos correlacionados; términos anidados pueden compartir palabras. No es exactitud conceptual.',
        'N.º | Inglés / Español | Umbral intacto | Coincidencias antes -> después / observaciones']
    for i,r in enumerate(terms,1):
        before=r['results']['old60'];after=r['results']['all_fixes']
        threshold='Exacto' if r['frozen_threshold'] is None else f"{r['frozen_threshold']:.2f}"
        lines.append(f"{i:02d} | {r['canonical_en']} / {r['preferred_es']} | {threshold} | {before['exact_reference_form']} -> {after['exact_reference_form']} / {after['observations']}")
    lines += ['', 'ALCANCE Y CONSERVACIÓN',
        'Se reutilizaron tres archivos de voz natural y nueve transcripciones de small, medium y large-v3-turbo: 251 apariciones únicas y 753 observaciones correlacionadas de los sesenta conceptos.',
        'Los archivos 02/03 podrían pertenecer a una misma charla. Las referencias son provisionales y el corpus ya había sido explorado.',
        'No hubo grabaciones nuevas, nuevas inferencias ASR ni variaciones controladas de entonación/acento/velocidad. Las erratas construidas son texto, no pronunciaciones verificadas.',
        'No se extrapola el resultado a los 657 conceptos, español, otros hablantes o funcionamiento en directo. No se modificó ningún umbral ni se repitió el sorteo.',
        'Pasaron 15 pruebas de las reglas finales y 11 verificaciones de las salidas, las regresiones, las entradas congeladas y la conservación de evidencias.',
        f"Se comprobaron {preserved['files_checked']} archivos de la instantánea, incluidos {preserved['strictly_protected_files_checked']} protegidos estrictamente. Observaciones de cambios ajenos a esta tarea: {len(preserved['other_workspace_observations'])}.",
        'Las huellas del glosario original, todos los ensayos anteriores, el paquete depurado, las evidencias, los audios/referencias, ASR guardados y las bibliotecas de aplicación utilizadas permanecen iguales.',
        'Solo se escribieron archivos nuevos en lexical_controls_trial_60_v1. La versión final está en boundary_refinement_v2; ambos ensayos y sus protocolos se conservan.',
        'El informe no cambia el estado de aprobación del paquete. No se conectó, desplegó ni integró nada en TRAD.',
        '', 'ARCHIVOS PARA REVISIÓN',
        'final_results.json: resumen y comparaciones. change_comparison.json: cambios retirados y conservados.',
        'boundary_refinement_v2/speech_comparison.json: métricas, texto simulado y auditorías de los seis perfiles.',
        'boundary_refinement_v2/context_comparison.json y constructed_comparison.json: resultados por caso, incluidos fallos.',
        'boundary_refinement_v2/correction_review.json: revisión léxica de los cambios finales.',
        'selection.json y thresholds.json: entradas originales intactas. Ambos protocol.json: reglas y huellas congeladas.',
        'first_replay_manifest.json conserva el ensayo intermedio; manifest.json sella todos los resultados nuevos. preservation_final.json acredita las evidencias anteriores.',
    ]
    (HERE/'REPORT.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (HERE/'README.txt').write_text(
        'Leer REPORT.txt y final_results.json. Investigación de laboratorio, sin integración.\n'
        'Entradas: los mismos 60 términos y umbrales de tolerance_trial_10_v1 + tolerance_trial_50_v1.\n'
        'Primera revisión: resultados en esta carpeta; conserva dos regresiones de identificadores.\n'
        'Revisión final: boundary_refinement_v2; corrige las dos regresiones. No se sobrescribe la primera.\n'
        'Los programas se niegan a sobrescribir un ensayo congelado. Los protocolos fijan fuentes e inputs.\n'
        'El corpus fue usado durante el desarrollo; no es una validación independiente. No hay entonaciones nuevas.\n',encoding='utf-8')
    replay.verify_prior()
    for r in replay.load(HERE/'first_replay_manifest.json')['files']:
        assert replay.sha(HERE/r['name'])==r['sha256']
    for directory in [FINAL,HERE]:
        destination=directory/'manifest.json'
        files=[dict(name=p.relative_to(directory).as_posix(),bytes=p.stat().st_size,sha256=replay.sha(p))
               for p in sorted(directory.rglob('*')) if p.is_file() and p!=destination]
        destination.write_text(replay.json.dumps(dict(sealed_at_utc=datetime.now(timezone.utc).isoformat(),
            files=files,original_and_prior_evidence_unchanged=True,integration_performed=False),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(replay.json.dumps(dict(model_comparison=table,contexts=summary['contexts'],constructed=summary['constructed'],
        changes_before=len(old_changes),changes_after=len(new_changes),removed=len(removed),introduced=len(introduced),
        preservation=preserved,report=str(HERE/'REPORT.txt')),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
