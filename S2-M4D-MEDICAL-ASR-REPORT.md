# TRAD — Sprint 2 / M4-D: fidelidad médica y selección incremental EN

20 de octubre de 2026, America/La_Paz. Ronda focalizada, inferior al límite de
dos horas. Prioridad: transmitir fielmente el inglés pronunciado.

**Dictamen: GO CON RESERVAS para investigación adicional muy específica.
NO-GO para integración con los resultados actuales. No hay ganador clínico.**
Conservar **large-v3-turbo adaptativo / LA2 / espera mínima 1 s / VAD instalado**
como base técnica del siguiente experimento acotado. Medium y Turbo conservan
tres de las cuatro expresiones adjudicadas, pero ambos confirman **`140 over 19`
frente a `140 over 90`**. Ese fallo basta para impedir la aprobación, aunque
Turbo reduzca el WER estable de 4,12 % a 2,59 %.

La elección técnica de Turbo considera también que conserva el fármaco y la
autocorrección de estadio que Medium pierde en estos replays; no se elige solo
por WER ni por tamaño. Turbo mantiene otras regresiones relevantes pendientes
de escucha. **TRAD para el congreso no recibe una nueva aprobación**: no hubo
integración, micrófono, servicios, traducción ni validación EN→ES/OBS.

## 1. Alcance, protección y evidencia

Se leyeron M4-C, M4-B §16–17, M4, TRAD-LAB, README M4-C y el informe bidireccional.
Se verificaron rutas, originales, cachés, estado Git y ausencia de listeners en
8000/8010/18000/18010. Los monitores exigieron esos puertos cerrados durante las
inferencias. DWM, Killer y OBS/browser de OBS permanecieron sin modificaciones.

Run privado: `C:/live-captions/logs/trad_lab/m4d_20261020T192300Z`.
El inicio real y el cierre constan en `audit.json` y `delivery.json`; el nombre
del directorio no sustituye esos relojes.

[Auditoría](C:/live-captions/logs/trad_lab/m4d_20261020T192300Z/audit.json):
192 fuentes previas y 2154 archivos de evidencia. Respaldo previo
`pre_m4d_sources.zip`, SHA-256
`36959dad16472e519be9f77b2cb138917a5a1adba548ac27556126d9b101be7b`.
Excluye `.env`, runtime, perfiles, entornos y pesos; `.env` solo se verifica
por hash. Se conservaron los 18 cambios versionados preexistentes.

[Preservación PASS](C:/live-captions/logs/trad_lab/m4d_20261020T192300Z/preservation_check.json):
fuentes y evidencias anteriores, `.env`, los 13 archivos CT2 cacheados y el
decoder PyTorch small no usado mantienen sus hashes. HEAD/main continúan en
`64f8221`; checkpoint `codex/s2-m4-checkpoint` en `cd008ad`.
No hubo staging, commits, tags, merges, resets, push o despliegues.

Solo se añade [el paquete M4-D](C:/live-captions/trad_lab/m4d/README.md), este
informe y evidencia privada. El motor M4-C, `app/`, SegmentManager, remuestreador,
glosarios, dependencias y colector M4-B no cambiaron. **Intento físico 04 intacto.**

## 2. Adjudicación y límites de los cuatro recortes

Se verificaron los once WAV de revisión M4-C contra su SHA y contra los bytes
exactos del intervalo de su fuente. Los cuatro solicitados corresponden a los
archivos indicados. Sin ganancia, filtros, remuestreo nuevo ni ajuste de límites
para favorecer resultados.

La autoridad de las cuatro expresiones es **la adjudicación provisional por
escucha aportada por el usuario en la solicitud M4-D**. No se efectuó una segunda
escucha independiente mediante estas herramientas. Se valida la identidad PCM;
no se adjudica toda la oración ni se inventan fronteras fonéticas desde el ASR.

| Caso | Fuente | Contenedor acústico en fuente, s | Expresión adjudicada | SHA del WAV, prefijo |
|---|---|---:|---|---|
| ORTHO | cardio_01 | 251,68–256,74 | orthostatic hypotension | `3cc57d6b636cf87d` |
| UNTREATED | cardio_03 | 313,14–319,48 | untreated stage two hypertension | `fc191a6417d94b0b` |
| YEARS | cardio_03 | 790,42–795,52 | every four to six years | `69bdcb56e348c08e` |
| BP140 | cardio_01 | 120,92–126,48 | 140 over 90 | `d895106709e92193` |

