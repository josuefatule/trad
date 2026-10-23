# TRAD — Investigación terminológica de hipertensión arterial EN↔ES

**Fecha de referencia: 20 de octubre de 2026. Estado: avance de investigación, candidato de integración sin aprobar.**

Se entregan los cuatro archivos solicitados en una carpeta separada. El glosario original conserva su contenido y su hash. No se modificó código de producción, configuración, parámetros ni modelos; no se integró el candidato ni se crearon commits o tareas programadas.

## 1. Resultado y límites del lote

| Medida | Cantidad |
|---|---:|
| Entradas originales | 294 |
| Formas léxicas curadas | 667 |
| Registros de investigación tras agrupación | 657 |
| Candidatos con respaldo conceptual o temático | 617 |
| Registros con fuente puntual pendiente | 40 |
| Equivalencias cotejadas en fuentes EN y ES | 52 |
| Traducciones propuestas pendientes de cotejo individual | 605 |
| Registros con validación clínica independiente | 0 |
| Términos operacionales nuevos de solo sugerencia | 346 |
| Propuestas nuevas retenidas fuera del candidato | 26 |
| Entradas del candidato operacional | 640 |
| Fuentes seleccionadas en el catálogo | 70 |

Los **617 candidatos con respaldo bibliográfico** son una selección para investigación: sus fuentes apoyan el concepto o su contexto especializado. No todos tienen atestación individual de cada forma inglesa, alias y traducción. **Solo las 52 equivalencias identificadas como contrastadas se cotejaron en fuentes EN y ES**; ello tampoco equivale a certificación por un clínico independiente.

Por tanto, **no se declara cumplida la meta de 600–1.000 conceptos bilingües únicos y plenamente verificados**. Los 657 registros incluyen unidades de lenguaje de congreso, procedimientos, subtipos, nombres de estudios y clases farmacológicas, además de entidades clínicas. Se agruparon diez formas léxicas para no contar adjetivos o variantes obvias como conceptos adicionales. La revisión de equivalencia conceptual no es exhaustiva.

El intervalo observado va de **16:08:31 a 16:36:06 UTC−04:00**, aproximadamente **27.60 minutos de reloj**. Incluye investigación, curación, documentación y validación; no se midieron por separado horas efectivas. **No se alcanzaron ni se afirman las tres horas efectivas solicitadas.** Este lote acotado se entrega con sus pendientes para continuidad.

El conector solicitado Deep Research no figuró entre las herramientas disponibles y no fue localizado en la búsqueda de plugins. Se realizaron consultas reales mediante acceso web. El índice de consultas conserva resultados y enlaces observados; no constituye una búsqueda sistemática exhaustiva ni un registro PRISMA. No hay investigación ejecutándose en segundo plano.

## 2. Archivos y uso

- [Dataset bilingüe enriquecido](hypertension_research_en_es.json): términos, traducciones propuestas, categorías, fuentes, riesgos, revisión y correspondencia con el original.
- [Candidato operacional](medical_base_en_extended_candidate.json): exclusivamente el esquema inglés que admite el normalizador; no sustituye al original.
- [Registro de continuidad](hypertension_research_progress.json): identificadores pendientes, categorías, fuentes y siguiente trabajo.
- Este informe: método, resultados, limitaciones y bibliografía.
- [Esquema documentado](DATASET_SCHEMA.md), [catálogo de fuentes](sources.json), [validación](validation_results.json), [auditoría original](original_glossary_audit.json) e [índice de consultas](web_consultation_index.json) permiten revisar la trazabilidad.
- Las tablas de curación y actualizaciones de evidencia se conservan para retomar el trabajo sin reconstruir el inventario. No son archivos de producción.

## 3. Método y ciclos completados

**A — Auditoría inicial.** Se leyó el adjunto y el JSON completo. Se verificaron las claves raíz, tipos de entrada, políticas y umbrales con el cargador real. Las 294 entradas originales usan 148 políticas exactas y 146 fuzzy. No aparecieron colisiones exactas según la tokenización del sistema. El cribado de pares canónicos identificó 32 pares similares; ese cribado no prueba que todos produzcan una sustitución en ejecución.

**B1 — Guías y medición.** Se priorizaron ESC, ACC, AHA, PubMed, OMS y KDIGO. Se comprobó el catálogo de versiones y se estudiaron medición fuera del consultorio, clasificación, fenotipos y objetivos dependientes de sociedad. Se separaron diagnóstico, umbral para iniciar tratamiento y objetivo durante el tratamiento.

**C1 — Revisión adversarial.** Se cuestionaron las equivalencias resistente/refractaria, elevación grave/emergencia, hipertensión sistémica/pulmonar, aldosteronismo primario/hiperaldosteronismo y medidas de efecto. Se separó la verificación del concepto de la traducción. Las dudas no se resolvieron contando la autorrevisión como evidencia independiente.

**D1 — Contraste externo.** Se consultaron la traducción SEC de ESC 2024, NLM en español y recomendaciones de Endocrine Society 2025. La fuente española permitió detectar colisiones entre idiomas como PA, HRV y ECA. Las páginas o artículos inaccesibles se registraron como acceso parcial.

