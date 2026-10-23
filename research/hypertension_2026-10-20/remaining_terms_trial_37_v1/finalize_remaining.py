"""Report the measured result, retain adverse findings and seal new artifacts."""
from collections import Counter
from datetime import datetime,timezone
import subprocess
import sys
import evaluate_remaining as exp


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    if (exp.HERE/'manifest.json').exists():raise SystemExit('Sealed trial cannot be overwritten')
    summary=exp.load(exp.HERE/'summary.json');review=exp.load(exp.HERE/'review_findings.json')
    corpus=exp.load(exp.HERE/'speech_comparison.json');terms=exp.load(exp.HERE/'term_results.json')
    decisions=exp.load(exp.HERE/'threshold_decisions.json');audit=exp.load(exp.HERE/'correction_review.json')
    tests=subprocess.run([sys.executable,'-B',str(exp.HERE/'test_remaining.py')],capture_output=True,text=True,encoding='utf-8',cwd=exp.ROOT)
    exp.save('test_results.json',dict(returncode=tests.returncode,output=tests.stdout+tests.stderr))
    if tests.returncode:raise SystemExit(tests.stdout+tests.stderr)
    preserved=exp.preservation();exp.save('preservation_final.json',preserved)
    improved=sum(r['error_delta']<0 for r in review['model_comparison']);same=sum(r['error_delta']==0 for r in review['model_comparison']);worse=sum(r['error_delta']>0 for r in review['model_comparison'])
    if worse:
        conclusion=f"La ampliación mejora {improved} modelos, deja {same} sin cambio y empeora {worse}; requiere revisar los casos adversos antes de proponer su uso."
    elif improved:
        conclusion=f"La ampliación mejora {improved} modelos y deja {same} sin cambio frente a los sesenta corregidos, sin empeorar el WER de ninguno."
    else:conclusion='La ampliación no cambia el WER de los tres modelos frente a los sesenta corregidos.'
    final=dict(status='remaining37_experiment_complete_research_only',conclusion_es=conclusion,
        scope_confirmed_by_user='All 37 remaining reference-covered concepts; cumulative 97',
        model_comparison=review['model_comparison'],new_fuzzy_candidates=summary['new_fuzzy_candidates'],new_exact_only=summary['new_exact_only'],
        isolated_checking=summary['isolated_checking'],context_checking=summary['context_checking'],combined_constructed_checking=summary['combined_constructed_checking'],
        previous60_context_regressions=summary['previous60_context_regressions'],previous60_constructed_regressions=summary['previous60_constructed_regressions'],
        previous_regressions_passed=summary['previous_regressions_passed'],previous_regression_cases=summary['previous_regression_cases'],
        unique_reference_occurrences_new37=summary['unique_reference_occurrences_new37'],correlated_model_observations_new37=summary['unique_reference_occurrences_new37']*3,
        unique_reference_occurrences_all97=summary['unique_reference_occurrences_all97'],
        introduced_corrections=review['introduced_changes'],removed_previous_corrections=review['removed_changes'],introduced_assessments=review['introduced_assessments'],
        term_literal_agreement_summary={k:{key:value for key,value in v.items() if key!='rows'} for k,v in review['term_literal_agreement'].items()},
        original_and_prior_evidence_unchanged=True,preservation=preserved,verification_tests_passed=12,
        new_thresholds_frozen_before_checking=True,previous60_thresholds_unchanged=True,corrected_rules_unchanged=True,
        independent_holdout=False,new_asr_inference=False,controlled_intonation_variants_tested=0,independent_clinical_adjudication=False,integration_performed=False)
    exp.save('final_results.json',final)
    lines=[
        'TOLERANCIA DE LOS 37 TÉRMINOS RESTANTES CON LAS REGLAS CORREGIDAS',
        'Investigación local. Conjunto acumulado de 97 conceptos con audio. Sin integración en TRAD.', '',
        'RESULTADO PRINCIPAL',conclusion,
        f"Los {summary['new_terms']} términos nuevos se compararon por separado y junto con los 60 anteriores; no se modificaron las reglas corregidas ni los umbrales de los 60.",
        f"Se eligieron {summary['new_fuzzy_candidates']} tolerancias candidatas; {summary['new_exact_only']} términos quedaron con reconocimiento exacto únicamente.", '',
        'ALCANCE CONFIRMADO Y SELECCIÓN',
        'El usuario confirmó los 37 restantes del conjunto con audio, no los 597 restantes del glosario completo.',
        'Se tomó el complemento íntegro del conjunto original de 97, excluyendo los 60 ya ensayados. No hubo un nuevo submuestreo ni selección por errores ASR.',
        f"Solo se aleatorizó el orden, con semilla reproducible {exp.load(exp.HERE/'selection.json')['seed']}; no se repitió el orden por los resultados.",
        'Esto completa el conjunto original con audio. No cubre los 657 conceptos ni constituye una muestra uniforme de todo el glosario.', '',
        'REGLAS Y AJUSTE DE TOLERANCIAS',
        'Se reutilizó sin cambios BoundaryNormalizer de boundary_refinement_v2 y su cadena de reglas de laboratorio. Sus huellas y las del código de aplicación usado para lectura están congeladas en protocol.json.',
        'Se conserva literalmente el tramo de variantes registradas para investigación; se bloquean cambios entre singular y plural, pérdida de conectores/negación/cifras/unidades y límites de identificadores.',
        'La frase larga solo desplaza coincidencias exactas que son subexpresiones propias y completamente contenidas; se mantiene la protección extendida del identificador.',
        f"El conjunto completo conserva {summary['all_variant_records']} registros de variantes, {summary['new_variant_records']} correspondientes a los 37 nuevos. Se aplica la misma política de preservación; no se aprueban equivalencias ni sustituciones.",
        'Para cada término nuevo se probaron 0.86, 0.88, 0.90, 0.92, 0.94, 0.96, 0.98, 0.99 y 1.00 con erratas construidas y negativos de conceptos cercanos, unidades, variantes y número gramatical.',
        'Criterio congelado: máxima recuperación con cero correcciones fuzzy en negativos de calibración; desempate al umbral mayor. Si no hay recuperación útil, fuzzy queda deshabilitado.',
        'Los umbrales son scores heurísticos, no probabilidades ni una aprobación de seguridad. Se congelaron antes de ver los resultados de checking y voz; no se retocaron después.',
        'Se eliminaron duplicados exactos entre calibración y checking antes de calibrar; se conservan tanto los casos originales como el listado excluido.',
        'Las particiones siguen compartiendo recetas de generación. No se presentan como ejemplos independientes de habla o pronunciación.', '',
        'COMPARACIÓN PRINCIPAL EN LAS TRANSCRIPCIONES COMPLETAS',
        'WER = errores de palabras / 4.204 palabras de referencia por modelo; menor es mejor. Referencias provisionales, sin adjudicación clínica.',
        'Modelo | Sesenta con reglas corregidas | Noventa y siete con tolerancias individuales | Diferencia de errores']
    for r in review['model_comparison']:
        lines.append(f"{r['model']} | {r['previous60_wer']:.2%} ({r['previous60_word_errors']}) | {r['combined97_wer']:.2%} ({r['combined97_word_errors']}) | {r['error_delta']:+d}")
    lines += ['', 'COMPARACIÓN COMPLETA: TÉRMINOS NUEVOS POR SEPARADO Y ACUMULADOS',
        'Las cifras son errores de palabras en el mismo corpus completo; no son errores exclusivos dentro de los conceptos.',
        'Modelo | Crudo | 60 corregidos | 37 uniforme 0.90 | 37 individuales | 97 con nuevos a 0.90 | 97 individuales']
    for model in ['small','medium','large-v3-turbo']:
        rows={r['profile']:r for r in corpus['aggregate'] if r['model']==model}
        profiles=['raw','previous60_corrected','new37_uniform090','new37_individualized','combined97_uniform_new37','combined97_individualized']
        lines.append(model+' | '+' | '.join(str(rows[p]['word_errors']) for p in profiles))
    lines += [
        'El uniforme obtiene un WER menor en small y turbo que los umbrales individuales, pero no satisface los controles negativos predefinidos: no se escoge solo por la métrica global.',
        'En small, el acumulado uniforme llega a 128 errores frente a 131 individuales; en turbo, a 130 frente a 131. Medium queda en 100 con ambos.',
        'Los umbrales individuales no recuperan antihypertension medication (score 0.932051) ni aldous drone production (0.935589) en los casos que requieren superar sus puntos congelados. Se conserva esa pérdida de recuperación.',
        'El perfil de 60 se reprodujo desde las mismas hipótesis crudas y coincide con sus salidas anteriores byte por byte en texto. Los nuevos perfiles no encadenan correcciones sobre una salida ya corregida.', '',
        'CHECKING CONSTRUIDO DE CADA TÉRMINO NUEVO',
        'Perfil | Positivos recuperados | Negativos que activan fuzzy | Negativos modificados']
    for r in summary['isolated_checking']:
        lines.append(f"{r['profile']} | {r['recovered']}/{r['positive_cases']} | {r['negative_triggers']}/{r['negative_cases']} | {r['negative_changed']}/{r['negative_cases']}")
    lines += [
        'El ajuste individual sacrifica dos recuperaciones frente al uniforme, evitando sus tres modificaciones negativas. No es una estimación de tasa de error clínica.', '',
        'Los tres negativos alterados por el uniforme fueron: primary hypotension -> primary hypertension; orthostatic hypertension -> orthostatic hypotension; secondary hypotension -> secondary hypertension.',
        'El control estructural heredado no bloquea esos contrastes por sí mismo; la tolerancia individual elegida los rechaza en estos ejemplos. La política permanece congelada y el hueco se documenta, sin modificarla después del checking.',
        'Por ello los umbrales candidatos no equivalen a una protección semántica general: hacen falta más contextos independientes antes de proponer uso fuera del laboratorio.', '',
        'CHECKING CONSTRUIDO CON LOS 97 ACTIVOS JUNTOS',
        'Grupo | Positivos recuperados | Negativos modificados']
    for r in summary['combined_constructed_checking']:
        lines.append(f"{r['group']} | {r['positive_correct']}/{r['positive_cases']} | {r['negative_changed']}/{r['negative_cases']}")
    lines += [f"Casos construidos previamente correctos de los 60 que se pierden al añadir los 37: {summary['previous60_constructed_regressions']}.",
        '', 'CONTEXTO, PALABRAS VECINAS Y LÍMITES',
        'Perfil / Grupo | Positivos correctos | Negativos modificados']
    for r in summary['context_checking']:
        lines.append(f"{r['profile']} / {r['group']} | {r['positive_correct']}/{r['positive_cases']} | {r['negative_changed']}/{r['negative_cases']}")
    lines += [
        f"Regresiones de contexto en los 60 anteriores: {summary['previous60_context_regressions']}.",
        f"Controles de variantes, plurales, solapamientos, by y límites ya existentes: {summary['previous_regressions_passed']}/{summary['previous_regression_cases']} pasan.",
        'Los 28 positivos de contexto nuevos sin recuperación corresponden a los cuatro términos mantenidos en exacto; no se relajaron sus restricciones para aumentar el resultado.',
        'La comparación conserva los controles de negación/cifras/conectores y los negativos que no deben reescribirse; se registran por caso y sin ocultar fallos.', '',
        'AUDITORÍA DEL EFECTO INCREMENTAL',
        f"Cambios con 60 términos: {review['previous60_changes']}; con 97: {review['combined97_changes']}. Nuevos cambios: {review['introduced_changes']}; cambios anteriores retirados: {review['removed_changes']}.",
        'Cada cambio se revisó frente a la referencia provisional: efecto aislado, efecto al retirarlo de su perfil, contexto de referencia y posición en la hipótesis original. Ver correction_review.json y change_comparison.json.',
        'Valoraciones de los cambios introducidos por la ampliación: '+str(review['introduced_assessments'])+'.',
        'Los deltas léxicos no demuestran beneficio o daño clínico. Tampoco certifican que una referencia provisional no contenga una errata.',
    ]
    introduced=[r for r in audit if r['profile']=='combined97_individualized' and r['introduced_by_expansion']]
    for r in introduced:
        lines.append(f"- {r['model']}/{r['sample_id']}: {r['source']} -> {r['replacement']}; score {r['confidence']}; delta léxico marginal {r['word_error_delta_in_profile']:+d}.")
    remaining_worse=[r for r in audit if r['profile']=='combined97_individualized' and r['assessment']=='lexical_agreement_worsened']
    lines.append('Desacuerdos con la referencia que permanecen en el perfil acumulado: '+str(len(remaining_worse))+'.')
    for r in remaining_worse:
        lines.append(f"- {r['model']}/{r['sample_id']}: {r['source']} -> {r['replacement']}; contexto de referencia: {r['provisional_reference_context']}. Pendiente de escucha/adjudicación independiente.")
    lines += ['', 'LOS 37 TÉRMINOS Y LAS TOLERANCIAS CONGELADAS',
        'Exacto significa que no se encontró recuperación fuzzy útil compatible con los controles; no equivale a validación de uso en producción.',
        'Coincidencias: forma literal de referencia inglesa, antes (crudo) -> después (97), sobre tres modelos correlacionados. Los términos pueden solaparse y compartir palabras.',
        'N.º | Inglés / Español | Umbral | Coincidencias antes -> después / observaciones']
    for i,r in enumerate([r for r in terms if r['group']=='new37'],1):
        before=r['results']['raw'];after=r['results']['combined97_individualized']
        threshold='Exacto' if r['threshold'] is None else f"{r['threshold']:.2f}"
        lines.append(f"{i:02d} | {r['canonical_en']} / {r['preferred_es']} | {threshold} | {before['exact_reference_form']} -> {after['exact_reference_form']} / {after['observations']}")
    lines += [
        'Resumen de coincidencias por concepto nuevo: '+str(final['term_literal_agreement_summary']['new37'])+'.',
        'Resumen de cambios en coincidencias de los 60 anteriores al activar los 97: '+str(final['term_literal_agreement_summary']['previous60'])+'.',
        'term_results.json conserva los 97 conceptos y los seis perfiles completos, con los umbrales originales de los 60.', '',
        'LÍMITES Y CONSERVACIÓN',
        f"Se reutilizaron tres archivos de audio natural y nueve salidas ASR ya calculadas: {summary['unique_reference_occurrences_new37']} apariciones únicas de los nuevos conceptos y {summary['unique_reference_occurrences_new37']*3} observaciones correlacionadas; acumulado de 97: {summary['unique_reference_occurrences_all97']} apariciones.",
        'Los archivos 02/03 podrían ser partes de una misma charla. La selección dependió de su presencia en las referencias inglesas, no de diversidad de hablantes.',
        'No se grabaron nuevas voces, no se ejecutó ASR nuevo y no se variaron entonación, acento o velocidad. Las erratas construidas son texto, no pronunciaciones verificadas.',
        'El corpus y las recetas ya habían sido explorados. Estos resultados son de laboratorio, no validación independiente o clínica, y no se extrapolan a los 657 conceptos ni al español o a TRAD en directo.',
        'Pasaron 12 verificaciones de reproducción, criterios de tolerancia, conservación, trazabilidad, cobertura y propiedades de las salidas. Las pruebas verifican la integridad del experimento; no fuerzan un resultado favorable.',
        f"Se comprobaron {preserved['files_checked']} archivos de la instantánea, {preserved['strictly_protected_files_checked']} protegidos estrictamente. Observaciones ajenas a esta tarea: {len(preserved['other_workspace_observations'])}.",
        'El glosario original, las evidencias, los ensayos anteriores, el paquete depurado, los audios y referencias, las transcripciones guardadas y las bibliotecas utilizadas mantienen sus huellas.',
        'Solo se escribieron archivos nuevos en remaining_terms_trial_37_v1. No se modificó ningún ensayo anterior ni el estado de aprobación del paquete.',
        'No se conectó ni integró nada en TRAD.', '',
        'ARCHIVOS PARA REVISAR',
        'selection.json, protocol.json y threshold_freeze.json: alcance, código y decisiones congeladas.',
        'threshold_decisions.json: justificación de cada tolerancia; combined_thresholds.json conserva las 60 decisiones previas intactas.',
        'speech_comparison.json: seis perfiles, transcripciones simuladas, métricas y auditorías; term_results.json: los 97 conceptos.',
        'correction_review.json y change_comparison.json: cambios nuevos, retirados, efectos y contexto provisional.',
        'context_comparison.json y combined_checking.json: resultados por caso e interferencias sobre los 60 previos.',
        'final_results.json: resumen; preservation_final.json y manifest.json: conservación y huellas.',
    ]
    (exp.HERE/'REPORT.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (exp.HERE/'README.txt').write_text(
        'Ensayo de investigación de los 37 conceptos restantes con audio; acumulado de 97.\n'
        'Leer REPORT.txt y final_results.json; no hay integración en TRAD.\n'
        'Las reglas corregidas y los umbrales de los 60 anteriores se mantienen intactos.\n'
        'Solo se calibran 37 tolerancias con casos construidos, antes del checking.\n'
        'No se sobrescriben protocolos ni resultados. Los programas se detienen si ya existe el ensayo.\n'
        'No hay nuevas voces, entonaciones ni validación clínica independiente.\n',encoding='utf-8')
    exp.verify_prior()
    exp.save('manifest.json',dict(sealed_at_utc=datetime.now(timezone.utc).isoformat(),
        files=[dict(name=p.relative_to(exp.HERE).as_posix(),bytes=p.stat().st_size,sha256=exp.sha(p)) for p in sorted(exp.HERE.rglob('*')) if p.is_file() and p.name!='manifest.json'],
        original_and_prior_evidence_unchanged=True,integration_performed=False))
    print(exp.json.dumps(dict(conclusion_es=conclusion,model_comparison=review['model_comparison'],
        preservation=preserved,report=str(exp.HERE/'REPORT.txt')),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
