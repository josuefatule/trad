# Esquema de los archivos de investigación

Versión del esquema enriquecido: **1.1.0**. Codificación: UTF-8. El archivo operacional conserva el esquema original; no debe recibir campos del dataset enriquecido. La continuación contiene 600 pares canónicos EN↔ES cotejados y 57 pendientes.

## hypertension_research_en_es.json

| Campo raíz | Contenido |
|---|---|
| name, schema_version, updated_at, research_date, status | Identidad, versión, fecha de actualización con zona horaria y estado del lote |
| original | Ruta, hash SHA-256 y cantidad de entradas del archivo original |
| counting_policy, counts | Reglas y cantidades; no equiparar registros con conceptos bilingües plenamente verificados |
| sources | Catálogo de fuentes con id, título descriptivo, URL, organización, idioma, acceso, fecha y limitaciones |
| concepts | Registros terminológicos |
| do_not_merge | Pares o categorías que no admiten equivalencia automática |
| cross_language_abbreviation_ambiguities | Significados alternativos; algunos son alertas contextuales que requieren comprobación específica |
| rejected_equivalences | Equivalencias rechazadas y motivo |
| scope_reference_entities | Entidades fuera del alcance usadas para distinguir conceptos, sin contarlas como hipertensión sistémica |
| operational_export | Identidad del candidato y modificaciones propuestas; integrated=false |
| bilingual_verification | Archivo del registro de 600 pares, archivo de decisiones y alcance de revisión |

Cada registro concepts contiene:

| Campo | Regla |
|---|---|
| id | Identificador estable derivado del canónico inglés; sirve para retomar pendientes |
| canonical_en | Forma inglesa preferida del registro de investigación |
| preferred_es | Traducción española propuesta; su presencia no implica validación |
| aliases_en | Inventario de formas propuestas o heredadas; no son todas sinónimos estrictos verificados |
| variants_es | Variantes propuestas en español; consultar notas y estado antes de utilizarlas |
| alias_review_status, form_reviews | Estado de las formas, incluidas sustituciones rechazadas; nunca habilitan automáticamente un reemplazo |
| abbreviations | Forma, idioma, expansión y significados alternativos; automatic_expansion_approved=false |
| category, scope, origin | Categoría de curación, alcance sistémico y procedencia original/nueva |
| original_entries | Copias de entradas originales asociadas; conserva parámetros y procedencia |
| grouped_lexical_forms | Formas agrupadas para el conteo; pueden incluir adjetivos y no son alias automáticos |
| grouped_lexical_forms_are_automatic_aliases | Siempre false |
| clinical_context, notes | Condiciones de uso, diferencias y precauciones terminológicas específicas |
| evidence | source_id, localizador y alcance del apoyo; puede ser conceptual o temático sin atestar cada palabra |
| source_ids | Referencias al catálogo; no sustituyen la lectura del nivel de acceso |
| review | Verificación del concepto, traducción, revisión independiente y aprobación operacional |
| ambiguity | Riesgo, términos confundibles y automatic_substitution_approved=false |
| curation_provenance | Archivo y línea del inventario de curación |

Estados de revisión:

- **literature_supported_research_candidate**: seleccionado para investigación con respaldo conceptual o de contexto en las fuentes indicadas. No significa atestación individual de cada forma o equivalencia.
- **pending_targeted_source_verification**: requiere fuente puntual antes de aceptación terminológica.
- **crosschecked_in_en_and_es_sources**: cotejo terminológico en material de ambos idiomas, o resúmenes bilingües de una fuente. No significa revisión clínica independiente.
- **proposed_translation_pending_individual_source_check**: traducción propuesta que no se presenta como externamente verificada.
- **manual_review_required_not_approved**: todos los registros requieren revisión antes de uso operacional.

Las relaciones de subtipo se mantienen por separado cuando importan clínicamente. Se agrupan algunas variantes obvias o gramaticales para no inflar el conteo; no es una ontología exhaustiva. No se deducen diagnósticos ni dosis a partir de términos.

## medical_base_en_extended_candidate.json

Objeto raíz con **name**, **version** y **terms**, como el original.

Cada entrada usa solo canonical y, cuando estaban presentes en el original, aliases, variants, auto_apply, auto_threshold y suggest_threshold. Los nuevos términos tienen canonical y auto_apply=suggest. No se añaden nuevas listas de alias ni umbrales.