**B2 — Ampliación por especialidades.** Se incorporaron vocabulario renal/endocrino, mecanismos del SRAA, fármacos genéricos, intervenciones, embarazo, daño orgánico, prevención y ensayos. Los nombres de tratamientos en investigación no implican aprobación regulatoria ni intercambiabilidad.

**C2/D2 — Corrección de propuestas.** Se reprodujeron sustituciones erróneas del original; se retiraron doce alias solo del candidato. Se corrigió una variante española que añadía indebidamente “agudo” a infarto de miocardio y se mantuvieron separados pequeño para edad gestacional y restricción del crecimiento fetal. Se buscaron fuentes adicionales para pruebas de supresión, síndromes monogénicos, fármacos recientes y significados alternativos de PRA/PAC/MRA/RAS.

**V — Validación final.** Se analizaron los JSON, se cargó el candidato con el normalizador real, se comprobaron estructura y conservación de parámetros, y se ejecutaron pruebas adversariales de texto. No se efectuó un experimento de reconocimiento de audio ni una validación clínica independiente.

## 4. Guías: versiones y discrepancias

| Ámbito | Documento comprobado | Lectura y límite |
|---|---|---|
| Hipertensión general ESC | ESC 2024; la página oficial enlaza un corrigendum de febrero de 2025 | Catálogo, página oficial y secciones de traducción SEC; no se verificó que esa traducción incluya toda corrección posterior |
| Estados Unidos | AHA/ACC 2025, que reemplaza 2017 | Resumen y materiales oficiales; no lectura integral del artículo de la guía |
| Presión arterial en ERC | KDIGO 2021 | Página oficial y resumen para clínicos |
| ERC general | KDIGO 2024 | Secciones del PDF oficial; una ruta de alojamiento de 2026 no cambia el año de la guía |
| Embarazo cardiovascular | ESC 2025 | Resumen y diapositivas oficiales indexadas; pendiente la lectura integral de hipertensión obstétrica |
| Aldosteronismo primario | Endocrine Society 2025 | Recomendaciones oficiales y registro bibliográfico |
| OMS | Directriz farmacológica de 2021; ficha de hipertensión de 2025 | Metadatos de la directriz y ficha; no se leyó el PDF completo |
| ISH | Recursos oficiales de las guías globales de 2020 | Página oficial y registro PubMed; no lectura integral |

