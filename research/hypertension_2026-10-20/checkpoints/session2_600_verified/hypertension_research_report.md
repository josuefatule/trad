# TRAD — Cotejo terminológico de hipertensión EN↔ES

Actualización: **2026-10-20T19:00:06-04:00**. Meta solicitada: **600 pares canónicos bilingües cotejados**, alcanzada. Investigación documental sin integración.

Se verificaron **548 de las 605 traducciones pendientes** y se conservaron los 52 pares ya contrastados: **600 verificados y 57 pendientes** entre los 657 registros del inventario. Cada par aceptado tiene una atestación inglesa y otra española, con fuente, URL, forma localizada, página o bloque de extracción y huella de integridad. La equivalencia fue revisada por el asistente; **no hubo revisión clínica independiente**.

El glosario original conserva su SHA-256 `4a4920d3ff9404db5601c1c8f832dde4fdeb180dc95d3f06037576ec726c2896`. El candidato operacional también conserva exactamente sus bytes, SHA-256 `f70199e00efd516220f33c6c36f500ed220992b2caa6bba0d85cdf9b2086ae45`. En esta continuación solo se actualizaron archivos de investigación. No hubo integración, cambios de código o parámetros de TRAD ni commits.

## Entregables y recuentos

- [Dataset enriquecido](hypertension_research_en_es.json): 657 registros con estado individual y referencias.
- [Registro de los 600 pares](bilingual_verification.json): evidencia EN/ES, forma atestada, localizadores y notas de equivalencia.
- [Decisiones editoriales](bilingual_decisions.json): resultado para los 657 registros, incluidos los 57 pendientes.
- [Progreso](hypertension_research_progress.json): historial de sesiones, categorías y pendientes por identificador.
- [Catálogo de fuentes](sources.json), [índice de acceso y huellas](source_access_index.json), [validación](validation_results.json), [esquema](DATASET_SCHEMA.md) y [manifiesto](manifest.json).
- [Candidato de la sesión anterior](medical_base_en_extended_candidate.json), conservado sin cambios. Su inclusión es documental y no autoriza su uso operativo.

| Medida | Resultado |
|---|---:|
| Entradas del glosario original | 294 |
| Formas léxicas del inventario previo | 667 |
| Registros canónicos tras las 10 agrupaciones previas | 657 |
| Pares EN↔ES cotejados individualmente | **600** |
| Nuevas verificaciones en esta continuación | **548** |
| Verificaciones anteriores conservadas | 52 |
| Traducciones pendientes | **57** |
| Pares de formas literales tras normalización | 385 |
| Pares con variante terminológica o formulación contextual revisada | 215 |
| Registros con respaldo conceptual o temático | 644 |
| Registros con respaldo conceptual puntual pendiente | 13 |
| Entradas del catálogo, incluidos accesos fallidos o parciales | 130 |
| Fuentes citadas en las atestaciones de los 600 pares | 72 |
| Atestaciones individuales comprobadas, dos por par | 1.200 |
| Registros certificados por un clínico independiente | 0 |

Se mantuvieron los identificadores y el inventario de la sesión previa. El conteo comprende entidades clínicas, fármacos, métodos, unidades, nombres de estudios y vocabulario de investigación o congreso; no significa 600 enfermedades distintas. Los alias y flexiones no suman conceptos y no se aprobaron automáticamente. Verificar una denominación farmacológica tampoco verifica dosis, indicaciones, formulaciones ni aprobación regulatoria.

## Método y revisión crítica

1. Se retomaron los 605 identificadores pendientes del registro anterior y se conservaron las 52 verificaciones previas. El estado anterior quedó archivado en `checkpoints/session1_52_verified`.
2. Se priorizaron ESC, ACC, AHA, PubMed, OMS y KDIGO. Para el español se contrastaron las traducciones oficiales SEC de ESC, publicaciones KDIGO/Nefrología y documentos NLM y de sociedades especializadas. Cuando fue necesario se usaron copias de publicaciones primarias alojadas por sociedades o repositorios institucionales, identificando el alojamiento.
3. La búsqueda en textos completos, páginas oficiales y resúmenes identificó **609 pares candidatos**. Las coincidencias de palabras solo sirvieron para localizar evidencia. Se revisaron identidad, método, población, temporalidad, calificadores y contexto clínico antes de aceptar la equivalencia.
4. Se retuvieron nueve coincidencias insuficientes como pendientes. Cuatro primeras coincidencias españolas de nombres farmacológicos estaban en bibliografía inglesa; se sustituyeron por listas de medicamentos dentro del cuerpo español de la AHA. No se contó una referencia inglesa como traducción española.
5. Se aceptaron 600 pares y se conservaron 57 pendientes. El registro distingue las formas efectivamente atestadas de la redacción preferida del inventario. La presencia de una variante en una fuente no convierte todos los alias del registro en sinónimos estrictos.