[Registro completo](C:/live-captions/logs/trad_lab/m4d_20261020T192300Z/evaluation/adjudication.json)
con SHA-256 íntegros, muestras, fuente y alcance. Los intervalos son los del
recorte verificable, **no alineación clínica exacta por palabra**. Por ello se
evalúa la expresión objetivo, sin WER de la oración parcial ni WER clínico.
Los modelos no establecen ni modifican retroactivamente la referencia.

## 3. Fase A: tres modelos offline y contexto acústico

Small, medium y large-v3-turbo están completos en caché y coinciden por hash con
los snapshots M3. Turbo utiliza `vocabulary.json` y `preprocessor_config.json`;
no se copiaron archivos de small. Los tres cargaron realmente en CUDA float16.

Perfil común: inglés explícito, transcribe, beam 5, best_of 5, temperatura 0,
previous_text ON, word timestamps, VAD OFF, initial_prompt/hotwords **None**,
cuatro hilos CPU y un worker. No referencias, glosario ni respuestas en prompts.
Se conservan transcripciones crudas, palabras, tiempos, opciones y hashes.

**45 inferencias focalizadas:** once recortes existentes y cuatro versiones con
contexto, por tres modelos. Los cuatro casos reciben exactamente **10 s antes
y 10 s después**, desde el mismo PCM original. Sus duraciones aisladas son
5,06/6,34/5,10/5,56 s; con contexto, 25,06/26,34/25,10/25,56 s.
El contexto posterior es diagnóstico offline y no acredita reconocimiento causal.

Matriz de **recortes aislados**; la última columna usa texto confirmado de los
archivos completos. M/T = empate Medium/Turbo en estos cuatro casos:

| Caso | Referencia adjudicada | Small offline | Medium offline | Turbo offline | Mejor incremental |
|---|---|---|---|---|---|
| ORTHO | orthostatic hypotension | orthostatic hypertension | orthostatic hypotension | orthostatic hypotension | M/T: orthostatic hypotension |
| UNTREATED | untreated stage two hypertension | I'm treated stage two hypertension | untreated stage two hypertension | untreated stage 2 hypertension | M/T: untreated stage two hypertension |
| YEARS | every four to six years | every 46 years | every 46 years | every four to six years | M/T: every four to six years |
| BP140 | 140 over 90 | 140 over 19 | 140 over 19 | 140 over 19 | Ninguno: ambos 140 over 19 |

Con contexto, small recupera UNTREATED y medium recupera YEARS. ORTHO sigue mal
en small; BP140 sigue mal en los tres. Coincidencias de expresión: small 0/4→1/4,
medium 2/4→3/4, Turbo 3/4→3/4. Son cuatro casos seleccionados, no tasas generales
de eficacia clínica. `stage 2/two` se reconoce como formato en este canal;
**`46` no equivale a `four to six`, ni `19` a `90`**. El WER primario no cambia.

La dependencia del contexto queda demostrada para algunos pasajes, pero no es
monótona: small conserva el rango en el offline completo M3 y lo pierde en el
recorte ampliado. Los tres offline completos M3 también contienen `140 over 19`.
Esto no identifica una causa exclusiva de acento, modelo o segmentación; tampoco
invalida la adjudicación humana. El caso proviene del original digital, no exige
culpar al Yeti o reparar el colector. Un consenso entre modelos tampoco lo resuelve.

[Matriz y resultados crudos](C:/live-captions/logs/trad_lab/m4d_20261020T192300Z/evaluation/offline_matrix.json).

## 4. Fases B/C: comparación causal y estabilidad

Se reutilizó el baseline M4-C **small adaptativo, LA2, edad mínima 1 s, avance
2 s, objetivo 15 s, límite 30 s, Silero instalado**. Se ejecutaron solamente
dos alternativas completas: medium y Turbo, inicialmente cambiando solo el
snapshot. Ambos terminaron los tres archivos, sin fallos de horizonte ni OOM.
No se repitió la espera de 4 s, dadas sus regresiones previas de tratamiento/rango.

