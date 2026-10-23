# TRAD — Verificación terminológica de los 657 conceptos EN↔ES

Actualización: **{{UPDATED}}**, hora de Bolivia (UTC−04:00).

**Inventario completado: 657 pares canónicos cotejados con fuentes inglesas y españolas; 0 traducciones canónicas pendientes.** Se verificaron los 57 pendientes y se conservaron íntegros los 600 registros de verificación anteriores. Se documentaron dos ajustes de preferencia española dentro del dataset de investigación.

El cotejo fue realizado por el asistente. **No constituye certificación clínica independiente ni aprobación para sustituciones automáticas.** Se mantienen las 657 unidades canónicas del inventario previo: entidades clínicas, fármacos, procedimientos, unidades, nombres de estudios y vocabulario de investigación o congreso. No se añadieron alias o flexiones para alcanzar la cifra, ni se afirma que sean 657 enfermedades distintas.

## Entregables y protección del proyecto

- [Dataset enriquecido](hypertension_research_en_es.json), [registro completo de los 657 pares](bilingual_verification.json) y [progreso actualizado](hypertension_research_progress.json).
- [Los 57 pares de esta sesión](session3_verification.json), [decisiones de revisión](session3_review_decisions.json) y [ajustes terminológicos](session3_terminology_corrections.json).
- [Decisiones acumuladas e historial](bilingual_decisions.json), [catálogo de fuentes](sources.json), [acceso e integridad de fuentes](source_access_index.json), [validación](validation_results.json), [esquema](DATASET_SCHEMA.md) y [manifiesto](manifest.json).

El glosario original conserva su SHA-256 `4a4920d3ff9404db5601c1c8f832dde4fdeb180dc95d3f06037576ec726c2896`. El candidato operacional previo también conserva exactamente sus bytes: `f70199e00efd516220f33c6c36f500ed220992b2caa6bba0d85cdf9b2086ae45`. Solo se escribieron archivos de investigación. No se modificaron código, configuración, modelos ni parámetros de TRAD. No hubo integración, commits ni tareas programadas.

El [candidato conservado](medical_base_en_extended_candidate.json) mantiene sus 640 entradas y su estado de propuesta. Esta revisión no lo amplió ni lo configuró como glosario activo. Los estados anteriores de 52 y 600 pares se conservan en `checkpoints/session1_52_verified/` y `checkpoints/session2_600_verified/`.

## Recuentos comprobados

| Medida | Resultado |
|---|---:|
| Entradas del glosario original | 294 |
| Formas léxicas del inventario inicial | 667 |
| Registros canónicos tras 10 agrupaciones previas | 657 |
| Pares canónicos EN↔ES cotejados | **657** |
| Verificaciones anteriores conservadas | 600 |
| Nuevas verificaciones en esta sesión | **57** |
| Traducciones canónicas pendientes | **0** |
| Registros con fuente conceptual puntual pendiente | 0 |
| Formulaciones literales tras normalización | {{LITERAL}} |
| Variantes o formulaciones contextuales revisadas | {{CONTEXTUAL}} |
| Atestaciones individuales comprobadas | **1.314** |
| Fuentes usadas en las atestaciones EN/ES | {{CITED}} |
| Entradas del catálogo, incluidos accesos parciales o fallidos | {{SOURCES}} |
| Ajustes de preferencia española en esta sesión | 2 |
| Registros certificados por un clínico independiente | 0 |

La verificación del par canónico no aprueba por extensión todos sus alias, abreviaturas, flexiones, indicaciones, dosis, formulaciones o puntos de corte.

## Método y revisión crítica

Se retomaron los 57 identificadores pendientes, priorizando ESC, ACC, AHA, PubMed, OMS y KDIGO. Las traducciones SEC, NLM/MedlinePlus, OPS y publicaciones de sociedades y centros académicos aportaron atestaciones españolas. Se revisaron identidad, modificadores, contexto y procedencia antes de aceptar cada par. Una coincidencia textual aislada no se convirtió automáticamente en verificación.

Se sustituyeron localizadores que solo apuntaban a bibliografía inglesa dentro de textos españoles. CARDIA, NHANES, RADIANCE-HTN TRIO y SPYRAL HTN-OFF MED se comprobaron en narrativa española. Para Advance-HTN se seleccionó el contenido de la sección correspondiente, separado de SOUL, en vez de usar solo su entrada en el índice.

Las nueve coincidencias insuficientes retenidas previamente se resolvieron así:

