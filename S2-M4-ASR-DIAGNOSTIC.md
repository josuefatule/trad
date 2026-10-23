# TRAD — Sprint 2 / M4: diagnóstico ASR en tiempo real

20 de octubre de 2026, America/La_Paz. Prioridad EN→ES. Objetivo del usuario: MVP para el 22 de octubre, 07:00. Este informe no aprueba un candidato ni el uso en congreso.

## 1. Dictamen y estado inicial

**Se confirmó un defecto de conteo temporal en el remuestreo por bloques y se localizó una pérdida de inicio en el ensayo sintético M3. No se demostró todavía una mejora integral de precisión médica y latencia visible.** No hay evidencia para aumentar beam, sustituir arquitectura ni cambiar modelo automáticamente.

Se completaron 36 inferencias locales sobre fragmentos: 18 offline beam 1/5, 12 A/B de remuestreo sintético y 6 con LocalAgreement instalado. Las tres repeticiones AlignAtt iniciadas no produjeron un resultado completo: un OOM y dos abortos por reserva de VRAM. Se conservan como bloqueos, no se puntúan contra referencias completas.

Antes de modificar fuentes se leyeron TRAD_LAB_REPORT.md, trad_lab/README.md, BIDIRECTIONAL_MVP_REPORT.md, S2-M1-REPORT.md e INSTALL_WINDOWS.md. No había listeners en 8000/8010/18000/18010 ni procesos operativos Python identificados. RTX 4070 Laptop: 8188 MiB, driver 596.08, 522 MiB usados/7427 libres, 56 °C al auditar. Se verificaron versiones instaladas: WLK 0.2.26, Faster-Whisper 1.2.1, CT2 4.8.2, torch 2.14.0+cu126, PyAV 19.0.1, NumPy 2.5.4, SciPy 1.18.1; no se actualizaron.

Rama de trabajo `sprint2/m1-rtx4070`; HEAD y main siguen en `64f82214b33fad4ee68295df1367249caeae3187`; RC resuelto al mismo commit, objeto anotado `87a25e093c673d9594407188efa00854826eccb6`. Se preservaron los 18 cambios versionados previos y los archivos sin seguimiento del MVP/M1/M3, incluido el glosario del usuario.

## 2. Protección, checkpoint y límites de autorización

Run privado: `C:\live-captions\logs\trad_lab\m4_20261020T084747Z`.

Se verificaron el ZIP original M3 y su ZIP de fuentes, junto con sus manifiestos: ningún archivo previo había cambiado. Se creó un respaldo adicional de **143 archivos**, `pre_m4_backup.zip`, SHA-256 `b8787e83bc04e0158fb29accdfc3fc696d0d9dcd75f7127cd6021ec82e06c86f`. Incluye fuentes, pruebas, documentación y estado/diff; excluye secretos, runtime, entornos, pesos y corpus/resultados privados.

Se preparó [la propuesta y allowlist](C:/live-captions/logs/trad_lab/m4_20261020T084747Z/GIT_CHECKPOINT_PROPOSAL.md) antes de solicitar aprobación. El usuario autorizó únicamente ese checkpoint Git local. Se creó:

- Rama nueva: `codex/s2-m4-checkpoint`.
- Commit: `cd008ad436d8d2c13a739490e899d18e188df9b3`, padre `64f8221`.
- Árbol: `2a658c89ba3f956a7e51b6897809f4b62a94a960`, 143 archivos comprobados contra la allowlist.
- Índice temporal, sin cambiar checkout/index actual/main/tag. Sin push ni despliegue.
- Git carecía de identidad configurada: se utilizó `TRAD-LAB local checkpoint <trad-lab@localhost>` solo en el entorno del proceso; no se cambió git config. El ZIP conserva bytes exactos; el árbol Git respeta los filtros normales de finales de línea.

Las adiciones M4 están en `trad_lab/m4/`, `tests/test_trad_lab_m4.py` y este informe. Ningún fuente preexistente, resultado M3, MP3/TXT original, glosario, `.env`, dependencia o threshold operativo fue sobrescrito. Solo se leyó el glosario como inventario; no se aplicaron correcciones.

Se solicitó autorización separada para hasta tres pruebas Operator/CAPTURE en 18000/18010 con DeepL deshabilitado. **No se recibió esa autorización en M4 y no se iniciaron servicios.** El permiso M3 ya ejecutado no se reutilizó como permiso para nuevos servidores. La latencia visible nueva queda pendiente de ese gate.

## 3. Referencias controladas y PCM