Se conservaron beam, precisión, VAD, límites y política de confirmación. El VAD
usa su ONNX local en CPU y defaults instalados, sin ajustes. La confirmación
determina los recortes del buffer: cambiar el modelo puede cambiar las ventanas
efectivas aun manteniendo la misma política. No es un A/B con todas las ventanas
internas forzadas a ser idénticas.

Cada llamada incremental recibe únicamente PCM ya disponible. La auditoría
independiente contrastó ventanas y hashes float32 contra las fuentes, límites,
EOF y concatenación literal de confirmaciones: **3403 ventanas de diez resultados**,
incluyendo seis nuevos completos y cuatro antecedentes M4-C reutilizados. De esas
ventanas, 2220 corresponden a las seis inferencias completas nuevas. No se confunde
el acceso separado del verificador al archivo con audio futuro entregado al decoder.

El buffer nunca superó 30 s, aproximadamente 1,83 MiB float32 más copias temporales.
Las medianas reales de ventana fueron 21,24 s small, 20,72 s medium y 21,36 s Turbo.
Hubo 319/315/286 actualizaciones con revisión provisional, respectivamente.
Se conservaron 20/15/15 conflictos de frontera y 10/12/9 pares de timestamps
confirmados solapados; estos tiempos estimados no prueban duplicación acústica.

El texto confirmado es append-only, pero puede quedar equivocado:

- **Medium, fármaco:** a disponibilidad 588 s confirmó `with and 25 milligrams a day`.
  A 590 s el RAW ya decía `with spironolactone and 25 milligrams a day`. El nombre
  llegó después de cerrar esa posición del texto estable y no pudo insertarse.
  El nombre faltaba en las hipótesis previas; no fue una pérdida de transporte.
- **Turbo, cardio_02:** confirmó `Significance` a 824 s. A 830 s la hipótesis decía
  `A significant reduction…`, sin el sustantivo anterior; la salida estable
  conserva `Significance, significant…`. La identidad acústica de esa repetición
  requiere escucha, pero la revisión tardía está registrada.
- **BP140:** el error persiste hasta en seis hipótesis consecutivas de Turbo
  después de estar disponible el recorte. Son ventanas solapadas, no seis
  observaciones independientes. El acuerdo repetido no constituye verdad.

[Alertas experimentales](C:/live-captions/logs/trad_lab/m4d_20261020T192300Z/evaluation/late_revision_alerts.json)
y [revisiones sensibles](C:/live-captions/logs/trad_lab/m4d_20261020T192300Z/evaluation/sensitive_alerts.json).
Son análisis posteriores, no un detector clínico integrado ni correcciones.
No se borraron confirmaciones, rellenaron medicamentos o ajustaron cifras.
No se añadieron combinaciones de prompts, beam o umbrales: el contexto, las trazas
y los fallos críticos disponibles bastan para la decisión de esta ronda.

## 5. Precisión y comprobación sobre archivos completos

Tres archivos, 2217,82275 s y 4204 palabras de referencia. TXT originales intactos,
revisados previamente por el usuario pero provisionales. **WER/CER léxicos
exploratorios, no validación clínica.** Las agregaciones suman errores/denominadores.

| Incremental, solo texto confirmado | cardio_01 WER | cardio_02 WER | cardio_03 WER | Errores / 4204 | WER total | CER total |
|---|---:|---:|---:|---:|---:|---:|
| Small, baseline M4-C | 2,80 % | 2,81 % | 6,03 % | 173 | 4,12 % | 1,84 % |
| Medium | 2,66 % | 2,30 % | 4,21 % | 132 | 3,14 % | 1,66 % |
| Turbo | 2,66 % | 1,57 % | 3,63 % | 109 | 2,59 % | 1,30 % |

| Resultado al añadir cola EOF **no confirmada** | WER | CER |
|---|---:|---:|
| Small | 4,04 % | 1,73 % |
| Medium | 3,04 % | 1,53 % |
| Turbo | 2,50 % | 1,17 % |

Los tres dejan vacía la cola de cardio_01. En cardio_02, small deja
`associated with stepwise`; medium/Turbo, `are associated with stepwise`.
En cardio_03 queda `is` o `is…`. **Ninguna palabra de esas colas se cuenta como
confirmada.** No se añade silencio futuro ni otro voto artificial al EOF.

