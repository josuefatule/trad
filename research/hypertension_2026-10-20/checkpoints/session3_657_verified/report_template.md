# TRAD — Investigación terminológica de hipertensión arterial EN↔ES

**Fecha de referencia: 20 de octubre de 2026. Estado: avance de investigación, candidato de integración sin aprobar.**

Se entregan los cuatro archivos solicitados en una carpeta separada. El glosario original conserva su contenido y su hash. No se modificó código de producción, configuración, parámetros ni modelos; no se integró el candidato ni se crearon commits o tareas programadas.

## 1. Resultado y límites del lote

{{COUNTS}}

Los **617 candidatos con respaldo bibliográfico** son una selección para investigación: sus fuentes apoyan el concepto o su contexto especializado. No todos tienen atestación individual de cada forma inglesa, alias y traducción. **Solo las 52 equivalencias identificadas como contrastadas se cotejaron en fuentes EN y ES**; ello tampoco equivale a certificación por un clínico independiente.

Por tanto, **no se declara cumplida la meta de 600–1.000 conceptos bilingües únicos y plenamente verificados**. Los 657 registros incluyen unidades de lenguaje de congreso, procedimientos, subtipos, nombres de estudios y clases farmacológicas, además de entidades clínicas. Se agruparon diez formas léxicas para no contar adjetivos o variantes obvias como conceptos adicionales. La revisión de equivalencia conceptual no es exhaustiva.

{{TIMING}}

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

{{CATEGORIES}}

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

{{REMOVED_ALIASES}}

Los doce alias se conservan en la trazabilidad de investigación; su retirada no borra el concepto. No se alteró el archivo original.

### Pruebas adversariales

{{ADVERSARIAL}}

El expediente de validación incluye 19 casos adversariales y 22 casos con el conjunto nuevo aislado. Los nuevos términos no produjeron correcciones automáticas en esas pruebas. La política suggest puede generar propuestas fuzzy: **sus puntuaciones de cadenas no son probabilidades clínicas ni evidencia de equivalencia** y no deben convertirse en reemplazos automáticos.

Se verificaron sintaxis JSON, unicidad de identificadores y canónicos normalizados, correspondencia de fuentes y carga con el normalizador real. El candidato no contiene campos operacionales adicionales. No se detectaron colisiones exactas que impidan cargarlo.

La expansión heredada BP→BLOOD PRESSURE sigue activa. También permanecen las políticas fuzzy del original. No se declara al candidato seguro para activación general por superar estas pruebas de texto.

**Hash SHA-256 original, antes y después:**
4a4920d3ff9404db5601c1c8f832dde4fdeb180dc95d3f06037576ec726c2896

## 9. Qué queda pendiente

{{PENDING}}

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

{{SOURCES}}