La guía estadounidense de 2025 sustituyó la de 2017; las menciones históricas de 2017 siguen siendo términos válidos y no se reemplazan silenciosamente. La página ESC consultada sigue identificando la guía general de hipertensión de 2024. [ACC 2025](https://www.acc.org/About-ACC/Press-Releases/2025/08/13/20/03/New-high-blood-pressure-guideline-emphasizes-prevention-early-treatment-to-reduce-CVD-risk), [ESC](https://www.escardio.org/guidelines/clinical-practice-guidelines/all-esc-practice-guidelines/elevated-blood-pressure-and-hypertension/).

La categoría **elevated blood pressure** difiere entre AHA/ACC y ESC. AHA/ACC 2025 conserva un estadio 1 desde PAS 130–139 o PAD 80–89 mmHg; ESC 2024 mantiene hipertensión en consultorio desde PAS ≥140 o PAD ≥90 mmHg y una categoría más amplia de presión elevada. Esos nombres requieren sociedad, año y método de medición; no son traducciones intercambiables de una clasificación universal. [AHA: clasificación](https://professional.heart.org/en/science-news/2025-high-blood-pressure-guideline/top-things-to-know), [SEC: secciones 5–6](https://secardiologia.es/images/2023/Gu%C3%ADas/Final_GPC_ESC_2024_PA_elevada_e_hipertensio%CC%81n.pdf).

El objetivo de presión sistólica de KDIGO se refiere a medición estandarizada en una población y contexto determinados. No autoriza aplicar un factor de conversión a una lectura habitual ni trasladar automáticamente objetivos entre embarazo, trasplante, diálisis y población general. [KDIGO: resumen para clínicos](https://kdigo.org/wp-content/uploads/2021/03/Top-10-Takeaways-Clinicians-KDIGO-BP-Guideline.pdf).

Se identificaron documentos cardiovasculares de 2026 relacionados con ERC y otros temas en el catálogo ESC. Su existencia no se presenta como revisión completa de esas subespecialidades. [Calendario oficial ESC](https://www.escardio.org/guidelines/clinical-practice-guidelines/guidelines-development/guidelines-publication-schedule/).

## 5. Cobertura de las áreas solicitadas

| Categoría | Registros | Fuente puntual pendiente |
|---|---:|---:|
| Clasificación y fenotipos | 41 | 2 |
| Medición y monitorización | 51 | 0 |
| Guías y sociedades | 10 | 0 |
| Lenguaje de congreso | 22 | 10 |
| Riesgo y prevención | 30 | 0 |
| Métodos de investigación | 38 | 3 |
| Ensayos, cohortes y encuestas | 23 | 10 |
| Endocrinología y mecanismos renales | 83 | 0 |
| Nefrología | 37 | 0 |
| Tratamientos y estrategias | 54 | 0 |
| Fármacos y clases | 69 | 4 |
| Daño orgánico y enfermedad cardiovascular | 55 | 0 |
| Estilo de vida | 27 | 0 |
| Unidades y vocabulario de medición | 15 | 0 |
| Fisiología y fisiopatología | 45 | 7 |
| Emergencias y daño agudo | 19 | 2 |
| Embarazo | 25 | 2 |
| Poblaciones especiales | 13 | 0 |


Las 16 áreas del encargo están representadas en estas 18 categorías de curación. Las áreas de fisiología y fisiopatología comparten registros; primaria/secundaria/resistente se distribuyen entre clasificación y endocrinología. Farmacología y tratamiento están separados. **Ninguna categoría se marca como totalmente verificada.**

Las fuentes más extensas fueron la traducción SEC de ESC 2024 y KDIGO 2024, leídas por secciones seleccionadas. Para muchos ensayos y consensos se dispuso de resumen o extractos indexados, no del texto completo. La revisión se orientó a terminología, no a reproducir protocolos, dosis ni recomendaciones para pacientes.

## 6. Equivalencias y riesgos de mayor importancia

| Términos | Decisión |
|---|---|
| Systemic arterial hypertension / pulmonary hypertension | Entidades separadas; hipertensión pulmonar solo aparece como referencia de límite de alcance, fuera del conteo |
| Resistant / refractory hypertension | No intercambiar; refractaria tiene una definición investigativa más restrictiva |
| Apparent treatment-resistant / true resistant hypertension | La sospecha no certifica resistencia verdadera |
| Hypertensive emergency / urgency / severe hypertension | Conservar la diferencia por daño agudo y la terminología de cada sociedad |
| Primary aldosteronism / hyperaldosteronism | El primero es un subtipo; no convertir toda producción excesiva de aldosterona en origen primario |
| White-coat hypertension / white-coat effect | No equivalencia automática; importa si el paciente recibe tratamiento |
| Nocturnal hypertension / non-dipping | Valor absoluto nocturno y patrón relativo son conceptos diferentes |
| Renal artery stenosis / renovascular hypertension | La lesión anatómica no demuestra causalidad individual |
| Albuminuria / proteinuria | No son equivalentes absolutos |
| Renal insufficiency / CKD / kidney failure / AKI | Conservar especificidad, cronicidad y fase aguda |
| PRA / direct renin concentration | Actividad y concentración no son la misma magnitud |
| Preeclampsia / eclampsia / gestational hypertension | Mantener las entidades y calificadores obstétricos |
| Fetal growth restriction / small for gestational age | Trastorno del crecimiento y clasificación del tamaño permanecen separados |
| Hazard ratio / relative risk / odds ratio | No traducirlos como una única medida |
| Serious / severe adverse event | Gravedad regulatoria e intensidad no son automáticamente equivalentes |
| Single-pill combination / polypill | Una combinación antihipertensiva no siempre es una polipíldora cardiovascular |
| Midodrine / droxidopa | Se incluyen por contexto de hipotensión; no se clasifican como antihipertensivos |

La hipertensión pulmonar afecta otra circulación. El propio material AHA la diferencia de la hipertensión sistémica. [AHA](https://www.heart.org/en/health-topics/high-blood-pressure/the-facts-about-high-blood-pressure/pulmonary-hypertension-high-blood-pressure-in-the-heart-to-lung-system).

El ensayo CHAP definió un desenlace de seguridad de peso pequeño para la edad gestacional. No se tomó “bajo peso al nacer” como equivalente estricto. Se cotejó el término español en NLM. [CHAP: resumen primario](https://pubmed.ncbi.nlm.nih.gov/35363951/), [NLM en español](https://medlineplus.gov/spanish/ency/article/002302.htm).

### Acrónimos

El dataset incluye significados alternativos y exige contexto. La única colisión exacta entre registros del inventario de alias de investigación es **MRA**, conservada deliberadamente para documentar dos significados. No se exporta como alias operativo nuevo.

- PA: aldosteronismo primario en inglés; presión arterial en español.
- MRA: antagonista del receptor mineralocorticoide o angiografía por resonancia magnética.
- RAS: sistema renina-angiotensina o estenosis de arteria renal; también puede aparecer en genética.
- PRA: actividad de renina plasmática o anticuerpos reactivos frente a panel.
- PAC: concentración plasmática de aldosterona o contracción auricular prematura.
- HR: frecuencia cardíaca o hazard ratio.
- HRV: variabilidad de la frecuencia cardíaca en inglés; hipertensión renovascular en la traducción SEC.
- ECA, RAR e IC: colisiones frecuentes entre vocabulario de fisiología, riesgo y metodología en español.
- NO: óxido nítrico o una negación; nunca se exporta como alias nuevo.

Las colisiones PRA, RAS/MRA y PAC se contrastaron con resúmenes primarios de trasplante, imagen renal y electrocardiografía. Son fuentes usadas para verificar lenguaje, sin añadir sus tratamientos o resultados al glosario de hipertensión. [PRA](https://pubmed.ncbi.nlm.nih.gov/15518726/), [RAS/MRA](https://pubmed.ncbi.nlm.nih.gov/21542417/), [PAC](https://pubmed.ncbi.nlm.nih.gov/33790146/).

## 7. Qué usa realmente TRAD

La inspección del código local comprobó lo siguiente:

1. En EN→ES, el modo de normalización es **identity** y el cliente selecciona **IdentityNormalizer** cuando el idioma fuente es inglés.
2. El normalizador terminológico admite exact, fuzzy y suggest. Es una etapa de posprocesamiento de texto.
3. La traducción recibe el texto normalizado. No se encontró una carga automática de este candidato como diccionario bilingüe en el motor.
4. En el laboratorio existe un experimento separado que puede usar términos como contexto de Faster-Whisper; eso no demuestra su activación en la sesión en vivo.
5. No se comprobó el estado de un proceso de producción abierto ni su configuración de ejecución.

Referencias locales: [direcciones de sesión](C:/live-captions/app/session_direction.py:17), [selección del normalizador](C:/live-captions/app/asr/whisperlivekit_client.py:74), [normalizador de identidad](C:/live-captions/app/captions/identity_normalizer.py:1), [políticas y cargador](C:/live-captions/app/captions/terminology_normalizer.py:215), [entrada de traducción](C:/live-captions/app/translation/engine.py:243), [experimento de laboratorio](C:/live-captions/trad_lab/runner.py:92).

**No hay evidencia de que ampliar este JSON mejore automáticamente el ASR.** No se modificaron prompts, hotwords, modelos, configuración ni código para incorporarlo.

## 8. Candidato operacional y validación

El candidato conserva las claves raíz name, version y terms y la versión 2. Contiene las 294 entradas canónicas originales y 346 entradas nuevas con auto_apply=suggest. No exporta alias ni variantes nuevos del inventario de investigación, ni palabras españolas a un normalizador inglés.

Las políticas exact/fuzzy y todos los umbrales de las entradas originales permanecen iguales en el candidato. Solo se retiran los siguientes alias por ambigüedad, título incorrecto o equivalencia gramatical inadecuada:

| Entrada | Alias retirados del candidato |
|---|---|
| mean arterial pressure | MAP |
| JNC 8 report | Eighth Joint National Committee |
| primary aldosteronism | PA |
| plasma renin activity | PRA |
| plasma aldosterone concentration | PAC |
| renin-angiotensin system | RAS |
| mineralocorticoid receptor | MR |
| mineralocorticoid receptor antagonists | MRAs, MRA |
| aldosterone-producing adenoma | APA |
| diuretics | diuretic therapy |
| frailty | frail patients |

Los doce alias se conservan en la trazabilidad de investigación; su retirada no borra el concepto. No se alteró el archivo original.

### Pruebas adversariales

| Entrada de prueba | Salida con original | Salida con candidato |
|---|---|---|
| The PA pressure was measured. | The PRIMARY ALDOSTERONISM pressure was measured. | The PA pressure was measured. |
| Review the MRA of the renal arteries. | Review the MINERALOCORTICOID RECEPTOR ANTAGONISTS of the renal arteries. | Review the MRA of the renal arteries. |
| A RAS mutation was detected. | A RENIN-ANGIOTENSIN SYSTEM mutation was detected. | A RAS mutation was detected. |
| Follow the MAP on the screen. | Follow the MEAN ARTERIAL PRESSURE on the screen. | Follow the MAP on the screen. |
| The PAC burden increased. | The PLASMA ALDOSTERONE CONCENTRATION burden increased. | The PAC burden increased. |
| These frail patients need follow-up. | These frailty need follow-up. | These frail patients need follow-up. |

El expediente de validación incluye 19 casos adversariales y 22 casos con el conjunto nuevo aislado. Los nuevos términos no produjeron correcciones automáticas en esas pruebas. La política suggest puede generar propuestas fuzzy: **sus puntuaciones de cadenas no son probabilidades clínicas ni evidencia de equivalencia** y no deben convertirse en reemplazos automáticos.

Se verificaron sintaxis JSON, unicidad de identificadores y canónicos normalizados, correspondencia de fuentes y carga con el normalizador real. El candidato no contiene campos operacionales adicionales. No se detectaron colisiones exactas que impidan cargarlo.

La expansión heredada BP→BLOOD PRESSURE sigue activa. También permanecen las políticas fuzzy del original. No se declara al candidato seguro para activación general por superar estas pruebas de texto.

**Hash SHA-256 original, antes y después:**
4a4920d3ff9404db5601c1c8f832dde4fdeb180dc95d3f06037576ec726c2896

## 9. Qué queda pendiente

- JNC 7 guideline (HTN_8d17bae1bc5a)
- guideline-driven management (HTN_b0de6f8f7d51)
- evidence-based medicine (HTN_fb95da26d020)
- evidence-based review (HTN_1b881806cbc3)
- clinical implications (HTN_5418fb6ca9f7)
- treatment threshold (HTN_e866166f56aa)
- clinical decision-making (HTN_7e17f880a489)
- CARDIA study (HTN_2674e0e256e0)
- National Institutes of Health (HTN_de7d5a3bf89e)
- Task Force (HTN_37fd92fc0bd4)
- co-chair (HTN_c55b21ee723a)
- pharmacologic management (HTN_b82e725f2d5b)
- clinical guidelines implementation (HTN_1461e740924a)
- as low as reasonably achievable (HTN_73996112033d)
- arterial compliance (HTN_ab697e405d94)
- baroreflex sensitivity (HTN_69258c163a94)
- nitric oxide (HTN_c044a9939be3)
- endothelin-1 (HTN_f70f3577aec5)
- norepinephrine (HTN_54f88fe6d26e)
- epinephrine (HTN_d13d73d7874a)
- vasopressin (HTN_0717fd030271)
- sustained hypertension (HTN_0ca1534f47b6)
- labile hypertension (HTN_28e3f8f90aad)
- sodium nitroprusside (HTN_1c57912cead1)
- nitroglycerin (HTN_32cc57600213)
- fenoldopam (HTN_ac6d1bdc419d)
- urapidil (HTN_1c605e842171)
- thrombotic microangiopathy (HTN_b26b18175258)
- flash pulmonary edema (HTN_073d741b83bc)
- soluble fms-like tyrosine kinase-1 (HTN_551519d50a25)
- placental growth factor (HTN_a64c492b2ca9)
- HYVET trial (HTN_3062e896a014)
- ACCOMPLISH trial (HTN_6eb1860586f5)
- ASCOT-BPLA trial (HTN_7083e8c3981d)
- RADIANCE-HTN TRIO trial (HTN_65b7bf5b1b54)
- SPYRAL HTN-OFF MED trial (HTN_8b09e2cea13f)
- SPYRAL HTN-ON MED trial (HTN_2bf1d385e126)
- odds ratio (HTN_9a5b7b5c9e81)
- number needed to harm (HTN_8098ae1ba6fd)
- relative risk reduction (HTN_1ca84c094bc5)

Además del cotejo puntual de esos registros, quedan 605 traducciones propuestas por verificar individualmente, la evaluación independiente de clínica/terminología y una revisión más amplia de alias heredados. No se consideran aprobados los alias que simplemente se conservaron del original.

La continuación debe empezar por los identificadores y fuentes de hypertension_research_progress.json, sin repetir la curación inicial. Prioridades:

1. Cotejar las traducciones de mayor riesgo y los registros pendientes con fuentes específicas, conservando la fuente para cada equivalencia.
2. Leer íntegramente las secciones obstétricas de 2025, los documentos cardiorrenales pertinentes de 2026 y corrigenda que no fueron accesibles.
3. Verificar expansiones pendientes de nombres de ensayos y las expresiones generales de congreso; no llenar lagunas por memoria.
4. Revisar posibles falsos positivos de las reglas fuzzy heredadas, cifras, unidades, negaciones, lateralidad y nombres de fármacos.
5. Evaluar una copia aislada con audio representativo y comparación contra la línea base: precisión de términos, errores clínicamente relevantes y latencia. Este lote no permite anticipar el resultado.
6. Mantener el inventario bilingüe separado del normalizador inglés hasta definir y validar cómo se utilizaría para traducción.

## 10. Bibliografía y alcance de acceso

Todas las fuentes siguientes se consultaron el 20 de octubre de 2026. “PDF por secciones” significa lectura de secciones seleccionadas, no lectura integral. “Indexado” significa que la evidencia accesible procedió de extractos de búsqueda o del registro, incluso si el enlace directo falló. Los metadatos sin fecha confirmada se dejan vacíos.

Los PDF de ciertos materiales ESC devolvieron 403; OUP no permitió abrir el original de ESC 2024, y varios recursos PMC/NCBI devolvieron comprobación de navegador o páginas incompletas. Se usaron fuentes oficiales alternativas y se declaró el límite. No se registró un DOI sin haberlo observado en una fuente.

| ID | Fuente | Idioma | Acceso registrado | Fecha del documento |
|---|---|---|---|---|
| S01 | [ESC 2024: página oficial y corrección de 2025](https://www.escardio.org/guidelines/clinical-practice-guidelines/all-esc-practice-guidelines/elevated-blood-pressure-and-hypertension/) | en | official_landing_page | 2024-08-30 |
| S02 | [AHA/ACC 2025: Top Things to Know](https://professional.heart.org/en/science-news/2025-high-blood-pressure-guideline/top-things-to-know) | en | official_summary_read | 2025-08-14 |
| S03 | [ACC: nueva guía estadounidense de 2025](https://www.acc.org/About-ACC/Press-Releases/2025/08/13/20/03/New-high-blood-pressure-guideline-emphasizes-prevention-early-treatment-to-reduce-CVD-risk) | en | official_summary_read | 2025-08-14 |
| S04 | [KDIGO 2021: Top 10 Takeaways for Clinicians](https://kdigo.org/wp-content/uploads/2021/03/Top-10-Takeaways-Clinicians-KDIGO-BP-Guideline.pdf) | en | full_pdf_selected_sections_read | 2021 |
| S05 | [KDIGO 2024 Clinical Practice Guideline for Evaluation and Management of CKD](https://kdigo.org/wp-content/uploads/2026/04/KDIGO-2024-CKD-Guideline.pdf) | en | full_pdf_selected_sections_read | 2024 |
| S06 | [OMS: Hipertensión](https://www.who.int/es/news-room/fact-sheets/detail/hypertension) | es | full_html_read | 2025-09-25 |
| S07 | [Types of Blood Pressure Medications](https://www.heart.org/en/health-topics/high-blood-pressure/changes-you-can-make-to-manage-high-blood-pressure/types-of-blood-pressure-medications) | en | full_html_read | 2025-08-14 |
| S08 | [Measurement of Blood Pressure in Humans](https://pubmed.ncbi.nlm.nih.gov/30827125/) | en | abstract_and_indexed_full_text_excerpts | 2019 |
| S09 | [Resistant Hypertension: Detection, Evaluation, and Management](https://pubmed.ncbi.nlm.nih.gov/30354828/) | en | abstract_read | 2018 |
| S10 | [Primary Aldosteronism: Endocrine Society guideline recommendations](https://www.endocrine.org/clinical-practice-guidelines/primary-aldosteronism-2) | en | official_recommendations_read | 2025-07-14 |
| S11 | [An Update on Refractory Hypertension](https://pubmed.ncbi.nlm.nih.gov/35384577/) | en | indexed_abstract_read | 2022 |
| S12 | [Hypertension in Pregnancy: Diagnosis, Blood Pressure Goals, and Pharmacotherapy](https://pubmed.ncbi.nlm.nih.gov/34905954/) | en | indexed_abstract_read | 2022 |
| S13 | [Chronic Hypertension and Pregnancy — CHAP](https://www.acc.org/Latest-in-Cardiology/Clinical-Trials/2022/04/01/03/19/CHAP) | en | official_trial_summary_read | 2022 |
| S14 | [Pheochromocytoma and paraganglioma: endocrine society guideline](https://pubmed.ncbi.nlm.nih.gov/24893135/) | en | indexed_abstract_read | 2014 |
| S15 | [The Management of Elevated Blood Pressure in the Acute Care Setting](https://pubmed.ncbi.nlm.nih.gov/38804130/) | en | indexed_abstract_read | 2024 |
| S16 | [Revascularization for Renovascular Disease](https://pubmed.ncbi.nlm.nih.gov/35708012/) | en | indexed_abstract_and_figure_legend_read | 2022 |
| S17 | [Hypertension — Oparil et al.](https://pubmed.ncbi.nlm.nih.gov/29565029/) | en | indexed_abstract_figures_and_full_text_excerpts | 2018 |
| S18 | [SPRINT: A Randomized Trial of Intensive versus Standard Blood-Pressure Control](https://pubmed.ncbi.nlm.nih.gov/26551272/) | en | indexed_abstract_read | 2015 |
| S19 | [ALLHAT: Major outcomes in high-risk hypertensive patients](https://pubmed.ncbi.nlm.nih.gov/12479763/) | en | indexed_abstract_read | 2002 |
| S20 | [PATHWAY-2: randomized double-blind crossover trial](https://pubmed.ncbi.nlm.nih.gov/26414968/) | en | indexed_abstract_read | 2015 |
| S21 | [CLICK: Chlorthalidone for Hypertension in Advanced CKD](https://pubmed.ncbi.nlm.nih.gov/34739197/) | en | indexed_abstract_read | 2021 |
| S22 | [BPROAD: Intensive Blood-Pressure Control in Patients with Type 2 Diabetes](https://pubmed.ncbi.nlm.nih.gov/39555827/) | en | indexed_abstract_read | 2025 |
| S23 | [STEP: Trial of Intensive Blood-Pressure Control in Older Patients with Hypertension](https://pubmed.ncbi.nlm.nih.gov/34491661/) | en | indexed_abstract_read | 2021 |
| S24 | [Catheter-Based Renal Denervation in HTN: Key Points](https://www.acc.org/latest-in-cardiology/ten-points-to-remember/2024/10/14/19/44/effects-of-catheter-based) | en | official_summary_read | 2024-10-14 |
| S25 | [DASH: A clinical trial of the effects of dietary patterns on blood pressure](https://pubmed.ncbi.nlm.nih.gov/9099655/) | en | indexed_abstract_read | 1997 |
| S26 | [Orthostatic Hypotension in Adults With Hypertension](https://pubmed.ncbi.nlm.nih.gov/38205630/) | en | indexed_abstract_read | 2024 |
| S27 | [Obstructive Sleep Apnea and Cardiovascular Disease](https://pubmed.ncbi.nlm.nih.gov/34148375/) | en | indexed_abstract_read | 2021 |
| S28 | [AAP: Screening and Management of High Blood Pressure in Children and Adolescents](https://publications.aap.org/pediatrics/article/140/3/e20171904/38358/Clinical-Practice-Guideline-for-Screening-and) | en | indexed_selected_sections_read | 2017 |
| S29 | [Guía ESC 2024: traducción revisada por la Sociedad Española de Cardiología](https://secardiologia.es/images/2023/Gu%C3%ADas/Final_GPC_ESC_2024_PA_elevada_e_hipertensio%CC%81n.pdf) | es | full_pdf_selected_sections_read | 2024 |
| S30 | [MedlinePlus: Prueba de renina](https://medlineplus.gov/spanish/pruebas-de-laboratorio/prueba-de-renina/) | es | full_html_read | No confirmada |
| S31 | [MedlinePlus: Prueba de aldosterona](https://medlineplus.gov/spanish/pruebas-de-laboratorio/prueba-de-aldosterona/) | es | indexed_selected_sections_read | No confirmada |
| S32 | [MedlinePlus: Medicamentos antihipertensivos](https://medlineplus.gov/spanish/ency/article/007484.htm) | es | full_html_read | No confirmada |
| S33 | [MedlinePlus: Clortalidona](https://www.medlineplus.gov/spanish/druginfo/meds/a682342-es.html) | es | indexed_selected_sections_read | No confirmada |
| S34 | [2020 International Society of Hypertension Global Hypertension Practice Guidelines](https://pubmed.ncbi.nlm.nih.gov/32370572/) | en | indexed_record_and_mesh_read | 2020 |
| S35 | [ESC Guidelines Publication Schedule](https://www.escardio.org/guidelines/clinical-practice-guidelines/guidelines-development/guidelines-publication-schedule/) | en | official_schedule_read | No confirmada |
| S36 | [SSaSS: Effect of Salt Substitution on Cardiovascular Events and Death](https://pubmed.ncbi.nlm.nih.gov/34459569/) | en | indexed_abstract_read | 2021 |
| S37 | [Pulmonary Hypertension — High Blood Pressure in the Heart-to-Lung System](https://www.heart.org/en/health-topics/high-blood-pressure/the-facts-about-high-blood-pressure/pulmonary-hypertension-high-blood-pressure-in-the-heart-to-lung-system) | en | indexed_selected_sections_read | No confirmada |
| S38 | [Advance-HTN: Lorundrostat Efficacy and Safety in Uncontrolled Hypertension](https://pubmed.ncbi.nlm.nih.gov/40267417/) | en | indexed_abstract_read | 2025 |
| S39 | [AHA: nueva guía de presión arterial alta, versión española](https://newsroom.heart.org/news/la-nueva-guia-sobre-la-presion-arterial-alta-enfatiza-la-prevencion-y-el-tratamiento-temprano-para-reducir-el-riesgo-de-ecv) | es | indexed_excerpts_only_direct_open_failed | 2025 |
| S40 | [ESPRIT: New Blood Pressure Target For Individuals at High Risk](https://www.acc.org/latest-in-cardiology/articles/2024/11/05/11/55/new-blood-pressure-target-for-individuals-at-high-risk) | en | indexed_selected_sections_read | 2024 |
| S41 | [Refractory Hypertension: Evidence of Heightened Sympathetic Activity](https://pubmed.ncbi.nlm.nih.gov/25987662/) | en | indexed_abstract_read | 2015 |
| S42 | [KDIGO: Blood Pressure in CKD — página oficial](https://kdigo.org/guidelines/blood-pressure-in-ckd/) | en | official_landing_page_read | No confirmada |
| S43 | [AHA: Orthostatic Hypotension — definición](https://professional.heart.org/en/science-news/orthostatic-hypotension-in-adults-with-hypertension) | en | official_summary_read | 2024-01-11 |
| S44 | [WHO: Directriz para el tratamiento farmacológico de la hipertensión en adultos](https://www.who.int/es/publications/i/item/9789240033986) | es | official_metadata_page_read | 2021 |
| S45 | [ESC: Hypertension — recommended reading](https://www.escardio.org/guidelines/scientific-documents/recommended-reading/hypertension/) | en | official_2026_reading_list_read | 2026-09-11 |
| S46 | [ACCORD-BP: Effects of intensive blood-pressure control in type 2 diabetes mellitus](https://pubmed.ncbi.nlm.nih.gov/20228401/) | en | indexed_abstract_read | 2010 |
| S47 | [CHAP: Treatment for Mild Chronic Hypertension during Pregnancy](https://pubmed.ncbi.nlm.nih.gov/35363951/) | en | indexed_abstract_read | 2022 |
| S48 | [BaxHTN: Efficacy and Safety of Baxdrostat in Uncontrolled and Resistant Hypertension](https://pubmed.ncbi.nlm.nih.gov/40888730/) | en | indexed_title_and_bibliographic_metadata | 2025 |
| S49 | [KARDIA-2: Add-On Treatment With Zilebesiran for Inadequately Controlled Hypertension](https://pubmed.ncbi.nlm.nih.gov/40434761/) | en | indexed_abstract_read | 2025 |
| S50 | [ESC 2025 Guidelines for management of cardiovascular disease and pregnancy — noticia oficial](https://www.escardio.org/news/news-room/congress-news/2025-guidelines-cvd-pregnancy/) | en | official_summary_read | 2025-08-31 |
| S51 | [MedlinePlus: Pequeño para la edad gestacional](https://medlineplus.gov/spanish/ency/article/002302.htm) | es | indexed_html_read | 2025-08-18 |
| S52 | [Manejo de la disfunción autonómica en la enfermedad de Parkinson](https://pubmed.ncbi.nlm.nih.gov/25857860/) | en,es | indexed_bilingual_abstracts_read | 2015 |
| S53 | [Decoding Monogenic Hypertension: A Review of Rare Hypertension Disorders](https://pubmed.ncbi.nlm.nih.gov/39803890/) | en | indexed_abstract_read | 2025 |
| S54 | [Oral Sodium Loading Test Is More Sensitive Than Seated Saline Infusion Test to Confirm Overt Primary Aldosteronism](https://academic.oup.com/jes/advance-article-pdf/doi/10.1210/jendso/bvae209/60812095/bvae209.pdf) | en | indexed_pdf_excerpts_read | 2025 |
| S55 | [Clinical practice guideline for prevention and management of hypertensive disorders of pregnancy — EsSalud](https://pubmed.ncbi.nlm.nih.gov/35503297/) | en,es | indexed_bilingual_abstracts_read | 2022 |
| S56 | [Low-Renin Hypertension](https://pubmed.ncbi.nlm.nih.gov/31655771/) | en | indexed_abstract_read | 2019 |
| S57 | [Magnesium sulfate in preeclampsia: Broad indications, not only in neurological symptoms](https://pubmed.ncbi.nlm.nih.gov/38669914/) | en | indexed_abstract_and_keywords_read | 2024 |
| S58 | [2014 evidence-based guideline for management of high blood pressure in adults: report from panel members appointed to JNC 8](https://pubmed.ncbi.nlm.nih.gov/24352797/) | en | bibliographic_record_verified_in_linked_primary_citation | 2014 |
| S59 | [The reasons for geographic and racial differences in stroke study: objectives and design](https://pubmed.ncbi.nlm.nih.gov/15990444/) | en | indexed_abstract_excerpt_read | 2005 |
| S60 | [About NHANES](https://www.cdc.gov/nchs/nhanes/about/) | en | indexed_official_metadata_read | No confirmada |
| S61 | [Novel Medical Treatments for Hypertension and Related Comorbidities](https://pmc.ncbi.nlm.nih.gov/articles/PMC7101636/) | en | indexed_table_excerpts_read | No confirmada |
| S62 | [2025 ESC pregnancy guidelines — official slides](https://www.escardio.org/static-file/Escardio/Guidelines/Products/Slide%20sets/2025/2025%20official%20slides_Pregnancy.pdf) | en | indexed_official_slide_excerpts_read | 2025 |
| S63 | [Physiology, Mean Arterial Pressure](https://pubmed.ncbi.nlm.nih.gov/30855814/) | en | indexed_book_excerpt_read | 2023-04-10 |
| S64 | [Validation of a new impedance cardiography device for noninvasive hemodynamic measurement in outpatient hypertensive patients](https://pmc.ncbi.nlm.nih.gov/articles/PMC12057702/) | en,es | bilingual_abstract_and_keywords_read | No confirmada |
| S65 | [ISH Global Hypertension Practice Guidelines — página oficial](https://ish-world.com/global-hypertension-practice-guidelines) | en | official_page_read | No confirmada |
| S66 | [Posterior Reversible Encephalopathy Syndrome: A Clinico-Radiological Approach](https://pubmed.ncbi.nlm.nih.gov/39588420/) | en | indexed_abstract_read | 2024-10-26 |
| S67 | [Diagnosis of hypertensive disorders in pregnancy](https://pubmed.ncbi.nlm.nih.gov/40348190/) | en | indexed_abstract_read | 2025 |
| S68 | [Effect of panel-reactive antibody positivity on graft rejection before or after kidney transplantation](https://pubmed.ncbi.nlm.nih.gov/15518726/) | en | indexed_abstract_read | No confirmada |
| S69 | [Comparison of duplex ultrasonography and magnetic resonance imaging in detection of significant renal artery stenosis](https://pubmed.ncbi.nlm.nih.gov/21542417/) | en | indexed_abstract_read | 2011 |
| S70 | [Revisit to the Prognostic Value of Premature Atrial Contraction Burden in 24-h Holter Electrocardiography](https://pubmed.ncbi.nlm.nih.gov/33790146/) | en | indexed_abstract_read | 2021 |