Los originales son MP3. Se derivaron WAV mono s16/16 kHz únicamente para trabajar con muestras PCM reproducibles; convertir a WAV no sustituye ni cambia los MP3. Referencias candidatas: oraciones exactas de los TXT revisados, sin copiarlas de las hipótesis ASR.

| Fragmento | Intervalo en MP3 decodificado | Duración | Palabras normalizadas | Dispersión máxima de bordes entre modelos |
|---|---:|---:|---:|---:|
| cardio_01 | 0.000–87.950 s | 87.950 s | 179 | 0.58 s |
| cardio_02 | 418.840–513.540 s | 94.700 s | 156 | 0.70 s |
| cardio_03 | 235.560–324.120 s | 88.560 s | 147 | 1.37 s |
| Total | | 271.210 s | 482 | |

Se usaron anchors léxicos y tiempos de small/medium/turbo M3 para proponer fronteras de oraciones. Se solicitó validación porque los tiempos no eran inequívocos. El usuario respondió: «Puedes usar los tres porque los revisé pero toma en cuenta que no son wav sino mp3». Se registró esa aceptación, su aclaración sobre los originales MP3 y los hashes de los WAV/TXT derivados.

**La aceptación no equivale a una revisión independiente de cada muestra PCM ni a alineación temporal certificada.** WER/CER aquí son provisionales y conservan esa incertidumbre, sobre todo en los bordes. No se calculó WER de un recorte contra el TXT completo. No se alteraron referencias para favorecer un decoder.

WAV, textos, fronteras, hashes y aceptación: [REFERENCE_REVIEW.md](C:/live-captions/logs/trad_lab/m4_20261020T084747Z/references/REFERENCE_REVIEW.md), `clips.json` y `reference_validation.json` en la misma carpeta.

## 4. Matriz ejecutada y configuración efectiva

| ID | Experimento | Control / variable | Repeticiones | Estado |
|---|---|---|---:|---|
| A | FW small offline beam 1 frente a 5 | Mismo PCM, float16, temperatura 0, idioma en, task transcribe, sin VAD/glosario/contexto terminológico; cambia solo beam_size | 3 por clip y beam | 18 completas |
| B | Worker operativo real en VM | Señal constante 48 kHz; solo cambia tamaño de bloque 128/480/960 | 60 s por caso | Conteo demostrado |
| C | Correlación del PCM M3 | Misma señal fuente; templates sin escala frente a 129/128 | 6 ventanas de 5 s | Deriva/desplazamiento localizados |
| D | Worker original frente a fase continua | Misma señal sintética 48 kHz, bloques 128, cuantizador idéntico, FW float16 beam 5; cambia resample() solo dentro de VM | 2 por clip y perfil | 12 completas |
| E | AlignAtt directo | PCM fijo, beam 1 inicial, chunks 1 s, sin VAC/VAD | Intento inicial | OOM y abort nativo; no resultado |
| F | AlignAtt directo sincronizado | Mismo perfil E; sincronización CUDA común | Intento inicial | Abortado por reserva VRAM |
| G | AudioProcessor WLK completo en proceso | VAC/VAD/configuración de sesión, PCM cada 100 ms; sin puertos/DOM | Intento inicial beam 1 | Abortado por reserva VRAM |
| H | LocalAgreement ya instalado | Arquitectura alternativa con small CT2 auto, beam 5, chunks 1 s, trimming segment 15 s, confidence_validation=False | 2 por clip | 6 completas |

A alternó el orden beam 1/5 entre repeticiones. Se consumió cada generador y se separó carga/warmup/scoring del cronómetro ASR. Los JSON conservan parámetros y defaults relevantes. No se descargaron nuevos modelos ni paquetes; se fijó modo HF offline y se verificó el small PyTorch en caché por hash M3.

H usa efectivamente `int8_float16` en CUDA frente a float16 de A. Además cambia confirmación, prompts de contexto y trimming: **no es una comparación causal de una sola variable contra A o AlignAtt**. Se reporta como alternativa completa, no como efecto del beam.

## 5. Resultados de precisión, repetición y coste

| Perfil | n inferencias | WER agregado | CER agregado | RTF agregado | Pico VRAM total muestreado |
|---|---:|---:|---:|---:|---:|
| FW small offline beam 1 | 9 | 2.90 % | 0.89 % | 0.0145 | 1357 MiB |
| FW small offline beam 5 | 9 | 3.73 % | 1.96 % | 0.0194 | 1357 MiB |
| Worker original sintético + FW beam 5 | 6 | 3.11 % | 0.83 % | 0.0203 | 985 MiB |
| Fase continua sintética + FW beam 5 | 6 | 4.15 % | 2.17 % | 0.0196 | 985 MiB |
| LocalAgreement small beam 5 | 6 | 5.60 % | 2.99 % | 0.4423 | 953 MiB |

