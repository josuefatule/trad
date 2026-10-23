# Esquema de los archivos de investigación

Versión del esquema enriquecido: **1.2.0**. Codificación: UTF-8. El archivo operacional conserva el esquema original; no debe recibir campos del dataset enriquecido. El inventario contiene 657 pares canónicos EN↔ES cotejados y 0 traducciones canónicas pendientes.

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
| bilingual_verification | Registro de 657 pares, decisiones, los últimos 57, ajustes de preferencia española y alcance de revisión |

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

El candidato conserva las políticas y umbrales originales. Las doce retiradas de alias pertenecen al lote inicial y se registran en validation_results.json y operational_export. Los 640 registros operacionales no se deben confundir con los 657 registros de investigación: estos agrupan formas del original y retienen propuestas que no se exportaron en el lote inicial. Aunque ahora los 657 pares canónicos están cotejados, el candidato se conserva byte por byte sin actualizarlo ni integrarlo.

El candidato no tiene traducciones porque el cargador operacional inglés no define campos bilingües. No se configura automáticamente como glosario activo.

## hypertension_research_progress.json

Incluye fechas, contabilidad de tiempo, ciclos, cantidades, categorías, identificadores pendientes, fuentes utilizadas, preguntas abiertas y siguiente trabajo.

observed_wall_clock_minutes suma los intervalos de las tres sessions y excluye ambas pausas; no mide horas efectivas. effective_research_hours_measured=null evita simular esa medición. background_work, scheduled_automation, commits_created e integration_performed son false. target.achieved=true se refiere exclusivamente a los 657 pares cotejados con fuentes externas, sin certificación clínica independiente. pending_translation_ids, pending_concept_ids y categories_pending están vacíos.

## Fuentes y continuidad

publication_date puede ser año, fecha completa o null cuando no se confirmó con precisión. language puede incluir en, es o ambos. access_level distingue página oficial, resumen, secciones de PDF, extractos indexados y metadatos. No se debe promover metadata-only a evidencia de lectura completa.

Las tablas de curación utilizan bloques @categoría|fuentes|localizador|respaldo y filas inglés|español|alternativas EN|variantes ES|nota. evidence_updates.json conserva cambios del lote inicial. Los constructores y finalizadores de 52 y 600 pares son históricos y tienen protección contra sobrescribir el cotejo posterior. finalize_657.py aplica los registros ya revisados y valida los entregables; nunca escribe el original ni el candidato.

No usar los alias de investigación para crear un mapa de sustitución sin revisión de contexto, gramática, idioma y colisiones.

## bilingual_verification.json y bilingual_decisions.json

El registro de verificación contiene 657 records, con los primeros 600 conservados como valores JSON idénticos al checkpoint previo. Cada uno conserva id, canonical_en, preferred_es, category, en_attestation, es_attestation, method, dos indicadores de literalidad normalizada, editorial_note, reviewed_by, reviewed_at_utc, independent_clinician_review y automatic_substitution_approved=false. Los 57 añadidos incluyen verification_session=session3.

Cada atestación incluye source_id, url, form (la forma realmente localizada), locator_kind, locator_index, source_copy_sha256, extracted_locator_sha256 y locator_index_is_pdf_page. Un índice pdf_page comienza en 1 y corresponde al archivo, no necesariamente a la página impresa. Los índices no PDF son bloques de extracción locales desde 1; no son números de página web.

method distingue literal_pair de reviewed_terminological_variant_or_contextual_rendering. La literalidad se calcula tras normalizar tildes, mayúsculas, ligaduras y puntuación. Un false en es_preferred_verbatim_normalized indica que la formulación preferida fue cotejada mediante una variante o expresión contextual, no que esté impresa literalmente en esa forma. El alcance de cada decisión se conserva en editorial_note.

bilingual_decisions.json contiene 657 decisiones accepted_external_bilingual_crosscheck del asistente. input_discovery_sha256_by_session conserva las dos huellas de descubrimiento. Los antiguos 57 pending permanecen en decision_history; los nueve pares insuficientes de la sesión anterior se resolvieron con evidencia específica o contexto definitorio. Las cuatro atestaciones españolas de fármacos corregidas en la sesión de 600 pares se mantienen; en la última sesión también se sustituyeron referencias bibliográficas inglesas por narrativa española de los estudios. Los archivos de descubrimiento son evidencia de búsqueda, no aprobación por sí mismos.

