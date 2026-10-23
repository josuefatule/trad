# Esquema de los archivos de investigación

Versión del esquema enriquecido: **1.0.0**. Codificación: UTF-8. El archivo operacional conserva el esquema original; no debe recibir campos del dataset enriquecido.

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

observed_wall_clock_minutes mide intervalo de reloj, no horas efectivas. effective_research_hours_measured=null evita simular esa medición. background_work, scheduled_automation, commits_created e integration_performed son false.

## Fuentes y continuidad

publication_date puede ser año, fecha completa o null cuando no se confirmó con precisión. language puede incluir en, es o ambos. access_level distingue página oficial, resumen, secciones de PDF, extractos indexados y metadatos. No se debe promover metadata-only a evidencia de lectura completa.

Las tablas de curación utilizan bloques @categoría|fuentes|localizador|respaldo y filas inglés|español|alternativas EN|variantes ES|nota. evidence_updates.json conserva cambios derivados de nuevas consultas. build_research.py solo escribe dentro de esta carpeta y comprueba el hash del original antes de reconstruir el lote.

No usar los alias de investigación para crear un mapa de sustitución sin revisión de contexto, gramática, idioma y colisiones.