Agregación por suma de errores y denominadores, incluyendo repeticiones simétricas; las repeticiones no son muestras clínicas independientes. Los mismos tres recortes producen una única hipótesis normalizada por condición en las repeticiones observadas. Esto no garantiza determinismo universal ni estabilidad de una conferencia.

| Recorte | FW beam 1 | FW beam 5 | Worker original sintético | Fase continua | LocalAgreement |
|---|---:|---:|---:|---:|---:|
| cardio_01 | 1.12 % | 1.12 % | 1.12 % | 1.12 % | 2.23 % |
| cardio_02 | 0.64 % | 0.64 % | 0.64 % | 0.64 % | 1.28 % |
| cardio_03 | 7.48 % | 10.20 % | 8.16 % | 11.56 % | 14.29 % |

Estos 482 tokens no son el corpus M3 de 4204 palabras. Cambiar longitud/contexto/cortes cambia la tarea; no comparar sus porcentajes como si se hubiera mejorado o empeorado el benchmark completo.

RTF offline no mide latencia visible. En H, el lag algorítmico de compromiso mediano por recorte fue aproximadamente **1.60–1.85 s**, máximo **6.92 s**, calculado desde disponibilidad nominal del audio hasta el fin de token estimado por ASR. No incluye pintado ni garantiza ese tiempo en vivo. El cierre entrega un tail no confirmado por dos hipótesis: dos tokens en cardio_01; queda registrado.

GPU/VRAM son del dispositivo completo, con otros procesos/Windows, no de un allocator. El muestreo nominal de 1 s tuvo intervalos reales cercanos a 6 s por consultas/guard; puede perder picos. Utilización media muestreada: A ~43 %, D ~65 %, H ~58 %. La temperatura y todos los samples están en los JSON. No hay ensayo térmico prolongado.

Tablas y resultados completos: [COMPARISON.md](C:/live-captions/logs/trad_lab/m4_20261020T084747Z/COMPARISON.md), [comparison.json](C:/live-captions/logs/trad_lab/m4_20261020T084747Z/comparison.json). Los RAW, segmentos, alineamientos S/D/I, señales clínicas y parámetros permanecen en cada JSON privado.

## 6. Captura: deriva, inicio y cola

Se ejecutó `app/static/recorder_worker.js` sin editarlo, en una VM Node:

| Entrada 48 kHz de 60 s | Muestras de salida a 16 kHz | Duración etiquetada |
|---|---:|---:|
| Bloques 128 | 967500 | **60.468750 s** |
| Bloques 480 | 960000 | 60.000000 s |
| Bloques 960 | 960000 | 60.000000 s |

`round(128/3)=43` reinicia la fase en cada bloque. El factor de longitud es `43×3/128=129/128`, +0.78125 %. Esto deforma la base temporal; no equivale a probar duplicación de palabras. La prueba con señal constante aísla el conteo, y la prueba de forma de onda utiliza una señal variable independiente.

El PCM M3 se analizó sin ASR: ventanas de la fuente a 10/20/30/40/50 s solo encajan bien al escalar el template por 129/128. Correlaciones absolutas 0.68–0.80, frente a menos de 0.27 sin escala. Ajuste temporal:

`tiempo_capturado ≈ 1.007790 × tiempo_fuente − 4.760775 s`.

Residuo máximo entre esos cinco anchors: ~0.613 ms. El ajuste estima **4.724 s iniciales de fuente ausentes** y **5.576 s de cola capturada después del fin de fuente alineado**. Esto explica por qué 61.283 s enviados no significan 61.283 s de contenido original íntegro.

La cola **no es silencio digital**: RMS de ventanas finales ~0.057–0.068, componente dominante ~298 Hz, creciente concentración tonal. Es compatible con un componente cercano a 300 Hz tras la escala temporal; no se certificó su origen ni se interpreta como habla. No se encontró evidencia que permita atribuir ese inicio/cola al Blue Yeti: M3 usó un archivo de audio falso de Chrome.