El candidato conserva las políticas y umbrales originales. Las doce retiradas de alias se registran en validation_results.json y en operational_export. Los 640 registros operacionales no se deben confundir con los 657 registros de investigación: estos agrupan algunas formas del original y retienen propuestas nuevas que no se exportaron por falta de verificación.

El candidato no tiene traducciones porque el cargador operacional inglés no define campos bilingües. No se configura automáticamente como glosario activo.

## hypertension_research_progress.json

Incluye fechas, contabilidad de tiempo, ciclos, cantidades, categorías, identificadores pendientes, fuentes utilizadas, preguntas abiertas y siguiente trabajo.

observed_wall_clock_minutes suma los intervalos observados de sessions y excluye la pausa entre sesiones; no mide horas efectivas. effective_research_hours_measured=null evita simular esa medición. background_work, scheduled_automation, commits_created e integration_performed son false. target.achieved=true se refiere exclusivamente a los 600 pares cotejados con fuentes externas, sin certificación clínica independiente.

## Fuentes y continuidad

publication_date puede ser año, fecha completa o null cuando no se confirmó con precisión. language puede incluir en, es o ambos. access_level distingue página oficial, resumen, secciones de PDF, extractos indexados y metadatos. No se debe promover metadata-only a evidencia de lectura completa.

Las tablas de curación utilizan bloques @categoría|fuentes|localizador|respaldo y filas inglés|español|alternativas EN|variantes ES|nota. evidence_updates.json conserva cambios del lote inicial. build_research.py y finalize_research.py son históricos y ahora impiden sobrescribir el cotejo posterior. finalize_continuation.py aplica el registro ya revisado y valida los entregables; nunca escribe el original ni el candidato.

No usar los alias de investigación para crear un mapa de sustitución sin revisión de contexto, gramática, idioma y colisiones.

## bilingual_verification.json y bilingual_decisions.json

El registro de verificación contiene 600 records. Cada uno conserva id, canonical_en, preferred_es, category, en_attestation, es_attestation, method, dos indicadores de literalidad normalizada, editorial_note, reviewed_by, reviewed_at_utc, independent_clinician_review y automatic_substitution_approved=false.

Cada atestación incluye source_id, url, form (la forma realmente localizada), locator_kind, locator_index, source_copy_sha256, extracted_locator_sha256 y locator_index_is_pdf_page. Un índice pdf_page comienza en 1 y corresponde al archivo, no necesariamente a la página impresa. Los índices no PDF son bloques de extracción locales desde 1; no son números de página web.

method distingue literal_pair de reviewed_terminological_variant_or_contextual_rendering. La literalidad se calcula tras normalizar tildes, mayúsculas, ligaduras y puntuación. Un false en es_preferred_verbatim_normalized indica que la formulación preferida fue cotejada mediante una variante o expresión contextual, no que esté impresa literalmente en esa forma. El alcance de cada decisión se conserva en editorial_note.

bilingual_decisions.json contiene 657 decisiones del asistente: 600 accepted_external_bilingual_crosscheck y 57 pending. Registra la huella de bilingual_discovery.json, el conjunto fijo revisado de 609 coincidencias dobles y nueve coincidencias excluidas. Las cuatro atestaciones españolas de nombres de fármacos inicialmente localizadas en bibliografía inglesa fueron sustituidas por el cuerpo español de AHA; los datos de descubrimiento se conservan como evidencia de la corrección, no como registro de aceptación.

review.continuation_editorial_decision, continuation_editorial_note y translation_verification_record enlazan el dataset con esta revisión. Las evidencias nuevas incluyen language, attested_form y verification_record_id. Esta revisión no cambia preferred_es, aliases_en, variants_es, políticas operativas ni identificadores.

## source_access_index.json y manifiesto

source_access_index.json registra disponibilidad real en esta continuación, clase y cantidad de localizadores, uso en los pares aceptados y huellas de los archivos locales consultados. continuation_access_level puede diferir del acceso registrado en una sesión anterior. Disponibilidad de un PDF completo significa que el archivo se pudo consultar, no lectura exhaustiva de cada página. Los resúmenes, títulos originales y palabras clave bilingües se etiquetan específicamente.

manifest.json contiene tamaño y SHA-256 de cada archivo entregado. Las publicaciones completas y el corpus local están excluidos del ZIP. El conjunto de datos y los localizadores se pueden revisar con las URL y las huellas; repetir la comprobación textual requiere conservar o recuperar las copias públicas y el corpus local.