| Concepto | Evidencia o precisión incorporada |
|---|---|
| Déficit neurológico focal | NLM atesta déficit como alteración funcional; se descartó lesión neurológica como equivalencia automática |
| Muestra aislada de orina | La fuente distingue muestra aislada de recogida cronometrada; matinal es una preferencia, no su definición |
| Tasa de excreción de albúmina | Se obtuvo la expresión completa con tasa, en lugar de solo excreción |
| Odds ratio | El NCI enumera razón de momios; el préstamo inglés aislado dejó de ser la única evidencia española |
| Arterial compliance | Se ajustó la preferencia a compliancia arterial, atestada en una publicación médica |
| PA automatizada con observador | La definición SEC identifica la modalidad con asistencia de un profesional; no se depende del fragmento con o sin personal |
| Hipertensión glomerular | Se obtuvo un artículo inglés sobre presión capilar glomerular; no se depende del fragmento arteriolar |
| NHANES | El CDC identifica y define la encuesta en una página narrativa española |
| Moderación del alcohol | Se cotejó la acción inglesa de restringir consumo con la expresión española de moderación |

Se mantuvieron separadas producción de aldosterona y secreción cuando el matiz importaba; para producción independiente de renina se obtuvo una formulación española específica de producción. La prueba nocturna de dexametasona se distinguió de las variantes de dos días. Las pruebas bioquímicas de adherencia se verificaron como detección de medicación en suero/orina, sin usar PA, glucemia o HbA1c como prueba de ingestión.

La cohorte CARDIA se distinguió del ensayo CARDia de revascularización en diabetes. También se conservaron SPYRAL OFF MED frente a ON MED; RADIANCE TRIO frente a SOLO y II; y ASCOT-BPLA frente a ASCOT-LLA. Las unidades se cotejaron sin trasladar intervalos históricos de referencia ni convertirlos en recomendaciones.

## Dos ajustes en el dataset de investigación

| Inglés | Preferencia anterior | Preferencia actual |
|---|---|---|
| arterial compliance | distensibilidad arterial | **compliancia arterial** |
| asymptomatic markedly elevated blood pressure | presión arterial marcadamente elevada sin síntomas | **presión arterial marcadamente elevada asintomática** |