Los localizadores `pdf_page` son páginas del archivo PDF, numeradas desde 1; pueden diferir de la paginación impresa. Los localizadores de HTML y de extractos web son bloques de 35 líneas del corpus local. Los títulos originales españoles, resúmenes españoles y palabras clave bilingües de PubMed se etiquetan expresamente. Una ficha indexada no se presenta como lectura del artículo completo. Las huellas permiten comprobar que el texto localizado no cambió.

La extracción normaliza mayúsculas, tildes, ligaduras, puntuación y cortes de línea de PDF para localizar términos. El criterio de aceptación final es una decisión editorial del asistente sobre ese conjunto fijo; el programa de búsqueda no puede aprobar nuevas coincidencias. Los 215 pares no literales incluyen flexiones, variantes regionales, siglas desarrolladas en la fuente y traducciones clínicas contextuales, con las formas localizadas conservadas para revisión.

## Fuentes principales y alcance de lectura

- **ESC 2024, hipertensión:** guía inglesa completa disponible mediante repositorio institucional y traducción española SEC completa. Se consultaron secciones de medición, clasificación, mecanismos, fármacos, hipertensión secundaria y daño orgánico. La página oficial de ESC sigue siendo la referencia de versión; no se afirma que la traducción incorpore toda corrección posterior. [ESC oficial](https://www.escardio.org/guidelines/clinical-practice-guidelines/all-esc-practice-guidelines/elevated-blood-pressure-and-hypertension/), [texto inglés, DOI 10.1093/eurheartj/ehae178](https://repisalud.isciii.es/bitstreams/4fe1933e-3844-454d-9cef-4a64b5debafe/download), [traducción SEC](https://secardiologia.es/images/2023/Gu%C3%ADas/Final_GPC_ESC_2024_PA_elevada_e_hipertensio%CC%81n.pdf).
- **AHA/ACC 2025:** materiales oficiales ingleses y españoles, clasificación y prevención, y páginas de medicamentos. No se afirma lectura integral de todo el artículo de la guía. La denominación histórica de 2017 se conserva como tal. [ACC 2025](https://www.acc.org/About-ACC/Press-Releases/2025/08/13/20/03/New-high-blood-pressure-guideline-emphasizes-prevention-early-treatment-to-reduce-CVD-risk), [AHA en español](https://newsroom.heart.org/news/la-nueva-guia-sobre-la-presion-arterial-alta-enfatiza-la-prevencion-y-el-tratamiento-temprano-para-reducir-el-riesgo-de-ecv), [medicamentos en español](https://www.stroke.org/es/health-topics/high-blood-pressure/changes-you-can-make-to-manage-high-blood-pressure/types-of-blood-pressure-medications).
- **KDIGO:** guía de ERC de 2024, resumen ejecutivo español y consenso sobre potasio; resumen oficial de PA de 2021. La ruta de alojamiento de 2026 no cambia el año de la guía de ERC. [KDIGO 2024](https://kdigo.org/wp-content/uploads/2026/04/KDIGO-2024-CKD-Guideline.pdf), [resumen ejecutivo español](https://static.elsevier.es/nad/kdigo2024.pdf), [KDIGO PA 2021](https://kdigo.org/wp-content/uploads/2021/03/Top-10-Takeaways-Clinicians-KDIGO-BP-Guideline.pdf).
- **OMS/OPS:** ficha española de hipertensión y publicación técnica sobre dispositivos de PA. Se utilizó una copia de la publicación española de especificaciones, ISBN 978-92-75-32305-2, alojada por un colegio profesional; IRIS devolvió una página de aplicación sin el PDF. [OMS](https://www.who.int/es/news-room/fact-sheets/detail/hypertension), [publicación técnica española, copia institucional](https://colegiodeenfermeros.org.ar/wp-content/uploads/2000/10/Especificaciones-tecnicas-de-la-OMS-para-dispositivos-electronicos.pdf).
- **ESC 2025, embarazo:** traducción SEC completa disponible; se consultaron glosario, biomarcadores y apartados hipertensivos. No se declara revisión exhaustiva de toda la cardiología obstétrica. [Guía española](https://secardiologia.es/images/2024/Gu%C3%ADas/Gui%CC%81a-ESC-2025-manejo-ECV-y-embarazo.pdf).
- **NLM/PubMed y especialidades:** textos publicados sobre medición, hipertensión resistente, SRAA, endocrinología y emergencias, además de títulos o resúmenes bilingües identificados individualmente. Los documentos históricos se usaron para terminología, sin trasladar sus umbrales o tratamientos a recomendaciones actuales. [AHA: medición, texto completo](https://pmc.ncbi.nlm.nih.gov/articles/PMC11409525/), [AHA: hipertensión resistente](https://pmc.ncbi.nlm.nih.gov/articles/PMC6530990/), [Endocrine Society 2025](https://www.endocrine.org/clinical-practice-guidelines/primary-aldosteronism-2).
- **Métodos de investigación:** glosario y manual de Cochrane y diccionario del NCI para distinguir medidas de efecto y diseños. [Cochrane](https://es.cochrane.org/es/glosario), [NCI: hazard ratio](https://www.cancer.gov/espanol/publicaciones/diccionarios/diccionario-cancer/def/cociente-de-riesgos-instantaneos).

El catálogo registra además las fuentes no accesibles. Una descarga bloqueada, una pantalla de comprobación o una página vacía no aporta verificación. El archivo de entrega excluye las copias completas de publicaciones y conserva enlaces y huellas. El conector Deep Research solicitado no estaba disponible entre las herramientas expuestas; esta continuación utilizó consultas web reales y fuentes públicas.

## Decisiones clínicas y terminológicas relevantes

- Se mantuvieron separados clasificación diagnóstica, umbral de tratamiento y objetivo terapéutico. Las categorías de PA elevada y los estadios requieren sociedad, año y método de medición. No se presentan ESC y AHA/ACC como una clasificación universal. [ESC 2024](https://www.escardio.org/guidelines/clinical-practice-guidelines/all-esc-practice-guidelines/elevated-blood-pressure-and-hypertension/), [AHA 2025](https://professional.heart.org/en/science-news/2025-high-blood-pressure-guideline/top-things-to-know).
- Se distinguieron hipertensión resistente, aparentemente resistente, pseudorresistente y refractaria; hipertensión arterial sistémica y pulmonar; elevación grave de PA y emergencia con daño agudo. El cotejo de palabras no elimina estas diferencias. [AHA: resistencia](https://pmc.ncbi.nlm.nih.gov/articles/PMC6530990/), [emergencias](https://pmc.ncbi.nlm.nih.gov/articles/PMC11522727/).
- Se preservaron actividad de renina, concentración directa de renina, aldosterona plasmática, cociente aldosterona/renina y pruebas de confirmación como unidades distintas. No se exportaron puntos de corte ni protocolos de documentos históricos. [Endocrine Society](https://www.endocrine.org/clinical-practice-guidelines/primary-aldosteronism-2).
- Se cotejaron sFlt-1 y PlGF por separado; pequeño para edad gestacional no se fusiona con restricción del crecimiento fetal, ni hipertensión preexistente con hipertensión gestacional. [ESC embarazo 2025](https://secardiologia.es/images/2024/Gu%C3%ADas/Gui%CC%81a-ESC-2025-manejo-ECV-y-embarazo.pdf).
- Se mantuvieron distintos hazard ratio, riesgo relativo y odds ratio. Este último sigue pendiente porque la coincidencia española encontrada conserva el término inglés y no verifica la traducción propuesta. Cochrane atesta «número necesario para dañar», pero recomienda una formulación de NNT para un resultado perjudicial adicional; la nota se conserva en el registro. [Cochrane: manual español](https://es.cochrane.org/sites/es.cochrane.org/files/uploads/manual_cochrane_510_web.pdf).

Las nueve coincidencias retenidas para revisión adicional son:

- **NHANES**: La coincidencia española encontrada es una referencia bibliográfica inglesa, no una atestación narrativa en español.
- **alcohol moderation**: Se retiene la expresión de intervención para un cotejo más literal; el pasaje inglés localizado describe consumo moderado y sus límites.
- **arterial compliance**: Distensibilidad y compliance requieren distinguir el cambio absoluto de volumen del cambio relativo; pendiente una equivalencia precisa.
- **attended automated office blood pressure**: El pasaje español con o sin observador reúne dos modalidades; falta atestación específica de la modalidad con observador.
- **albumin excretion rate**: Excreción de albúmina sin tasa no conserva la dimensión temporal de excretion rate.
- **spot urine sample**: Una muestra de la mañana no verifica la equivalencia general de muestra aislada o puntual.
- **focal neurological deficit**: Lesiones neurológicas focales no atesta déficit neurológico focal; se conserva pendiente.
- **glomerular hypertension**: El localizador inglés especifica arteriolar; se retiene para revisar el compartimento vascular con una fuente más precisa.
- **odds ratio**: La forma inglesa prestada odds ratio no atesta la traducción propuesta razón de momios.

## Cobertura y pendientes

| Categoría del inventario | Registros | Cotejados EN/ES | Pendientes |
|---|---:|---:|---:|
| classification | 41 | 40 | 1 |
| measurement | 51 | 49 | 2 |
| guidelines | 10 | 8 | 2 |
| conference_language | 22 | 17 | 5 |
| risk_prevention | 30 | 28 | 2 |
| research_methods | 38 | 35 | 3 |
| clinical_trials | 23 | 11 | 12 |
| endocrine_renal | 83 | 76 | 7 |
| kidney | 37 | 35 | 2 |
| treatment | 54 | 49 | 5 |
| medications | 69 | 69 | 0 |
| organ_damage | 55 | 53 | 2 |
| lifestyle | 27 | 25 | 2 |
| units_measurement | 15 | 13 | 2 |
| physiology | 45 | 44 | 1 |
| emergencies | 19 | 15 | 4 |
| pregnancy | 25 | 23 | 2 |
| special_populations | 13 | 10 | 3 |

Los 57 siguientes conservan estado pendiente. Su inclusión en el inventario no debe interpretarse como verificación bilingüe:

| ID estable | Inglés | Español propuesto |
|---|---|---|
| HTN_8d17bae1bc5a | JNC 7 guideline | guía JNC 7 |
| HTN_4ab0f32c0a4c | JNC 8 report | informe JNC 8 |
| HTN_b0de6f8f7d51 | guideline-driven management | manejo basado en guías |
| HTN_1b881806cbc3 | evidence-based review | revisión basada en la evidencia |
| HTN_a9290515a379 | ten-year ASCVD risk | riesgo de enfermedad cardiovascular aterosclerótica a 10 años |
| HTN_9c147fb0dd01 | primordial prevention | prevención primordial |
| HTN_2674e0e256e0 | CARDIA study | estudio CARDIA |
| HTN_9efacc096375 | REGARDS study | estudio REGARDS |
| HTN_de8a43278de5 | NHANES | NHANES |
| HTN_c55b21ee723a | co-chair | copresidente |
| HTN_ee45bdae9c43 | renin-independent aldosterone production | producción de aldosterona independiente de renina |
| HTN_fe15c79eba36 | hypokalemic metabolic alkalosis | alcalosis metabólica hipopotasémica |
| HTN_90d4d5df0cdf | medication titration | ajuste gradual de la dosis |
| HTN_210db6e8d322 | mineralocorticoid receptor antagonist therapy | tratamiento con antagonistas del receptor de mineralocorticoides |
| HTN_c14e2214165b | subclinical atherosclerosis | aterosclerosis subclínica |
| HTN_b77b3ada1555 | sodium-containing salts | sales que contienen sodio |
| HTN_360421e6c958 | alcohol moderation | moderación del consumo de alcohol |
| HTN_b3a920f4854a | micrograms per day | microgramos por día |
| HTN_08df2fb9a572 | micrograms per deciliter | microgramos por decilitro |
| HTN_1461e740924a | clinical guidelines implementation | implementación de guías de práctica clínica |
| HTN_ab697e405d94 | arterial compliance | distensibilidad arterial |
| HTN_51c3b943c1c3 | hybrid sphygmomanometer | esfigmomanómetro híbrido |
| HTN_7a7149e08b17 | attended automated office blood pressure | presión arterial automatizada en consultorio con observador |
| HTN_ef6b40c76638 | renal parenchymal hypertension | hipertensión de origen parenquimatoso renal |
| HTN_e0ffd99ff3e1 | adrenal lateralization | lateralización suprarrenal |
| HTN_001a4396cf85 | lateralizing primary aldosteronism | aldosteronismo primario lateralizado |
| HTN_4110283fe66f | overnight dexamethasone suppression test | prueba de supresión nocturna con dexametasona |
| HTN_2059d7aa272f | preoperative alpha blockade | bloqueo alfaadrenérgico preoperatorio |
| HTN_9ebc2ef8e698 | licorice-induced hypertension | hipertensión inducida por regaliz |
| HTN_02d32c438fa5 | albumin excretion rate | tasa de excreción de albúmina |
| HTN_48687c33055c | spot urine sample | muestra aislada de orina |
| HTN_ee68c0139219 | biochemical adherence testing | pruebas bioquímicas de adherencia |
| HTN_dabd6a557ead | alcohol-mediated renal denervation | denervación renal mediada por alcohol |
| HTN_bf82b7ff7585 | renal artery stenting | colocación de stent en la arteria renal |
| HTN_52a96921d6d9 | asymptomatic markedly elevated blood pressure | presión arterial marcadamente elevada sin síntomas |
| HTN_a771971e83a5 | focal neurological deficit | déficit neurológico focal |
| HTN_5307fadc73e2 | intravenous antihypertensive therapy | tratamiento antihipertensivo intravenoso |
| HTN_073d741b83bc | flash pulmonary edema | edema pulmonar de aparición súbita |
| HTN_696e8078d71d | postpartum preeclampsia | preeclampsia posparto |
| HTN_5ea9929ea500 | perinatal death | muerte perinatal |
| HTN_6832f45cc30b | glomerular hypertension | hipertensión glomerular |
| HTN_be503d73e106 | blood pressure percentile | percentil de presión arterial |
| HTN_43e0c4af6dd1 | cerebral hypoperfusion | hipoperfusión cerebral |
| HTN_10b0fd07b0f1 | intermittent hypoxemia | hipoxemia intermitente |
| HTN_16fdb8ef2c0b | CLICK trial | ensayo CLICK |
| HTN_11211b77eb7e | BPROAD trial | ensayo BPROAD |
| HTN_418a9b8ed5a9 | ESPRIT trial | ensayo ESPRIT |
| HTN_8e92ddf03bf5 | Advance-HTN trial | ensayo Advance-HTN |
| HTN_3062e896a014 | HYVET trial | ensayo HYVET |
| HTN_7083e8c3981d | ASCOT-BPLA trial | ensayo ASCOT-BPLA |
| HTN_65b7bf5b1b54 | RADIANCE-HTN TRIO trial | ensayo RADIANCE-HTN TRIO |
| HTN_8b09e2cea13f | SPYRAL HTN-OFF MED trial | ensayo SPYRAL HTN-OFF MED |
| HTN_d006ebf84516 | standard blood pressure control | control estándar de la presión arterial |
| HTN_581d1bf28a4d | nonfatal stroke | accidente cerebrovascular no mortal |
| HTN_9a5b7b5c9e81 | odds ratio | razón de momios |
| HTN_8f0c47679c6d | 2021 KDIGO blood pressure guideline | guía KDIGO de presión arterial de 2021 |
| HTN_f8015196a74c | 2024 KDIGO CKD guideline | guía KDIGO de enfermedad renal crónica de 2024 |

## Validación, continuidad y tiempo

Se comprobaron los JSON, la unicidad de los 657 identificadores, las referencias de fuentes, las 1.200 atestaciones y sus localizadores, la coherencia de recuentos y las huellas de los archivos protegidos. Se verificó que todos los registros conservan `automatic_substitution_approved=false`, que no hay aprobación clínica independiente y que el archivo ZIP reproduce los archivos del manifiesto.

Las pruebas del normalizador y los casos adversariales pertenecen a la sesión anterior y conservan su fecha. No se repitieron porque el candidato y el glosario son idénticos. No se realizó evaluación de audio, mejora de ASR, latencia ni calidad de traducción en ejecución. Las doce retiradas de alias del candidato pertenecen a la sesión previa; esta continuación no lo modificó.

La primera sesión duró aproximadamente **27,58 minutos de reloj**. Esta continuación registra **41.6 minutos**, desde las 22:18:30 UTC hasta el cierre documentado. La suma es **69.18 minutos**; excluye la pausa entre sesiones e incluye investigación, curación, documentación y validación. No se midieron horas efectivas por separado ni se afirman tres horas efectivas.

La meta de 600 pares solicitada para esta continuación queda completada. Los 57 restantes y la revisión clínica independiente siguen documentados para una eventual continuación. No hay tareas programadas ni investigación ejecutándose en segundo plano. El archivo `CONTINUATION_README.txt` explica cómo verificar los entregables sin volver al constructor histórico de 52 pares.