Antecedentes offline completos M3, mismos pesos y perfil explícito verificados:
small WER/CER 3,52/1,43 %, medium 2,78/0,90 %, Turbo 3,14/1,93 %.
Se reutilizaron esas inferencias y sus hashes; no son mediciones nuevas de tiempo.
Su VAD OFF y segmentación difieren del incremental: la diferencia de WER no se
atribuye exclusivamente a causalidad ni al tamaño del modelo.

**Procedencia y separación:** cardio_02 termina con `associated with step-wise` y
cardio_03 comienza `increase in coronary artery calcium scores`. La continuidad
de contenido y metadatos compatibles apoyan que sean partes del mismo webinar;
sin URL/identificador original no puede certificarse. Se agrupan conservadoramente
como una fuente, junto a otra para cardio_01: no se presentan tres discursos
independientes ni el Yeti como otro conferencista.

Cardio_02 no intervino en la fase focal M4-D, pero ya se había explorado en M3/M4-C.
Una proyección secundaria excluye 60 tokens a cada lado de los cuatro casos:
3710 palabras, WER estable 3,96/2,83/2,37 % para small/medium/Turbo. **No es un
holdout intacto**: también contiene otros recortes diagnósticos vistos. No se
redefinió para ocultar errores. La comprobación es interna; falta generalización
a voces/conferencias nuevas. Ver
[procedencia](C:/live-captions/logs/trad_lab/m4d_20261020T192300Z/evaluation/source_provenance.json)
y [límites de la partición](C:/live-captions/logs/trad_lab/m4d_20261020T192300Z/evaluation/partition_caveats.json).

Resultados por archivo, CER, colas, causalidad y fuentes:
[comparación reproducible](C:/live-captions/logs/trad_lab/m4d_20261020T192300Z/evaluation/incremental_comparison.json).

## 6. Errores y conflictos médicos nuevos o persistentes

Solo los cuatro casos de §2 tienen adjudicación humana específica aportada para
esta ronda. Los demás contrastes se conservan para escucha; ni el TXT ni otro ASR
se convierten en verdad clínica.

| Pasaje | Hallazgo | Consecuencia para la decisión |
|---|---|---|
| ORTHO | Small confirma hypertension; medium/Turbo hypotension | Mejora demostrada respecto a la expresión adjudicada |
| UNTREATED / YEARS | Ambos alternativos conservan tratamiento y rango en los completos | Sin repetir allí las regresiones de espera 4 s |
| BP140 | Todos producen 19; la referencia adjudicada es 90 | Fallo crítico persistente; impide integración |
| Fármaco cardio_03 | Small spironolactam; medium omite el nombre; Turbo spironolactone | Turbo conserva el nombre esperado por el TXT; Medium presenta recuperación RAW tardía, sin reparar el estable |
| Aldosterone | Turbo produce dos eldest run; en la segunda mención small/medium conservan aldosterone | Regresión terminológica de Turbo pese a menor WER; primera mención de small ya estaba degradada |
| Riesgo a diez años | Ambos alternativos low tenure; small conserva low 10-year ASCVD risk | Se pierde la duración explícita; nueva discrepancia relevante pendiente de adjudicación |
| Autocorrección de estadio | Medium pierde sorry for stage one; small/Turbo la conservan | Riesgo de omitir una corrección diagnóstica; no se explica por simple formato 1/one |
| Normotensive / aldosteronism | Persisten normal intensive, neuromotensive, normal attention y otras variantes | No se resuelve toda la terminología al cambiar el modelo |
| Unidad | Small decilator; medium/Turbo deciliter en el pasaje completo | Mejora ortográfica; cifra/unidad pronunciadas siguen pendientes de adjudicación independiente |
| 57 / non-elevated / 120 over 70 | Conservados en cardio_01 completo por los tres | Coincidencias con referencia provisional; no certifican todo el audio físico Yeti |
| Systolic / diastolic | No aparecen swaps literales entre ambos en los alineamientos; medium/Turbo no contienen dystolic en cardio_02 | Screening limitado, no garantía de ausencia de errores clínicos |