No se probó exhaustivamente ausencia de duplicaciones en todo el audio ni se reconstruyó el comienzo perdido. El análisis se limita a anchors y espectro; el contenido que falta no se recupera con un glosario. Evidencia: [audio_diagnostic.json](C:/live-captions/logs/trad_lab/m4_20261020T084747Z/m3_audio_analysis/audio_diagnostic.json), `actual_worker_probe.json` y `tail_spectrum.json` de esa carpeta.

El prototipo `continuous_box.cjs` conserva el promedio de tres muestras a través de fronteras y produce exactamente 16 kHz en los tres fragmentos. El test independiente comprueba invariancia ante siete particiones del mismo stream. Solo soporta 48→16 kHz; EOF informa hasta dos muestras de entrada incompletas. No se conectó a CAPTURE.

## 7. Significado médico y referencia provisional

No se usa WER como certificado de fidelidad clínica. Cada resultado registra negaciones, números, unidades, contexto de dosis y déficit léxico de términos. Son alertas/proxies con solapamientos y cobertura limitada, no un conteo adjudicado de errores médicos.

Hallazgos que requieren revisión:

- La referencia de cardio_03 contiene `primary allosteronism` donde varias hipótesis producen `primary aldosteronism`. Se conserva la referencia intacta y se marca como posible errata, sin declarar automáticamente erróneo al ASR.
- La referencia representa porcentajes mediante `%`; algunas hipótesis dicen `percent`. También aparecen `stage 1/2` frente a `stage one/two`. El scoring primario penaliza diferencias de formato y su tokenización omite el símbolo %. Eso explica parte de las diferencias de WER/unidades.
- Una sensibilidad **secundaria, post hoc y explícita** expande `%` y unifica solo `stage one/two` simétricamente: WER agregado A beam 1 2.26 %, A beam 5 2.67 %, D original 2.46 %, D fase continua 2.67 %, H 4.11 %. No cambia referencias/RAW ni sirve para aprobar candidatos. No unifica negaciones, cantidades distintas o términos médicos.
- Las formas `normotensive`/`normo-tensive` generan déficits léxicos sin demostrar pérdida del concepto. Los términos y contextos originales se conservan para revisión.
- Las discrepancias M3 `57`/`567` y `2024`/`2020/24` siguen siendo señales relevantes, pero en M4 no hubo una captura nueva completa para verificar si persisten. No se adjudicaron por comparación contra otro ASR.
- Estos recortes no cubren de forma suficiente nombres específicos de medicamentos. Cero flags de fármacos no acredita seguridad. Se necesita una prueba supervisada con esos nombres y negaciones/dosis adjudicadas antes de aceptación.

La corrección temporal está demostrada; su beneficio clínico general no. El A/B sintético no incluye AGC, inicio del navegador, micrófono, red ni streaming AlignAtt completo. No se presenta la mejora de conteo como una mejora aprobada del sistema entero.

## 8. Hipótesis, bloqueos y alternativas

| Hipótesis | Dictamen | Evidencia / límite |
|---|---|---|
| El worker puede distorsionar el reloj PCM | Confirmada para bloques 128 a 48→16 kHz | Conteo real del worker y anchors de forma de onda M3 |
| El archivo fuente completo llegó a CAPTURE en M3 | Refutada para ese ensayo sintético | Inicio ~4.72 s ausente; cola adicional no silenciosa |
| El Blue Yeti es la causa | No sustentada | El caso analizado no utilizó el micrófono real |
| Beam 5 mejora siempre small | Refutada en estos recortes | Tres repeticiones; cardio_03 y agregados no mejoran |
| small es insuficiente en general | Inconclusa | Calidad dependiente de recorte/contexto; sin benchmark clínico certificado |
| El idioma inglés explica el fallo por decoder español | No observado en M3; no revalidado por nueva captura M4 | No confundir metadata M3 con inferencia nueva |
| SegmentManager introduce esas diferencias | No observado en el fragmento M3 | RAW→READY 0 % allí; no hay nueva prueba completa M4 |
| AlignAtt beam 5 es viable/mejor que beam 1 | Bloqueada | No se completó siquiera el baseline M4 beam 1 |
| LocalAgreement instalado resuelve el problema | No demostrada | 5.60 % WER, mayor RTF, lag algorítmico; sin DOM/OBS |

El primer replay AlignAtt acabó en CUDA OOM/abort nativo. El sincronizado llegó a 7923 MiB de uso total; AudioProcessor con VAC/VAD llegó a 7927 MiB y se abortó por menos de 768 MiB libres. El último había enviado solo 26.5 s. No se calcularon WER/CER finales sobre esas salidas truncadas.