review.continuation_editorial_decision, continuation_editorial_note y translation_verification_record enlazan el dataset con la revisión. Las evidencias incluyen language, attested_form y verification_record_id. Se ajustaron dos preferred_es exclusivamente en investigación, con sus valores anteriores y razones en terminology_revision_history y session3_terminology_corrections.json. No se cambiaron aliases_en, variants_es, políticas operativas, canónicos ingleses ni identificadores. Las redacciones españolas reemplazadas no se aprobaron como alias automáticos.

session3_verification.json contiene los 57 pares finales; session3_review_decisions.json, su revisión explícita sobre una huella fija. Las listas indexed_bilingual_author_keywords pueden tener language=en,es y atestar ambas lenguas; esta excepción exige palabras clave genuinamente bilingües y no habilita a usar una bibliografía inglesa como traducción española.

supplementary_context_sources registra apoyo contextual adicional, distinto de las dos atestaciones nucleares de un par. No suma conceptos ni altera la cuenta de 1.314 atestaciones EN/ES.

## source_access_index.json y manifiesto

source_access_index.json registra disponibilidad en el corpus actual, clase y cantidad de localizadores, uso en los pares aceptados y huellas de los archivos locales consultados. latest_access_level puede diferir del acceso registrado en sesiones anteriores (incluido continuation_access_level). Disponibilidad de un PDF completo significa que el archivo se pudo consultar, no lectura exhaustiva de cada página. Los resúmenes, títulos originales y palabras clave bilingües se etiquetan específicamente.

manifest.json contiene tamaño y SHA-256 de cada archivo entregado. Las publicaciones completas y el corpus local están excluidos del ZIP. El conjunto de datos y los localizadores se pueden revisar con las URL y las huellas; repetir la comprobación textual requiere conservar o recuperar las copias públicas y el corpus local.


## Auditoría posterior de alias (solo investigación)

El dataset canónico conserva sus bytes. alias_inventory.json enumera 900 ocurrencias y 1.314 destinos canónicos EN/ES. occurrence_id identifica campo y procedencia; form_id agrupa por concepto, idioma y grafía exacta. alias_review_decisions.json contiene 567 decisiones y concept_coverage incluye los 657 conceptos, incluidos 301 sin alternativas. El listado crudo se consulta junto a esta capa de revisión, no se considera un conjunto de alias aprobados.

Los estados distinguen exclusión de equivalencia estricta, equivalencia contextual, sigla con definición obligatoria, colisión, grafía, flexión, unidad y variante de consulta. automatic_substitution_approved es siempre false. literal_location solo señala una coincidencia normalizada: no demuestra significado, sinonimia o idioma del pasaje. Las 124 formas sin coincidencia permanecen explícitas; no se eliminan ni se declaran verificadas externamente.

alias_corrections_proposed.json contiene propuestas sin aplicación: 11 exclusiones, 47 condiciones, 6 expansiones y 22 ajustes de metadatos. Las 3 colisiones internas, 16 advertencias externas y 60 pares similares tienen distinto alcance y no se suman como errores independientes. alias_definition_evidence.json separa 24 localizadores de definiciones del corpus previo y 20 referencias complementarias de alias_source_catalog.json; los niveles indexados/resumen no prueban lectura de artículos completos. Los IDs AS no sustituyen ni renumeran S01–S191.

Los recuentos counts del dataset/progreso anterior son una instantánea de la fase canónica. Los actuales están en alias_audit.counts y alias_audit_validation.json. La auditoría añade un cuarto intervalo observado y preserva todos los anteriores. finalize_657.py queda protegido contra reescribir esta fase; finalize_alias_audit.py valida y empaqueta la capa de revisión sin escribir el original, el candidato ni el dataset canónico. No reejecutar finalizadores para simular tiempo transcurrido de investigación.
