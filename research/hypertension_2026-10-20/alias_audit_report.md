> **Actualización posterior:** [verificación de las 124 formas sin coincidencia literal previa](surface_verification_124_report.md). La auditoría que sigue es la instantánea anterior; no describe el estado posterior de atestación de esas 124 formas.

# Auditoría de alias, siglas y variantes de los 657 conceptos

Cierre: 2026-10-21T01:00:26-04:00, hora de Bolivia. **Solo investigación; ninguna integración en TRAD.**

**Se revisaron los 657 conceptos, las 900 apariciones de alternativas y las 567 formas distintas por concepto e idioma.** Se identificaron 3 colisiones internas, 16 ambigüedades con acepciones externas, 11 equivalencias que deben excluirse como alias estrictos y 47 equivalencias condicionadas. Se proponen 6 ajustes de expansión y 22 de metadatos. El cribado completo de semejanza dentro de cada idioma produjo 60 pares que deben mantenerse separados.

El registro editorial de los 657 conceptos está completo. Esto no convierte las alternativas en 567 sinónimos verificados externamente: 443 tienen una coincidencia literal normalizada de búsqueda y 124 no la tienen en el corpus consultado. Ninguna coincidencia prueba por sí sola el significado ni la lengua del pasaje; puede aparecer en referencias, ejemplos u otro contexto. Las definiciones comprobadas específicamente están separadas en alias_definition_evidence.json. No se aprueba ninguna sustitución automática.

## Alcance y recuento

| Elemento | Cantidad |
|---|---:|
| Conceptos con alternativas / sin alternativas | 356 / 301 |
| Alias EN / variantes ES / objetos de sigla | 306 / 243 / 176 |
| Alias heredados / variantes heredadas / formas agrupadas adicionales | 145 / 20 / 10 |
| Total de apariciones, sin descartar procedencia repetida | 900 |
| Formas únicas por concepto, idioma y grafía | 567 |
| Cadenas canónicas EN y ES incluidas como destinos de colisión | 1.314 |
| Conceptos canónicos bilingües preservados / pendientes | 657 / 0 |

Las 900 apariciones se solapan entre campos. Por ejemplo, una sigla puede figurar como alias, abreviatura y alias heredado. Los recuentos de hallazgos tampoco se suman como errores independientes: una forma puede requerir contexto y además una corrección de metadatos. Las 10 formas agrupadas ya tenían prohibida la conversión automática en alias.

## Colisiones internas comprobadas