No se ha aislado si el consumo depende del harness, mezcla de allocators, audio/contexto, pacing u otra condición instalada. No equivale a demostrar que todo servidor WLK falle: M3 completó una sesión bajo otras condiciones. No se forzaron tipos de cómputo, paquetes o modelos para obtener un PASS.

| Alternativa | Evidencia actual | Memoria/latencia/complejidad | Riesgo y viabilidad para congreso |
|---|---|---|---|
| Corregir continuidad de fase en captura | Alta para corregir duración; limitada para clínica | Prototipo 48→16; buffering máximo 2 muestras (~0.042 ms). Falta navegador real y otros rates | Cambio mínimo prometedor; requiere validación, no aprobado |
| Aumentar beam AlignAtt | Sin resultados completos | Consumo M4 ya bloquea baseline; beam 5 puede cambiar coste | No proponer despliegue con esta evidencia |
| Cambiar a LocalAgreement CT2 instalado | Seis replays completos | ~953 MiB muestreados, RTF ~0.44; lag hasta 6.92 s; cambia política/contexto | Alternativa de investigación, riesgo mayor; no mejora demostrada |
| Sustituir small por medium/turbo | Solo benchmark offline M3 | Memoria, latencia y arquitectura streaming no verificadas | No justificado automáticamente |
| ASR offline por ventanas y confirmación | Solo idea/viabilidad de FW offline | Exigiría diseñar reencolado, contexto, límites y cierres | No implementada; demasiado incierta para promover sin ensayos |

## 9. Pruebas y regresiones

**81 tests Python PASS, sin skips**, usando el entorno ASR existente para ejecutar también FFT NumPy/SciPy: laboratorio M3/M4, normalizador, SegmentManager y validación de release. Pruebas nuevas: aceptación por hash/negación de referencias alteradas, alineación de forma de onda con delay/ganancia/DC/polaridad, y sensibilidad de formato que conserva diferencias de negación/cantidad.

Node: PASS en siete particiones del stream y tratamiento explícito del grupo EOF incompleto. Se ejecutó además el worker operativo en VM para los tres tamaños de bloque y A/B completo. No son pruebas de dispositivo físico ni sustituyen pintado real.

No se ejecutó un E2E nuevo que arrancara servicios sin autorización. Compilación de fuentes y comprobación de whitespace completadas. Los manifiestos de preservación y resultados de pruebas están en el run privado; el checkpoint y los resultados M3 se conservaron por hash.

## 10. Cambio mínimo propuesto, aprobación y rollback

**Propuesta técnica:** preparar en un hito autorizado una corrección de fase/estado del remuestreador, conservando el protocolo CAPTURE, EOF, cuantización, autenticación y SegmentManager. La implementación existente permanece intacta. El prototipo de laboratorio demuestra la propiedad de duración y ayuda a definir los tests; no es todavía un reemplazo completo para todas las tasas de audio.

Antes de aplicarlo:

1. Revisar este informe y las ambigüedades de referencia. Decidir si se autoriza el ensayo de servicios ya propuesto; no ha sido ejecutado.
2. Repetir captura real con un inicio de reproducción controlado después del handshake o preroll claramente registrado, verificar que se conserva la introducción y separar señal útil de cola. No confundir una corrección del harness con una mejora del micrófono.
3. Resolver el bloqueo de VRAM con trazas de asignación y una sesión baseline reproducible. Comparar beam 1/5 solo con baseline completo, sin cambiar simultáneamente precisión/política/audio.
4. Validar el remuestreador en 48/44.1/16 kHz y bloques variables, continuidad entre bloques y EOF. Correlacionar PCM, RAW, READY y DOM con tiempos comparables; revisar términos, cifras, unidades, negaciones y medicamentos por escucha.
5. Definir y aprobar criterios de latencia visible y fidelidad antes de promover. Mantener DeepL deshabilitado en laboratorio; cualquier ensayo real facturable requiere autorización aparte.

Rollback de M4 no requiere restaurar LIVE porque no se modificó. Para recuperar el estado pre-M4, inspeccionar primero `codex/s2-m4-checkpoint` o extraer el ZIP en otra carpeta y comparar hashes; restaurar solo archivos autorizados. Si más adelante se aprueba un parche, registrar diff/checkpoint y revertir únicamente ese parche con sesión detenida tras revisión. No usar reset hard, clean ni alterar main/RC.

**Trabajo detenido para revisión del usuario. No se inició M5, no se modificó LIVE ni se declaró un candidato aprobado.**