Medium también produce `140.90` donde el TXT separa `140 90`: se conserva como
representación potencialmente ambigua, no se equipara automáticamente a una
fracción correcta. `177,000`/`177 000`, `1400`/`1,400` y `stage two`/`stage 2`
se distinguen de alterar un valor. `46 years` sí colisiona con el rango adjudicado.
Las alertas genéricas pueden marcar `anti hypertensive` por partición y omitir
otras alteraciones: no se usan sus conteos como errores médicos certificados.

**Ejemplos de menor WER con significado peor:** Turbo baja a 2,59 % pero degrada
la segunda mención de aldosterone y la duración de diez años que small conservaba.
Medium baja a 3,14 % pero omite el medicamento en el estable y una autocorrección
de estadio. No se aceptan esos promedios como criterio clínico suficiente.

Audios nuevos de comprobación, sin ganancia y con manifiesto de muestras/SHA:
[aldosterone](C:/live-captions/logs/trad_lab/m4d_20261020T192300Z/evaluation/checking_review_audio/cardio03_aldosterone_checking.wav),
[diez años](C:/live-captions/logs/trad_lab/m4d_20261020T192300Z/evaluation/checking_review_audio/cardio03_ten_year_checking.wav),
[autocorrección de estadio](C:/live-captions/logs/trad_lab/m4d_20261020T192300Z/evaluation/checking_review_audio/cardio03_stage_correction.wav).
Los límites se localizaron con timestamps anteriores, no se usaron para prompts
ni para retocar configuraciones y **siguen pendientes de escucha humana**.
Para el fármaco se conserva el
[recorte M4-C original](C:/live-captions/logs/trad_lab/m4c_20261020T173100Z/review_audio_delivery/cardio03_drug.wav).

## 7. Latencia simulada, memoria y rendimiento

| Perfil, completos | Registros confirmados | Mediana serial | p95 serial | Máximo serial | RTF inferencia |
|---|---:|---:|---:|---:|---:|
| Small, M4-C | 4174 | 3,644 s | 6,337 s | 24,075 s | 0,263 |
| Medium | 4143 | 4,094 s | 7,431 s | 14,700 s | 0,523 |
| Turbo | 4162 | 3,623 s | 6,439 s | 16,615 s | 0,282 |

Son registros de palabra agrupados, no el denominador léxico de WER. La mediana
y p95 algorítmicas, sin sumar inferencia, son 3,03/6,19 s medium y 3,06/5,90 s Turbo.
Por actualización: medium mediana/p95 1,016/1,384 s, máximo 5,946 s; Turbo
0,494/0,800 s, máximo 2,965 s. La cola serial simulada previa a una llamada llegó
a 3,946 s medium y 0,965 s Turbo, y se drenó; RTF medio <1 no garantiza cada plazo.

Disponibilidad = muestras/16000; cómputo = perf_counter al consumir todo el
generador. El origen de palabra lo estima cada ASR, sin alineación acústica
independiente. La simulación serial usa una inferencia a la vez, sin descartar
actualizaciones. Excluye captura, SO, red, logs, SegmentManager, DOM, DeepL y
pantalla. **No es latencia física ni total EN→ES.** Una pasada por perfil;
baseline medido en M4-C, sin comparación estadística de velocidad entre rondas.

Nuevos replays completos: pico total muestreado medium **2625 MiB**, Turbo
**2657 MiB**; mínimos libres 5324/5292 MiB. Máxima temperatura de la ronda 81 °C.
Muestreo nominal ~1 s del dispositivo entero, con Windows/OBS, no pico exacto del
allocator. Reserva inicial 3500 MiB y parada de laboratorio por reserva agotada;
no son thresholds de ASR. Sin OOM ni fallback de precisión/modelo.

Ambos son viables en memoria y cómputo para **este replay**. El servicio real,
su cola bajo entrada continua y la latencia visible no se implementaron ni validaron.

## 8. Pruebas, integridad y cierre

**130 pruebas CPU PASS, sin skips**, 5,285 s: 121 previas seleccionadas y nueve
M4-D. Cubren cifras distintas, rango frente a 46, untreated/treated, términos
opuestos, alertas de revisión sin corrección, identidad PCM, límites de recortes,
partición no independiente y rechazo de agregación de un corpus parcial.
[Log final](C:/live-captions/logs/trad_lab/m4d_20261020T192300Z/tests_final_130.log).
Compilación, whitespace y comprobación de enlaces completadas. Las suites JS
previas permanecen como antecedentes; no se simula una integración nueva con ellas.