| Forma | Conceptos diferentes | Corrección propuesta | Evidencia |
|---|---|---|---|
| PAD | Presión arterial diastólica (ES); peripheral artery disease (EN) | Exigir idioma y definición local; conservar ambos nombres completos | [S29](https://secardiologia.es/images/2023/Gu%C3%ADas/Final_GPC_ESC_2024_PA_elevada_e_hipertensio%CC%81n.pdf), PDF 8; [AS02](https://www.acc.org/about-acc/press-releases/2024/05/21/16/00/early-diagnosis-treatment-of-peripheral-artery-disease-essential-to-improve-outcomes-reduce-amputation-risk) |
| ECA | Ensayo controlado aleatorizado; enzima convertidora de angiotensina (ambos ES) | El idioma no resuelve la colisión; conservar la expansión definida en el pasaje | [S89](https://semap.org/wp-content/uploads/simple-file-list/Guia_2018_ESC_ESH_HTA.pdf), bloque 8; [S29](https://secardiologia.es/images/2023/Gu%C3%ADas/Final_GPC_ESC_2024_PA_elevada_e_hipertensio%CC%81n.pdf), PDF 8 |
| MRA | Mineralocorticoid receptor antagonist; magnetic resonance angiography (ambos EN) | Distinguir fármaco/clase de técnica de imagen; conservar singular/plural en la frase | [S71](https://repisalud.isciii.es/bitstreams/4fe1933e-3844-454d-9cef-4a64b5debafe/download), PDF 6; [AS01](https://www.heart.org/en/health-topics/peripheral-artery-disease/diagnosing-pad) |

Son colisiones en el inventario de investigación ampliado, no tres fallos nuevos demostrados en el glosario operacional. El recuento histórico de una colisión en el lote inicial tenía otro alcance y queda conservado como antecedente. No se ejecutó el normalizador ni se midieron sustituciones en audio.

## Ambigüedades con acepciones externas

Estas 16 advertencias no añaden conceptos ni colisiones exactas al inventario. La acepción competidora puede no estar incluida como alias en él. Las fuentes y localizadores verificables están en el registro de definiciones.

| Forma | Acepción del inventario | Acepción competidora | Decisión y fuentes |
|---|---|---|---|
| PA | primary aldosteronism (en) | presión arterial (es) | Mantener idioma y definición local; el idioma solo no basta para toda acepción. [S10](https://www.endocrine.org/clinical-practice-guidelines/primary-aldosteronism-2), [S29](https://secardiologia.es/images/2023/Gu%C3%ADas/Final_GPC_ESC_2024_PA_elevada_e_hipertensio%CC%81n.pdf) |
| HRV | heart rate variability (en) | hipertensión renovascular (es) | Exigir expansión local y especialidad; no transportar la sigla entre idiomas. [AS18](https://pubmed.ncbi.nlm.nih.gov/29034226/), [S29](https://secardiologia.es/images/2023/Gu%C3%ADas/Final_GPC_ESC_2024_PA_elevada_e_hipertensio%CC%81n.pdf) |
| RAR | reducción absoluta del riesgo (es) | ratio aldosterona-renina (es) | Exigir medida y unidades; no decidir solo por idioma. S93 usa RRA, que no justifica atestar RAR. [AS16](https://www.cochrane.org/es/evidence/CD003610_benefits-and-harms-antibiotics-secondary-prevention-coronary-heart-disease), [S29](https://secardiologia.es/images/2023/Gu%C3%ADas/Final_GPC_ESC_2024_PA_elevada_e_hipertensio%CC%81n.pdf) |
| ARR | aldosterone-to-renin ratio (en) | absolute risk reduction (en) | Distinguir endocrinología y medida de efecto; conservar sigla si no se define. [S71](https://repisalud.isciii.es/bitstreams/4fe1933e-3844-454d-9cef-4a64b5debafe/download), [AS11](https://pubmed.ncbi.nlm.nih.gov/24686884/) |
| PRA | plasma renin activity | panel reactive antibody | Distinguir endocrinología y evaluación inmunológica del trasplante. [S10](https://www.endocrine.org/clinical-practice-guidelines/primary-aldosteronism-2), [AS06](https://pubmed.ncbi.nlm.nih.gov/8000853/) |
| PAC | plasma aldosterone concentration | premature atrial contraction | Distinguir analito y evento electrocardiográfico. [AS17](https://pubmed.ncbi.nlm.nih.gov/42162197/), [AS05](https://newsroom.heart.org/news/air-pollution-may-spur-irregular-heart-rhythms-in-healthy-teens) |
| ACS | autonomous cortisol secretion | acute coronary syndrome | Distinguir endocrinología y síndrome coronario; no resolver mediante frecuencia de uso. [S10](https://www.endocrine.org/clinical-practice-guidelines/primary-aldosteronism-2), [AS07](https://www.heart.org/en/health-topics/heart-attack/about-heart-attacks/acute-coronary-syndrome) |
| FMD | fibromuscular dysplasia | flow-mediated dilation | Distinguir enfermedad vascular y medición funcional endotelial. [AS19](https://pubmed.ncbi.nlm.nih.gov/30648921/), [AS08](https://pubmed.ncbi.nlm.nih.gov/20952670/) |
| IAH | índice de apnea-hipopnea (es) | intra-abdominal hypertension (en) | Exigir idioma, expansión y magnitud; no colapsar índice y enfermedad. [S29](https://secardiologia.es/images/2023/Gu%C3%ADas/Final_GPC_ESC_2024_PA_elevada_e_hipertensio%CC%81n.pdf), [AS09](https://pubmed.ncbi.nlm.nih.gov/18446319/) |
| PEG | pequeño para la edad gestacional (es) | percutaneous endoscopic gastrostomy (en) | Distinguir clasificación de tamaño y procedimiento digestivo. [S98](https://secardiologia.es/images/2024/Gu%C3%ADas/Gui%CC%81a-ESC-2025-manejo-ECV-y-embarazo.pdf), [AS10](https://pubmed.ncbi.nlm.nih.gov/8977937/) |
| CI | confidence interval | cardiac index | Distinguir intervalo estadístico y medida hemodinámica; conservar unidades. [S71](https://repisalud.isciii.es/bitstreams/4fe1933e-3844-454d-9cef-4a64b5debafe/download), [AS12](https://pubmed.ncbi.nlm.nih.gov/30540751/) |
| RR | relative risk | respiratory rate | Distinguir medida de efecto y signo vital; no expandir por proximidad de números. [AS20](https://pubmed.ncbi.nlm.nih.gov/38620441/), [AS13](https://pubmed.ncbi.nlm.nih.gov/31251168/) |
| IC | intervalo de confianza | insuficiencia cardíaca | La misma lengua y especialidad pueden contener ambas acepciones; exigir definición local. [S64](https://pmc.ncbi.nlm.nih.gov/articles/PMC12057702/), [S98](https://secardiologia.es/images/2024/Gu%C3%ADas/Gui%CC%81a-ESC-2025-manejo-ECV-y-embarazo.pdf) |
| HR | heart rate | hazard ratio | Distinguir frecuencia cardíaca de razón de riesgos instantáneos; no decidir por números aislados. [S41](https://pubmed.ncbi.nlm.nih.gov/25987662/), [S05](https://kdigo.org/wp-content/uploads/2026/04/KDIGO-2024-CKD-Guideline.pdf) |
| MR | mineralocorticoid receptor | magnetic resonance | Distinguir receptor y técnica de imagen; no completar MR angiography como receptor. [S17](https://pubmed.ncbi.nlm.nih.gov/29565029/), [S188](https://pmc.ncbi.nlm.nih.gov/articles/8034801/) |
| RAS | renin-angiotensin system | renal artery stenosis | Distinguir sistema hormonal y lesión de arteria renal; ambas acepciones existen en hipertensión. [S71](https://repisalud.isciii.es/bitstreams/4fe1933e-3844-454d-9cef-4a64b5debafe/download), [AS15](https://pubmed.ncbi.nlm.nih.gov/21722784/) |

Se comprobó RAR con [AS16](https://www.cochrane.org/es/evidence/CD003610_benefits-and-harms-antibiotics-secondary-prevention-coronary-heart-disease): la fuente andina S93 emplea **RRA**, por lo que esa fuente no se presenta como atestación de la grafía RAR. La guía española usa RAR para aldosterona/renina. Las advertencias históricas adicionales (p. ej., NO, MAP y significados secundarios no comprobados de MRAs/APA/AF) se conservan separadas; no se promocionan a acepciones verificadas en esta sesión.

## Equivalencias que deben retirarse de los alias estrictos

Se documentan las 11 relaciones rechazadas. Se conserva cada cadena original para trazabilidad; su retirada se propone únicamente en la capa de investigación. El fundamento aquí es la diferencia de entidad, alcance o categoría gramatical, no una prueba de rendimiento del sistema.

| Concepto | Forma | Corrección propuesta |
|---|---|---|
| hypertension | hipertenso (es) | Es adjetivo o persona; conservar hipertenso/hipertensa según la frase, sin convertirlo en el nombre de la enfermedad. |
| hypertension | hypertensive (en) | Adjetivo o sustantivo de persona; no sustituir por hypertension. Mantener separado en una propuesta gramatical. |
| normotension | normotenso (es) | Persona o adjetivo frente a estado fisiológico; no sustituir por normotensión. |
| normotension | normotensive (en) | Adjetivo/persona frente a nombre de estado; conservar categoría gramatical. |
| JNC 8 report | Eighth Joint National Committee (en) | Comité y documento no son la misma entidad. Usar JNC 8 report para el informe; retener el comité solo como entidad relacionada. |
| co-chair | coordinador conjunto (es) | La coordinación conjunta no garantiza el cargo de copresidente. Mantener copresidente; no promover el cargo alternativo a alias. |
| diuretics | diuretic therapy (en) | Clase de fármacos frente a tratamiento. Conservar diuretic therapy como expresión relacionada: tratamiento con diuréticos. |
| frailty | frail patients (en) | Condición frente a grupo de personas. Conservar frail patients como pacientes con fragilidad, sin colapsarlo con frailty. |
| pressure natriuresis | relación presión-natriuresis (es) | El fenómeno y su relación o curva de respuesta no son cadenas intercambiables. Mantener la relación como expresión relacionada. |
| sympathetic activation | hiperactividad simpática (es) | La activación no implica necesariamente hiperactividad. Conservar activación simpática; hiperactividad queda relacionada con un grado de actividad aumentado. |
| pill burden | carga de medicación (es) | Carga de medicación es más amplia que número de comprimidos. Proponer número de comprimidos/pastillas como aclaración contextual; no sustituir por dosis total. |

## Expansiones y metadatos

| Sigla | Expansión anterior | Propuesta de investigación |
|---|---|---|
| AMPA | monitorización domiciliaria de la presión arterial | automedida de la presión arterial |
| SAOS | apnea obstructiva del sueño | síndrome de apnea obstructiva del sueño |
| MRA | mineralocorticoid receptor antagonists | mineralocorticoid receptor antagonist |
| ARB | angiotensin II receptor blockers | angiotensin II receptor blocker |
| CCB | calcium channel blockers | calcium channel blocker |
| NSAID | nonsteroidal anti-inflammatory drugs | nonsteroidal anti-inflammatory drug |

AMPA y SAOS se cotejaron con el glosario de [S29](https://secardiologia.es/images/2023/Gu%C3%ADas/Final_GPC_ESC_2024_PA_elevada_e_hipertensio%CC%81n.pdf), PDF 8. Las otras cuatro propuestas preservan el número gramatical; las guías también pueden usar la sigla sin s para designar una clase en plural. Por eso no se impone una expansión singular en toda oración. Las formas plurales MRAs, ARBs, CCBs y NSAIDs se conservan separadas.

En 22 objetos de abreviatura se propone limpiar other_meanings: retirar la propia expansión del campo de significados alternativos y separar las notas vagas o los plurales deducidos sin evidencia específica. Retener una advertencia histórica no certifica todas sus acepciones. El detalle anterior/propuesto y el motivo de cada retirada están en alias_corrections_proposed.json.

## Equivalencias que solo deben conservarse con condiciones

| Concepto | Forma | Condición de uso |
|---|---|---|
| systolic blood pressure | presión sistólica (es) | Exige contexto de presión arterial; no completar automáticamente si se trata de una cavidad o circuito pulmonar. |
| systolic blood pressure | systolic pressure (en) | Exige contexto de presión arterial; no añadir el territorio arterial sistémico a una medida de otra localización. |
| diastolic blood pressure | presión diastólica (es) | Exige contexto arterial; puede describir otra presión diastólica si se elimina la localización. |
| diastolic blood pressure | diastolic pressure (en) | Conservar el territorio de medición; arterial no se debe inferir de diastolic aislado. |
| blood pressure classification | blood pressure categories (en) | Categorías y sistema de clasificación se relacionan, pero no designan el mismo objeto en toda frase; preservar estructura de clasificación. |
| home blood pressure monitoring | automedición domiciliaria de la presión arterial (es) | Forma clínica de AMPA; verificar quién mide y el ámbito domiciliario. No equiparar todo seguimiento remoto o medición por un profesional con automedición. |
| cardiovascular risk | riesgo de enfermedad cardiovascular (es) | Exige el mismo desenlace y horizonte temporal; no completar ASCVD, diez años ni una ecuación concreta. |
| cardiovascular risk | cardiovascular disease risk (en) | Conservar desenlace y horizonte; el riesgo cardiovascular genérico no identifica por sí solo una calculadora. |
| renin suppression | suppressed renin (en) | Proceso de supresión frente a hallazgo de renina suprimida; conservar tiempo, mecanismo y construcción de la oración. |
| renin suppression | renina suprimida (es) | Hallazgo frente a proceso; no inferir prueba de supresión ni diagnóstico de aldosteronismo. |
| extracellular fluid volume | extracellular volume (en) | Expresión abreviada válida cuando el compartimento es líquido; no extender a todo volumen extracelular de una técnica de imagen. |
| extracellular fluid volume | volumen extracelular (es) | Requiere contexto de líquido extracelular; mantener el compartimento y la técnica de medición. |
| antihypertensive medication | blood pressure medication (en) | Expresión de divulgación; confirmar que reduce la PA. No inferir fármaco ni indicación a partir de una referencia genérica a presión arterial. |
| medication adherence | treatment adherence (en) | Adherencia al tratamiento puede incluir dieta, ejercicio u otras intervenciones. Conservar el calificador farmacológico cuando es el objeto. |
| medication titration | dose titration (en) | Ajuste de dosis de una medicación en este contexto; no presupone aumento, fármaco concreto o pauta. |
| thiazide diuretics | thiazide-type diuretics (en) | La extensión varía por autor: KDIGO 2012 lo usa como grupo amplio que incluye thiazide-like. No mapear universalmente a tiazidas estructurales; conservar el término del documento y sus ejemplos. |
| cardiac arrhythmia | arrhythmia (en) | La abreviación lexical requiere contexto cardíaco; no ampliar a un diagnóstico o subtipo específico. |
| obstructive sleep apnea | síndrome de apnea obstructiva del sueño (es) | Mantener la palabra síndrome cuando aparece; no convertir un evento de apnea aislado en síndrome ni perder el carácter obstructivo. |
| lifestyle modification | manejo del estilo de vida (es) | Manejo incluye evaluación y seguimiento; modificación designa cambio. Conservar como expresión relacionada bajo contexto, no sustitución literal. |
| lifestyle modification | lifestyle management (en) | Manejo y modificación tienen alcance distinto; no convertir seguimiento o consejo en modificación ya realizada. |
| healthy diet | healthy dietary pattern (en) | Patrón y dieta son formulaciones relacionadas en recomendaciones; no convertirlo en un régimen específico como DASH. |
| dietary sodium restriction | sodium restriction (en) | Exige contexto de ingesta dietética; no reemplazar una restricción en otro medio o procedimiento. |
| potassium-enriched salt substitute | potassium-supplemented salt (en) | Confirmar que se usa como sustituto de sal y conserva la composición del producto; no inferir porcentaje o dosis de potasio. |
| sugar-sweetened beverages | sugary drinks (en) | Forma coloquial; verificar presencia de azúcar añadido en la definición del estudio. No incluir automáticamente bebidas sin azúcar añadido. |
| aerobic exercise | aerobic training (en) | Entrenamiento es un programa; ejercicio puede ser una actividad aislada. Conservar duración y modalidad. |
| dynamic resistance exercise | dynamic resistance training (en) | Programa de entrenamiento frente a ejercicio; conservar dinámico y de fuerza, sin inferir resistencia aeróbica. |
| dynamic resistance exercise | ejercicio dinámico de resistencia (es) | Resistencia se usa aquí como fuerza contra carga; no confundir con resistencia cardiorrespiratoria. |
| isometric resistance exercise | isometric resistance training (en) | Conservar isométrico y la diferencia entre ejercicio y programa de entrenamiento. |
| isometric resistance exercise | ejercicio de resistencia isométrica (es) | Conservar contracción isométrica de fuerza; no convertir en ejercicio dinámico o aeróbico. |
| plasma concentration | niveles plasmáticos (es) | Confirmar analito, muestra y magnitud; niveles no implica actividad ni unidades concretas. |
| plasma concentration | plasma levels (en) | Niveles es una expresión informal de concentración solo si el analito y la muestra son explícitos; no inferir actividad de renina. |
| oscillometric blood pressure monitor | oscillometric device (en) | Dispositivo oscilométrico es más amplio fuera del contexto de PA; conservar el tipo de medida. |
| inter-arm blood pressure difference | inter-arm difference (en) | Expresión elíptica: exigir que la diferencia sea de PA, no de circunferencia u otra medida. |
| clinical guidelines implementation | guideline implementation (en) | Exige guías de práctica clínica, sin inferir una guía o versión concreta. |
| systemic vascular resistance | resistencia vascular periférica (es) | Validar circulación sistémica y magnitud; periférica no autoriza inferir territorio pulmonar. |
| systemic vascular resistance | peripheral vascular resistance (en) | Uso fisiológico contextual; preservar circulación sistémica. No confundir resistencia vascular pulmonar ni expandir PVR sin definición. |
| daytime blood pressure | awake blood pressure (en) | Periodo del reloj y vigilia no son idénticos. Usar diario de sueño y definición del protocolo; no intercambiar automáticamente en trabajadores por turnos. |
| nighttime blood pressure | asleep blood pressure (en) | Noche y sueño pueden diferir. Usar diario/protocolo y conservar el periodo informado. |
| night-to-day blood pressure ratio | relación noche-día (es) | Exigir PA y sentido noche/día; no invertir numerador y denominador ni inferir porcentaje de descenso. |
| adrenal venous sampling | cateterismo de venas suprarrenales (es) | El cateterismo es el acceso; confirmar muestreo de sangre suprarrenal. No equiparar una intervención venosa sin toma de muestras con AVS. |
| dual combination therapy | biterapia antihipertensiva (es) | Exige contexto antihipertensivo y dos componentes; no asumir un único comprimido. |
| triple combination therapy | triterapia antihipertensiva (es) | Exige contexto antihipertensivo y tres componentes; no asumir dosis fija o un único comprimido. |
| therapeutic inertia | clinical inertia (en) | La literatura usa ambos términos de forma intercambiable en falta de inicio/intensificación indicada. Retener en ese contexto; no atribuir inercia a toda ausencia de cambio terapéutico. |
| multidisciplinary team-based care | atención multidisciplinaria (es) | Varios profesionales no prueban trabajo coordinado en equipo. Mantener el atributo de equipo cuando es parte del modelo. |
| left atrial enlargement | dilatación de la aurícula izquierda (es) | Confirmar medida de tamaño/volumen auricular y criterio de la técnica; no inferir hipertrofia, fibrilación o umbral. |
| double-blind trial | double-masked trial (en) | Variantes de enmascaramiento: conservar a quién se ocultó la asignación; doble no identifica por sí solo los dos grupos. |
| 2025 AHA/ACC guideline | 2025 ACC/AHA guideline (en) | El orden de las sociedades puede variar; mantener año y tema de hipertensión. En 2025 existen otras guías AHA/ACC, incluida ACS. |

El uso amplio de thiazide-type está explícito en [AS04](https://kdigo.org/wp-content/uploads/2016/10/KDIGO-2012-Blood-Pressure-Guideline-English.pdf), PDF 25; se contrasta con la distinción thiazide/thiazide-like de [S71](https://repisalud.isciii.es/bitstreams/4fe1933e-3844-454d-9cef-4a64b5debafe/download), PDF 47–48. Se usa la fuente de 2012 para documentar variación terminológica histórica. No se adopta ninguna recomendación terapéutica antigua.

Para vigilia/sueño, [S76](https://pmc.ncbi.nlm.nih.gov/articles/PMC11409525/), bloque 12, distingue los periodos y pide un diario; [S71](https://repisalud.isciii.es/bitstreams/4fe1933e-3844-454d-9cef-4a64b5debafe/download), PDF 22, también requiere registrar el sueño. El uso contextual de clinical inertia se encuentra en [AS14](https://pubmed.ncbi.nlm.nih.gov/21301689/). Estas referencias apoyan la decisión de conservar contexto, no una sustitución universal.

## Grafías parecidas y calificadores protegidos

Se compararon todas las formas y destinos canónicos de un mismo idioma con longitud normalizada de al menos 8 caracteres, usando SequenceMatcher ≥0,90. El filtro por longitud solo descarta parejas cuyo máximo matemático no alcanza el umbral. Se conservaron dígitos, letras de subtipo y negaciones. Los 60 resultados se revisaron como conceptos distintos; no son puntuaciones del motor operacional ni una prueba de todos los errores posibles de ASR.

| Idioma | Forma A | Forma B | Similitud de caracteres |
|---|---|---|---:|
| es | presión arterial alta | presión arterial baja | 0.905 |
| es | presión sistólica | presión diastólica | 0.914 |
| es | meta de presión arterial | lectura de presión arterial | 0.902 |
| es | hipertensión en etapa 1 | hipertensión en etapa 2 | 0.957 |
| es | receptor AT1 | receptor AT2 | 0.917 |
| es | presión arterial en bipedestación | presión arterial en sedestación | 0.938 |
| es | biterapia antihipertensiva | triterapia antihipertensiva | 0.943 |
| es | calcioantagonistas dihidropiridínicos | calcioantagonistas no dihidropiridínicos | 0.961 |
| es | presión arterial elevada | presión arterial no elevada | 0.941 |
| es | presión arterial sistólica | presión arterial diastólica | 0.943 |
| es | hipertensión no controlada | hipertensión controlada | 0.939 |
| es | hipertensión en estadio 1 | hipertensión en estadio 2 | 0.960 |
| es | hipertensión sistólica aislada | hipertensión diastólica aislada | 0.951 |
| es | emergencia hipertensiva | urgencia hipertensiva | 0.909 |
| es | prevención primordial | prevención primaria | 0.900 |
| es | ensayo SPRINT | ensayo ESPRIT | 0.923 |
| es | angiotensina II | angiotensina I | 0.966 |
| es | enzima convertidora de angiotensina | enzima convertidora de angiotensina 2 | 0.972 |
| es | tasa de filtración glomerular estimada | tasa de filtración glomerular medida | 0.919 |
| es | tratamiento farmacológico | tratamiento no farmacológico | 0.943 |
| es | insuficiencia cardíaca con fracción de eyección reducida | insuficiencia cardíaca con fracción de eyección preservada | 0.912 |
| es | actividad física | inactividad física | 0.941 |
| es | receptor de angiotensina II tipo 1 | receptor de angiotensina II tipo 2 | 0.971 |
| es | inflado del manguito | desinflado del manguito | 0.930 |
| es | presión arterial automatizada en consultorio sin observador | presión arterial automatizada en consultorio con observador | 0.966 |
| es | disfunción diastólica | disfunción sistólica | 0.927 |
| es | factores de riesgo modificables | factores de riesgo no modificables | 0.954 |
| es | ensayo SPYRAL HTN-OFF MED | ensayo SPYRAL HTN-ON MED | 0.939 |
| es | bloqueadores de los canales de calcio dihidropiridínicos | bloqueadores de los canales de calcio no dihidropiridínicos | 0.974 |
| en | stage one hypertension | stage two hypertension | 0.909 |
| en | stage one hypertension | stage 2 hypertension | 0.905 |
| en | stage two hypertension | stage 1 hypertension | 0.905 |
| en | angiotensin 2 | angiotensin I | 0.923 |
| en | pharmacologic therapy | nonpharmacologic therapy | 0.933 |
| en | pharmacologic therapy | non-pharmacologic therapy | 0.913 |
| en | AT1 receptor | AT2 receptor | 0.917 |
| en | unattended AOBP | attended AOBP | 0.929 |
| en | medication non-adherence | medication adherence | 0.909 |
| en | non-modifiable risk factors | modifiable risk factors | 0.920 |
| en | 2025 ACC/AHA guideline | 2017 ACC/AHA guideline | 0.909 |
| en | dihydropyridine CCBs | non-dihydropyridine CCBs | 0.909 |
| en | elevated blood pressure | non-elevated blood pressure | 0.920 |
| en | elevated blood pressure | seated blood pressure | 0.909 |
| en | uncontrolled hypertension | controlled hypertension | 0.958 |
| en | stage 1 hypertension | stage 2 hypertension | 0.950 |
| en | isolated systolic hypertension | isolated diastolic hypertension | 0.918 |
| en | hypertensive emergency | hypertensive urgency | 0.905 |
| en | SPRINT trial | ESPRIT trial | 0.917 |
| en | angiotensin II | angiotensin I | 0.963 |
| en | angiotensin-converting enzyme | angiotensin-converting enzyme 2 | 0.967 |
| en | antihypertensive therapy | antihypertensive drug therapy | 0.906 |
| en | pharmacological therapy | non-pharmacological therapy | 0.920 |
| en | medication adherence | medication nonadherence | 0.930 |
| en | heart failure with reduced ejection fraction | heart failure with preserved ejection fraction | 0.911 |
| en | physical activity | physical inactivity | 0.944 |
| en | angiotensin II type 1 receptor | angiotensin II type 2 receptor | 0.967 |
| en | unattended automated office blood pressure | attended automated office blood pressure | 0.976 |
| en | modifiable risk factors | nonmodifiable risk factors | 0.939 |
| en | SPYRAL HTN-OFF MED trial | SPYRAL HTN-ON MED trial | 0.936 |
| en | dihydropyridine calcium channel blockers | non-dihydropyridine calcium channel blockers | 0.952 |

Además se registran 51 barreras de distinción clínica, incluidas relaciones de subtipo o solapamiento que no constituyen sinonimia. Se mantienen, entre otras, hipopotasemia/hiperpotasemia, hipoxemia/hipoxia, TFG medida/estimada, actividad/concentración de renina, primera orina matutina/muestra aislada, FGR/SGA, emergencia/urgencia y HR/RR/OR. Las unidades conservan prefijo y denominador; no se convierten mg, µg, ng, mmol ni cantidades por día en cantidades por decilitro.

Se protegen 47 etiquetas de referencia completas. CARDIA (cohorte) y CARDia (ensayo de revascularización) son referencias distintas: [S156](https://newsroom.heart.org/news/ver-la-television-por-un-tiempo-moderado-o-considerable-en-la-mediana-edad-se-vincula-con-un-posterior-deterioro-cognitivo-y-de-la-salud-cerebral), [AS03](https://pubmed.ncbi.nlm.nih.gov/15660030/). STEP y STEP-1 también aparecen separados en el glosario de [S71](https://repisalud.isciii.es/bitstreams/4fe1933e-3844-454d-9cef-4a64b5debafe/download), PDF 6. Se mantienen los sufijos OFF/ON MED, TRIO, BPLA y los años de las guías. No se deduce una rama concreta de ACCORD o ASCOT a partir del nombre abreviado.

## Archivos y límites

- [Decisiones completas de 567 formas y cobertura de 657 conceptos](alias_review_decisions.json).
- [Correcciones propuestas, sin aplicación operacional](alias_corrections_proposed.json).
- [Inventario de 900 apariciones con rutas de procedencia](alias_inventory.json).
- [Definiciones específicamente comprobadas](alias_definition_evidence.json) y [20 referencias complementarias con nivel de acceso](alias_source_catalog.json).
- [Descubrimiento literal y similitud, separado de las decisiones](alias_evidence_discovery.json).
- [Validación de integridad de esta auditoría](alias_audit_validation.json), [progreso](hypertension_research_progress.json) y [paquete completo](hypertension_research_deliverables.zip).

La revisión es editorial del asistente. No hubo certificación clínica independiente, evaluación de audio, ensayo de traducción en vivo ni autorización de corrección automática. Las 124 formas sin coincidencia literal siguen identificadas como no atestadas individualmente en el corpus; antes de aprobarlas como alias estrictos requieren fuente específica. La revisión de seguridad está cerrada porque para todas las formas hay una decisión, incluso si consiste en conservar contexto o retener la aprobación.

El glosario original, el candidato operacional, el dataset canónico de investigación y los 657 registros de verificación se preservan byte por byte. Las correcciones viven en archivos nuevos de investigación. El estado previo íntegro está en checkpoints/session3_657_verified/. No hubo integración, cambio de configuración, commit ni automatización.