El primer ajuste evita asumir una equivalencia física universal con distensibilidad. El segundo adopta la denominación técnica atestada y conserva la distinción respecto a emergencia con daño orgánico agudo. Los valores anteriores quedan en el historial y no se añaden como alias automáticos. Una cifra de PA por sí sola no define emergencia. [Publicación médica sobre compliancia](https://encolombia.com/medicina/revistas-medicas/academedicina/vam-128/presion-arterial/), [AHA: categorías españolas](https://www.heart.org/eS/health-topics/high-blood-pressure/the-facts-about-high-blood-pressure), [AHA: cuidados agudos](https://professional.heart.org/en/science-news/management-of-elevated-blood-pressure-in-the-acute-care-setting/top-things-to-know).

## Los 57 pares completados

Las columnas EN y ES remiten al [catálogo de fuentes](sources.json). Las formas efectivamente atestadas, páginas o bloques y justificaciones están en [el registro de esta sesión](session3_verification.json). La redacción preferida no se presenta como cita literal cuando se verificó mediante una variante o definición contextual.

| Inglés canónico | Español preferido | Fuente EN | Fuente ES |
|---|---|---|---|
{{NEW_PAIRS}}

## Fuentes y límites de acceso

Las versiones inglesa y española de ESC 2024 y los textos KDIGO siguen siendo la base del corpus. La continuación agregó búsquedas puntuales; no se presenta como revisión exhaustiva de todas las recomendaciones clínicas o correcciones de guías.

- **ESC/SEC:** medición, etiologías renales, emergencias y estudios, además de narrativa española sobre BPROAD y titulación. [ESC 2024](https://www.escardio.org/guidelines/clinical-practice-guidelines/all-esc-practice-guidelines/elevated-blood-pressure-and-hypertension/), [traducción SEC](https://secardiologia.es/images/2023/Gu%C3%ADas/Final_GPC_ESC_2024_PA_elevada_e_hipertensio%CC%81n.pdf), [BPROAD](https://secardiologia.es/blog/15689-control-intensivo-de-la-presion-arterial-en-pacientes-con-diabetes-tipo-2).
- **AHA/ACC/NLM:** prevención, horizonte de riesgo ASCVD y publicaciones primarias de estudios. La forma inglesa exacta guideline-driven management se encontró en una revisión de Circulation Research. [Artículo en PMC](https://pmc.ncbi.nlm.nih.gov/articles/8034801/), [ACC: Advance-HTN](https://www.acc.org/latest-in-cardiology/clinical-trials/2025/03/27/15/49/advance-htn), [AHA: riesgo](https://newsroom.heart.org/news/redefinicion-de-riesgo-prevencion-y-tratamiento-de-las-enfermedades-cardiacas), [AHA: CARDIA](https://newsroom.heart.org/news/ver-la-television-por-un-tiempo-moderado-o-considerable-en-la-mediana-edad-se-vincula-con-un-posterior-deterioro-cognitivo-y-de-la-salud-cerebral).
- **KDIGO:** títulos de PA 2021 y ERC 2024, sin sustituir el año del documento por el de su alojamiento. [PA 2021](https://kdigo.org/wp-content/uploads/2021/03/Top-10-Takeaways-Clinicians-KDIGO-BP-Guideline.pdf), [ERC 2024](https://kdigo.org/wp-content/uploads/2026/04/KDIGO-2024-CKD-Guideline.pdf), [resumen español de ERC 2024](https://static.elsevier.es/nad/kdigo2024.pdf).
- **OMS/OPS:** terminología de cargos y traducción del JNC 7 histórico, consultada como contenido indexado. [OMS](https://www.who.int/es/news/item/01-07-2017-dr-tedros-takes-office-as-who-director-general), [OPS: JNC 7](https://www3.paho.org/hq/dmdocuments/2010/jnc7_interactivo.pdf).
- **NLM, CDC y NCI:** denominaciones funcionales, posparto, unidades y nombres oficiales. [Déficit neurológico focal](https://www.medlineplus.gov/spanish/ency/article/000701.htm), [preeclampsia posparto](https://www.medlineplus.gov/spanish/ency/patientinstructions/000606.htm), [unidades](https://medlineplus.gov/spanish/pruebas-de-laboratorio/como-entender-sus-resultados-de-pruebas-de-laboratorio/), [NHANES](https://www.cdc.gov/nchs/nhanes/participant/spanish/participant-es.htm), [razón de momios](https://www.cancer.gov/espanol/publicaciones/diccionarios/diccionario-cancer/def/oportunidad-relativa).

Publicaciones complementarias de IACS, CCSS, sociedades especializadas y centros académicos resolvieron términos específicos. El catálogo distingue artículo original, revisión, consenso, título, resumen y palabras clave bilingües. Los documentos antiguos se usaron para atestación terminológica, sin actualizar con ellos protocolos o puntos de corte.

La denominación española de PA marcadamente elevada asintomática se localizó en un extracto indexado de la revista Red Dávila de 2025, página impresa 53. La descarga directa fue bloqueada y la apertura redirigió al inicio; no se afirma lectura del PDF completo ni se inventa una autoría de artículo. Se contrastó además con el contexto oficial AHA. Todas estas limitaciones permanecen en el catálogo.

El conector Deep Research solicitado inicialmente no estaba disponible entre las herramientas expuestas. Se hicieron consultas web reales, sin simular una ejecución de ese conector ni una búsqueda sistemática exhaustiva.

## Localizadores, cobertura e integridad

`pdf_page` significa página del archivo desde 1, que puede diferir de la paginación impresa. Los demás índices son bloques locales de extracción desde 1. Los títulos, resúmenes y palabras clave bilingües se etiquetan expresamente; estas últimas pueden atestar ambos idiomas en un mismo registro bibliográfico.

La búsqueda normaliza mayúsculas, tildes, ligaduras, puntuación y cortes de línea. Se conserva la forma localizada, incluidas anomalías de extracción, y se distingue de la redacción preferida. Los localizadores y huellas permiten revisar la evidencia contra el corpus local.

| Categoría del inventario | Registros | Cotejados EN/ES | Pendientes |
|---|---:|---:|---:|
{{CATEGORIES}}

Se comprobaron 657 identificadores y 1.314 atestaciones, idioma, URL, localizador, huellas y coherencia entre archivos; también la conservación de los 600 registros previos y del original y candidato. El ZIP se contrastó con el manifiesto. Las publicaciones completas y el corpus local se excluyen del ZIP.

Las pruebas del normalizador pertenecen al lote inicial y no se repitieron, porque original y candidato siguen idénticos. No se midieron exactitud de ASR, latencia ni traducción en directo. Todos los registros mantienen prohibida la sustitución automática sin revisión.

## Tiempo y continuidad

Se conservan las dos sesiones previas, de **27,58** y **41,60 minutos de reloj**. Esta sesión registra **{{SESSION3_MINUTES}} minutos**, desde el 20 de octubre a las 23:40:57 hasta el cierre indicado del 21 de octubre, hora de Bolivia. La suma es **{{MINUTES}} minutos** e incluye investigación, curación, documentación y validación. Se excluyen las dos pausas. No se midieron horas efectivas por separado ni se afirman tres horas efectivas.

La verificación documental de los 657 pares queda completada. La revisión clínica independiente y la aprobación individual de alias o usos operacionales siguen siendo trabajos distintos. No hay investigación en segundo plano ni integración que vaya a ejecutarse automáticamente.