El primer comando global CPU quedó bloqueado en IPC interno de asyncio bajo el
sandbox; se interrumpió solo ese proceso y se conservó su salida. La selección
terminó con permiso de ejecución, sin servidores TCP, audio ni GPU adicional.
Se corrigieron dos supuestos del harness: admitir el vocabulario JSON de Turbo
y exigir todos los archivos para declarar completo un agregado. No afectaron
las inferencias ni el motor de confirmación; los registros intermedios se conservan.

La verificación causal y el EOF pasan, pero **no equivalen a completitud médica**:
hay omisiones y revisiones tardías. El máximo de eliminaciones consecutivas frente
al TXT estable fue 4/5/5 palabras small/medium/Turbo, incluyendo colas EOF; también
se observaron repeticiones como `per per day` ya presentes en el RAW de Turbo.
No se eliminaron para mejorar puntuación ni se certificó su origen acústico.

No se repitió el Yeti completo con otros modelos ni se amplió el barrido: los
cuatro casos y los completos permiten decidir. Sus clips diagnósticos y el
baseline previo se preservan con sus limitaciones M4-B, sin nuevo WER clínico.

[Cierre final](C:/live-captions/logs/trad_lab/m4d_20261020T192300Z/final_closure.json):
procesos propios ausentes, cuatro puertos libres, GPU 286 MiB usados/7663 libres,
56 °C. No se arrancó ni detuvo LIVE u OBS. Artefactos y diff:
[entrega](C:/live-captions/logs/trad_lab/m4d_20261020T192300Z/delivery.json),
[M4D.diff](C:/live-captions/logs/trad_lab/m4d_20261020T192300Z/M4D.diff),
[archivo privado](C:/live-captions/logs/trad_lab/m4d_20261020T192300Z/M4D_EVIDENCE.zip).

## 9. Decisión práctica e integración propuesta, sin implementar

**Ningún candidato supera todos los criterios.** Medium y Turbo mejoran ORTHO
sin invertir los otros dos casos adjudicados en los completos, pero BP140 falla
en ambos. Las regresiones adicionales impiden presentar el promedio como fidelidad
médica aceptable. No se recomienda migrar TRAD para el congreso con esta evidencia.

Conservar Turbo como **control técnico de investigación**, manteniendo exactamente
el perfil evaluado. La comparación con medium aporta motivos de contenido: conserva
el nombre del medicamento y la autocorrección de estadio, además de menor coste.
Sus propios fallos de aldosterone, duración y BP140 siguen abiertos. No hay un
ganador clínico ni una promesa de que un modelo mayor los resuelva.

La única continuación propuesta es adjudicar los tres audios de comprobación y
resolver **BP140 y las revisiones médicas tardías**, con ejemplos de comprobación
independientes de las respuestas usadas para decidir. Una alerta general de revisión
sensible puede investigarse conservando RAW y evidencia; no debe introducir el
valor esperado ni modificar automáticamente diagnóstico, negación, medicamento o
unidad. No se propone otro barrido de decenas de configuraciones.

Plan posterior, condicionado a resolver esos gates y a autorización nueva:

1. Adaptador aislado EN que exponga provisional/confirmado sin cambiar auth,
   dueño, dirección, CLEAR, SegmentManager o texto médico. Replay de archivos
   primero; sin conexión automática a LIVE.
2. Definir el tratamiento de la cola EOF: conservar pendiente/incompleto donde
   corresponda, sin votos ficticios ni convertirla automáticamente en READY.
3. Solo después, prueba supervisada de servicios aislados con DeepL OFF,
   controles normales y verificación de PCM/identidad de dispositivo/cierre.
   Medir latencia visible y revisar cifras/términos con referencia independiente.
4. Rollback por selección explícita del backend original y cierre exclusivo del
   laboratorio tras STOP/EOF. Conservar evidencia; sin reset, restauración masiva,
   cambio de `.env` ni borrado de trabajo posterior. Hoy no hay cambio operativo
   que revertir.

**GO CON RESERVAS para investigación adicional muy específica; integración
NO-GO.** El estado del laboratorio no cambia el estado de TRAD para el congreso.
Se entrega y se detiene para revisión del usuario, sin M5 ni cambios LIVE.
