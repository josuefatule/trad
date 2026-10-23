"""Create an auditable report and manifest for this new research folder only."""
from datetime import datetime, timezone
import evaluate_50 as trial

HERE=trial.HERE
load=trial.prior.load
save=trial.save


def main():
    trial.sys.stdout.reconfigure(encoding='utf-8')
    if (HERE/'manifest.json').exists():raise SystemExit('Sealed experiment already exists')
    trial.verify_inputs()
    s=load(HERE/'summary.json');review=load(HERE/'review_findings.json')
    selection=load(HERE/'selection.json');terms=load(HERE/'term_results.json')
    decisions=load(HERE/'threshold_decisions.json');freeze=load(HERE/'threshold_freeze.json')
    assert trial.prior.sha(HERE/'threshold_decisions.json')==freeze['decisions_sha256']
    assert load(HERE/'test_results.json')['returncode']==0
    audit=load(HERE/'correction_review.json');overlaps=load(HERE/'overlap_diagnostics.json')
    preserve=trial.preserve();save('preservation_final.json',preserve)
    aggregate=s['corpus_aggregate']
    table=[]
    for model in ['small','medium','large-v3-turbo']:
        rows={r['profile']:r for r in aggregate if r['model']==model}
        delta=rows['combined60_individualized_guarded']['word_errors']-rows['previous10_guarded']['word_errors']
        table.append(dict(model=model,previous10_word_errors=rows['previous10_guarded']['word_errors'],
            combined60_word_errors=rows['combined60_individualized_guarded']['word_errors'],
            delta_word_errors=delta,reference_words=4204,
            previous10_wer=rows['previous10_guarded']['wer'],combined60_wer=rows['combined60_individualized_guarded']['wer']))
    assert [r['delta_word_errors'] for r in table]==[4,4,5]
    assert len(terms)==50 and len({r['concept_id'] for r in terms})==50
    assert all(r['concept_id'] not in selection['excluded_previous_ten_ids'] for r in terms)
    assert s['previous_regressions_passed'] and len(load(HERE/'previous_regressions_combined60.json'))==7
    assert sum(r['observed_pharmacologic_canonicalization'] for r in audit)==12
    assert sum(r['observed_plural_to_singular'] for r in audit)==5
    final=dict(experiment='Fifty additional randomly selected English terms; research only',
        conclusion_es='La ampliación no mejora el error léxico global frente a los diez términos con controles; no está lista para incorporarse.',
        selected_new_terms=50,random_pool=87,previous_ten_excluded=True,seed=selection['seed'],
        individualized_fuzzy_candidates=37,exact_only=13,threshold_grid=load(HERE/'protocol.json')['grid'],
        unique_reference_occurrences_new50=217,correlated_model_observations_new50=651,
        corpus_reference_words_per_model=4204,incremental_comparison=table,
        synthetic_comparison=s['synthetic_checking'],context_comparison=[{k:v for k,v in r.items() if k!='failed_case_ids'} for r in s['context_checking']],
        correction_review=review,previous_regressions_passed=7,verification_tests_passed=12,
        preservation=preserve,postchecking_diagnostics_not_used_to_retune=True,
        original_glossary_sha256=trial.prior.sha(trial.ROOT/'glossaries/medical_base_en.json'),
        no_new_audio_or_asr_inference=True,controlled_intonation_variants_tested=0,
        independent_clinical_validation=False,integration_performed=False)
    save('final_results.json',final)
    lines=[
        'AMPLIACIÓN DE TOLERANCIAS A OTROS 50 TÉRMINOS ALEATORIOS',
        'Investigación local; resultados simulados, sin integración en TRAD.', '',
        'RESULTADO PRINCIPAL',
        'La ampliación no mejora el error léxico global frente a los diez términos con controles de contexto y límites de palabra.',
        'Añade 4 errores en small, 4 en medium y 5 en large-v3-turbo. Se conserva el resultado desfavorable, sin repetir el sorteo ni retocar los umbrales después de verlo.',
        'Se estudiaron 50 términos nuevos y se comparó también el conjunto acumulado de 60.', '',
        'MUESTRA Y MÉTODO',
        'Muestreo uniforme sin reemplazo entre los 87 conceptos restantes de los 97 presentes en las referencias inglesas anteriores. Se excluyeron los diez ya estudiados.',
        f"Semilla reproducible: {selection['seed']}. No representa una muestra uniforme de los 657 conceptos completos: está limitada por la cobertura del corpus.",
        'Por término se probaron umbrales 0.86, 0.88, 0.90, 0.92, 0.94, 0.96, 0.98, 0.99 y 1.00 con los controles anteriores sin cambios.',
        'Se eligió la mayor recuperación de erratas construidas con cero disparos en negativos de calibración; desempate hacia el umbral más alto. Sin recuperación útil, se dejó solo coincidencia exacta.',
        'Resultado: 37 candidatos con tolerancia individual y 13 limitados a coincidencia exacta. Un score 1.00 no significa certeza médica ni coincidencia literal obligatoria.',
        'Los umbrales quedaron congelados antes de las comprobaciones. Se eliminaron duplicados exactos entre calibración y checking antes de elegirlos; se conservaron los casos originales y el listado excluido.',
        'Los ejemplos construidos de ambas particiones comparten recetas y no constituyen datos independientes de pronunciación.',
        'Las reglas se aplicaron antes de seleccionar coincidencias: contexto, conectores, negación, cifras/unidades, límites de palabra e identificadores y anclas léxicas. Su protección de plurales es parcial y falló en los casos indicados más abajo.',
        'No se habilitaron las alternativas del paquete para sustitución literal: el ensayo utiliza formas canónicas y decisiones experimentales. No se ha autorizado ninguna nueva equivalencia.', '',
        'COMPARACIÓN PRINCIPAL: DIEZ ANTERIORES FRENTE A SESENTA ACUMULADOS',
        'WER = errores de palabras / 4.204 palabras de referencia por modelo; menor es mejor. Referencias provisionales, no adjudicación clínica.',
        'Modelo | Antes: 10 con controles | Después: 60 con controles | Diferencia',
    ]
    for r in table:
        lines.append(f"{r['model']} | {r['previous10_wer']:.2%} ({r['previous10_word_errors']}) | {r['combined60_wer']:.2%} ({r['combined60_word_errors']}) | +{r['delta_word_errors']} errores")
    lines += ['', 'COMPARACIÓN COMPLETA SOBRE EL MISMO CORPUS',
        'Las cifras siguientes son errores de palabras. Todos los perfiles usan las mismas hipótesis crudas y referencias, sin generar nuevas inferencias.',
        'Modelo | Crudo | 10 con controles | 50 uniforme 0.90 con controles | 50 individual sin controles | 50 individual con controles | 60 individual con controles']
    for model in ['small','medium','large-v3-turbo']:
        rows={r['profile']:r for r in aggregate if r['model']==model}
        keys=['raw','previous10_guarded','new50_uniform090_guarded','new50_individualized_unguarded','new50_individualized_guarded','combined60_individualized_guarded']
        lines.append(model+' | '+' | '.join(str(rows[k]['word_errors']) for k in keys))
    lines += [
        'El acumulado de 60 conserva parte de la mejora anterior en small/medium frente al crudo, pero la ampliación por sí misma empeora los tres modelos.', '',
        'COMPROBACIONES CONSTRUIDAS',
        'Checking por término: 250 casos positivos y 667 negativos, sin duplicados exactos con calibración.',
        'Perfil | Positivos recuperados | Negativos que activan corrección fuzzy']
    for r in s['synthetic_checking']:
        lines.append(f"{r['profile']} | {r['recovered']}/{r['positive_cases']} | {r['negative_triggers']}/{r['negative_cases']}")
    lines += [
        'La tolerancia individual con controles evita los ocho disparos negativos del uniforme, a costa de recuperar 17 positivos menos. Cero de 667 no estima una tasa clínica ni garantiza ausencia de errores en texto real.',
        'Contexto con los 50 activos a la vez: 350 positivos y 250 negativos; incluyen by, palabras vecinas, negación exterior/interior, cifras e identificadores.',
        'Perfil | Contextos positivos correctos | Negativos modificados']
    for r in s['context_checking']:
        lines.append(f"{r['profile']} | {r['positive_correct']}/{r['positive_cases']} | {r['undesired_negative_changes']}/{r['negative_cases']}")
    lines += [
        'La prueba conjunta revela interferencias que no aparecen al calibrar cada término aislado.', '',
        'QUÉ EXPLICA EL EMPEORAMIENTO',
        'Se auditaron por separado los 27 cambios nuevos del perfil individual con controles: 4 mejoran la concordancia léxica con la referencia, 17 la empeoran y 6 son neutros.',
        'Doce cambios convierten pharmacologic therapy en pharmacological therapy: cuatro por modelo, que añaden cuatro errores por modelo frente a la grafía ya presente en la referencia.',
        'El registro previo UF0173 clasifica pharmacologic therapy como variante léxica de investigación, con localización literal de una fuente; niega aprobación de equivalencia estricta y de sustitución automática.',
        'No se interpreta una distancia léxica mayor entre estas grafías como daño clínico demostrado. El fallo de política es reescribir la forma sin demostrar un error de reconocimiento ni contar con aprobación de sustitución.',
        'Cinco cambios adicionales convierten plurales en singular: diastolic blood pressures en los tres modelos y cardiovascular risks en medium/turbo. Se pierde la forma gramatical observada.',
        'Los controles congelados protegían algunos pares explícitos (event/events, receptor/receptors, etc.), pero no pressure/pressures ni risk/risks. Los nuevos negativos de calibración tampoco cubrían todas las direcciones singular/plural.',
        'Por eso el buen resultado en negativos construidos no basta: el corpus descubre huecos que la prueba sintética no cubría.',
        'Las cuatro mejoras léxicas corresponden a hypokalamic metabolic alkalosis, renin-independent allosterone production, urinary allosterone y renin-independent aldosteron production.',
        'Cada cambio tiene contexto provisional, offsets, score y delta de error documentados en correction_review.json. No hubo revisión auditiva o clínica independiente.', '',
        'INTERFERENCIA ENTRE EXPRESIONES LARGAS Y CORTAS',
        '259 contextos positivos eran recuperables en calibración aislada; solo 217 se recuperan al activar los 50 términos juntos. Hay 42 fallos adicionales, siete por cada una de estas seis expresiones:']
    for r in overlaps:
        blockers=sorted({m['canonical'] for c in r['auto_fuzzy_intended_candidates'] for m in c['overlapping_reserved_exact']})
        lines += [f"- {r['canonical_en']}: {r['failed_contexts']} contextos; subexpresión reservada: {', '.join(blockers)}.",
                  f"  Ejemplo: {r['input']}", f"  Aislado: {r['isolated_output']}", f"  Con los 50: {r['all50_output']}"]
    lines += [
        'El motor reserva coincidencias exactas cortas antes de seleccionar la frase aproximada. La frase larga sí supera su umbral y pasa los controles, pero se descarta por solapamiento.',
        'Se verificó el mecanismo con offsets y candidatos en overlap_diagnostics.json, sin modificar el motor. Los otros 91 positivos no recuperados pertenecen a los 13 términos deliberadamente limitados a exacto.', '',
        'LOS 50 TÉRMINOS Y SUS DECISIONES',
        'Solo exacto significa que no hubo recuperación fuzzy útil compatible con los negativos de calibración y los controles congelados; no que el término haya sido validado para producción.',
        'Apariciones: coincidencia con la forma de referencia inglesa sobre tres modelos correlacionados; no equivale a exactitud conceptual o clínica. Pueden solaparse términos como blood pressure y diastolic blood pressure.',
        'N.º | Inglés / Español | Umbral candidato | Coincidencias crudo -> 50 con controles / observaciones']
    for i,r in enumerate(terms,1):
        threshold='Solo exacto' if r['threshold'] is None else f"{r['threshold']:.2f}"
        raw=r['results']['raw'];after=r['results']['new50_individualized_guarded']
        lines.append(f"{i:02d} | {r['canonical_en']} / {r['preferred_es']} | {threshold} | {raw['exact_reference_form']} -> {after['exact_reference_form']} / {raw['observations']}")
    lines += [
        '', 'ALCANCE Y DECISIÓN DE INVESTIGACIÓN',
        'Se reutilizaron tres archivos de voz natural (36,96 minutos únicos) y sus nueve salidas ASR previamente calculadas. Los archivos 02/03 podrían pertenecer a una misma charla.',
        'Hay 217 apariciones únicas de los 50 términos y 651 observaciones de modelo correlacionadas; acumulado de 60: 251 apariciones. Una misma grabación analizada por tres modelos no son tres entonaciones.',
        'No se grabaron nuevas voces, no se modificaron tono/acento/velocidad y no hubo prueba de entonaciones controladas. Las erratas construidas son texto, no variantes fonéticas verificadas.',
        'La muestra inglesa ya había sido explorada. No se extrapola a los 657 conceptos, español, otros hablantes ni funcionamiento en directo.',
        'Los siete casos de regresión previos pasan con los 60 términos, incluido primary allosteronism by this test -> primary aldosteronism by this test: se conserva by.',
        'En las nueve transcripciones con el perfil individual y controles no cambió la secuencia medida de conectores/negaciones/cifras, pero esas comprobaciones no detectan todos los cambios de significado ni de gramática.',
        'Antes de otra prueba conviene estudiar tres correcciones de política en un experimento nuevo: conservar variantes ya admisibles, proteger flexión singular/plural en ambas direcciones y resolver la selección entre frases largas y subexpresiones.',
        'Estas propuestas se documentan únicamente; no se aplicaron retrospectivamente, no se corrigieron los resultados desfavorables ni se cambió TRAD.',
        '', 'CONSERVACIÓN Y REPRODUCIBILIDAD',
        f"Se comprobaron {preserve['files_checked']} archivos de la instantánea; {preserve['strictly_protected_files_checked']} estaban protegidos estrictamente: glosarios, investigación anterior, paquete depurado, audios, referencias, ASR y bibliotecas usadas.",
        f"Cambios ajenos a la carpeta de este experimento observados en la instantánea: {len(preserve['other_snapshot_observations'])}.",
        'Las huellas de los originales y las evidencias anteriores coinciden. Únicos archivos nuevos: esta carpeta tolerance_trial_50_v1.',
        'Pasaron 12 pruebas de reproducibilidad/protección; la auditoría posterior comprobó los 27 cambios y las seis interferencias. No son una aprobación de eficacia del perfil.',
        'selection.json y protocol.json fijan muestra y método; threshold_decisions.json justifica cada punto; speech_comparison.json conserva todas las salidas simuladas y perfiles.',
        'final_results.json resume las comparaciones; preservation_final.json acredita la conservación; manifest.json contiene las huellas de los archivos nuevos.',
        'No se modificó el glosario original, no se alteraron evidencias previas y no se conectó ni integró nada en TRAD.',
    ]
    (HERE/'REPORT.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (HERE/'README.txt').write_text(
        'Ensayo de investigación: 50 términos adicionales; no integrado.\n'
        'Leer REPORT.txt y final_results.json. El resultado global de la ampliación es desfavorable.\n'
        'Los archivos previos, las decisiones congeladas y los resultados no se sobrescriben.\n'
        'evaluate_50.py reproduce el protocolo inicial en una carpeta nueva; se niega a sobrescribir el ensayo terminado.\n'
        'review_50.py documenta hallazgos después del checking; no recalibra.\n'
        'No hay pronunciaciones ni entonaciones nuevas, ni autorización de sustitución clínica.\n',encoding='utf-8')
    assert trial.prior.sha(HERE/'threshold_decisions.json')==freeze['decisions_sha256']
    trial.verify_inputs()
    # Seal only after all deliverables are complete; the manifest excludes itself.
    save('manifest.json',dict(sealed_at_utc=datetime.now(timezone.utc).isoformat(),
        files=[dict(name=p.relative_to(HERE).as_posix(),bytes=p.stat().st_size,sha256=trial.prior.sha(p))
               for p in sorted(HERE.rglob('*')) if p.is_file() and p.name!='manifest.json'],
        original_inputs_unchanged=True,frozen_thresholds_sha256=freeze['decisions_sha256'],integration_performed=False))
    print(trial.json.dumps(dict(report=str(HERE/'REPORT.txt'),new_files=len(load(HERE/'manifest.json')['files']),
        incremental_comparison=table,preservation=preserve),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
