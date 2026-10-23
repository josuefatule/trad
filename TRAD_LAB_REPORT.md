# TRAD — Sprint 2 / M3: TRAD-LAB

Fecha: 20 de octubre de 2026. Equipo: RTX 4070 Laptop, 8188 MiB reportados por NVIDIA-SMI, driver 596.08. Ejecución privada: `C:\live-captions\logs\trad_lab\20261020T074247Z`.

## Resultado y alcance

Se implementó un evaluador local aislado y se completaron las tres conferencias con `small`, `medium` y `large-v3-turbo`, secuencialmente, además de un experimento separado `small-context`. Las referencias de TurboScribe fueron revisadas por el usuario, pero siguen siendo provisionales y no constituyen ground truth clínicamente certificado.

`medium` presenta el menor WER agregado de esta pasada, mientras `large-v3-turbo` conserva más ocurrencias léxicas de términos en la tercera conferencia. Estas mediciones no acreditan un ganador para congreso ni explican por sí solas el fallo del ensayo LIVE. No se cambió el modelo operativo.

Herramienta y uso: [trad_lab/README.md](C:/live-captions/trad_lab/README.md). Resultados completos: [SUMMARY.md](C:/live-captions/logs/trad_lab/20261020T074247Z/evaluation/SUMMARY.md) y [summary.json](C:/live-captions/logs/trad_lab/20261020T074247Z/evaluation/summary.json). Cada combinación contiene `REPORT.md`, `result.json`, `rescored_metrics.json`, hipótesis cruda, referencia original, inventario médico y shadow del glosario.

## Auditoría y preservación

Rama `sprint2/m1-rtx4070`. HEAD, `main` y el commit señalado por `v0.1.0-rc1`: `64f82214b33fad4ee68295df1367249caeae3187`. Se preservó todo el trabajo sucio preexistente: 18 archivos modificados y los archivos no versionados del MVP/M1, incluido el glosario inglés del usuario. El estado inicial exacto está en `checkpoint.json`.

Checkpoint recuperable: [checkpoint.zip](C:/live-captions/logs/trad_lab/20261020T074247Z/checkpoint.zip), 129 archivos, SHA-256 `e222e2daac361ae6e8ffc0cc6c245601c79631b6f7e08df6094f94213a1165c1`. Incluye manifiesto, diff y estado Git; excluye `.env`, secretos, `.runtime`, entornos, cachés y resultados privados. Extraer primero en una carpeta vacía y restaurar archivos elegidos tras revisar el manifiesto; no aplicar un reset ni sobrescribir trabajo posterior.

Al inicio TRAD estaba LIVE EN→ES. No se detuvo desde el laboratorio. Tras la confirmación del usuario de que la sesión había terminado, se verificó que 8000/8010 no escuchaban y se ejecutaron los benchmarks. El usuario autorizó después iniciar únicamente la comparación aislada en 18000/18010. DeepL permaneció deshabilitado en esa prueba.

Los únicos archivos fuente nuevos son `trad_lab/`, `tests/test_trad_lab.py` y este informe. No se editó código operativo, thresholds de SegmentManager, `.env`, glosarios originales ni paquetes. No se hicieron commits, staging, tags, merges, resets, push ni cambios de `main`. Los pesos públicos faltantes de medium/turbo se descargaron en la caché local; corpus e hipótesis no se enviaron a servicios externos.

Verificación de preservación: [preservation_check.json](C:/live-captions/logs/trad_lab/20261020T074247Z/preservation_check.json). Los 129 archivos originales del checkpoint, los tres pares del corpus y ambos ejemplares del glosario mantienen sus hashes. El checkpoint no incluye secretos ni pretende ser una copia del entorno instalado.

## Corpus y perfil reproducible

| Muestra | Duración decodificada | Palabras de referencia normalizadas |
|---|---:|---:|
| cardio_01 | 344.723 s | 714 |
| cardio_02 | 955.848 s | 1781 |
| cardio_03 | 917.252 s | 1709 |
| Total | 2217.823 s / 36.96 min | 4204 |

Los MP3/TXT originales permanecen en `C:\TRAD-LAB\corpus`. SHA-256, MP3 / TXT, respectivamente:

- cardio_01: `59d1ec58514134f7bf326d824e33f61eb868713b71cad147395563104119a25d` / `036162774cd76db99225e636a1107309cd7a4e71b394bfb7561a5729df233e5d`.
- cardio_02: `a81932f2ad001ea95eafaff7b2ad08d007811b82a8daa9ef1c5392cc740bb420` / `a9014efd3faa653c8d916eff7059fc1f7b6d0b28aea60019302e301bb2abb949`.
- cardio_03: `cf2fd94d8dee89b55322cbb9618b251557c4e69157e614e74ca8060f7c3c07c5` / `9074c4a20521f6b0291a9dbc42c3552dbeb331fca2c0943a5cbf3bb9869b1a80`.

Se preservó cada TXT byte a byte y la hipótesis anterior a cualquier normalización. No se eliminaron pasajes de referencia ni se aplicó glosario a las referencias.

Entorno observado de ASR: Python 3.12.10, WhisperLiveKit 0.2.26, Faster-Whisper 1.2.1, CTranslate2 4.8.2, torch 2.14.0+cu126, PyAV 19.0.1, NumPy 2.5.4. No se actualizaron dependencias. `environment.json` por modelo registra versiones, revisión de snapshot, tamaños y hashes completos de los pesos, parámetros explícitos y defaults de `transcribe`.

Perfil baseline común: CUDA:0, float16, cuatro hilos CPU, un worker, `language=en`, `task=transcribe`, beam 5, best_of 5, temperatura 0, contexto de transcripción previo activado, word timestamps, sin VAD, initial_prompt ni hotwords. Se consumió el generador completo. RTF = segundos ASR / segundos audio; excluye carga, warmup, decodificación MP3, scoring y reportes. Una pasada por condición, sin aleatorización ni análisis de significancia o estabilidad térmica.

Incidencia reproducida: el `decode_audio` instalado de Faster-Whisper pasa `metadata_errors` a `av.open`, incompatible con PyAV 19. El laboratorio incorpora el mismo pipeline de frames/resample/s16 sin ese argumento obsoleto, sin parchear paquetes ni LIVE. Los WAV derivados mono 16 kHz decodifican exactamente al mismo PCM que sus MP3 de entrada; no se aplicaron ganancia, VAD ni denoise. No hubo muestras no finitas ni clipping a escala completa. Esto verifica el adaptador local, no el micrófono del ensayo anterior.

Un intento de descarga medium se interrumpió y conservó antes de reintentar con `HF_HUB_DISABLE_XET=1` solo en el proceso. La observación parcial no demuestra un defecto de Xet. Los intentos y logs se conservaron; la ejecución final completó los cuatro perfiles.

## Resultados comparables

| Modelo / muestra | WER | CER | RTF |
|---|---:|---:|---:|
| small / cardio_01 | 2.38 % | 0.66 % | 0.0204 |
| small / cardio_02 | 1.74 % | 0.58 % | 0.0206 |
| small / cardio_03 | 5.85 % | 2.61 % | 0.0208 |
| medium / cardio_01 | 2.94 % | 0.56 % | 0.0416 |
| medium / cardio_02 | 1.74 % | 0.69 % | 0.0392 |
| medium / cardio_03 | 3.80 % | 1.25 % | 0.0383 |
| large-v3-turbo / cardio_01 | 4.90 % | 3.22 % | 0.0281 |
| large-v3-turbo / cardio_02 | 2.58 % | 1.60 % | 0.0201 |
| large-v3-turbo / cardio_03 | 2.98 % | 1.75 % | 0.0202 |

| Perfil completo | Errores / 4204 palabras | WER agregado | CER agregado | RTF corpus | VRAM total pico muestreado |
|---|---:|---:|---:|---:|---:|
| small | 148 | 3.52 % | 1.43 % | 0.0206 | 1419 MiB |
| medium | 117 | 2.78 % | 0.90 % | 0.0392 | 2868 MiB |
| large-v3-turbo | 132 | 3.14 % | 1.93 % | 0.0214 | 2900 MiB |
| small-context, experimento separado | 151 | 3.59 % | 1.46 % | 0.0192 | 1396 MiB |

Las métricas agregadas suman errores y denominadores, sin promediar porcentajes de muestras desiguales. VRAM es el total del dispositivo muestreado cada 2 s, con baseline de 520–529 MiB; incluye Windows/otros procesos y puede perder picos cortos. No es la asignación exacta del proceso. Todos los modelos pasaron la comprobación CUDA float16 y la reserva previa de VRAM, sin solapar workers GPU.

WER/CER usan NFKC, casefold, apóstrofes unificados y puntuación/hífenes como separadores; conservan decimales y separadores numéricos internos. No convierten palabras numéricas, abreviaturas o unidades a equivalencias semánticas. CER incluye espacios únicos. La puntuación principal puede ocultar signos menos, comparadores y porcentaje: un canal adicional de firmas de medición crudas los expone como alertas. Vacío frente a hipótesis no vacía produce métricas indefinidas. No se interpreta `language_probability=1` de inglés forzado como confianza clínica.

## Errores médicos y límites

| Perfil | Déficit léxico de términos | Alertas numéricas | Unidades | Contexto dosis/medición | Medicamento | Polaridad/lateralidad |
|---|---:|---:|---:|---:|---:|---:|
| small | 34 | 14 | 5 | 11 | 1 | 2 |
| medium | 28 | 14 | 1 | 4 | 0 | 1 |
| large-v3-turbo | 6 | 23 | 3 | 6 | 0 | 1 |
| small-context | 35 | 17 | 5 | 11 | 1 | 2 |

Son proxies léxicos y alertas sobre alineamientos, no errores clínicos certificados. Las categorías se solapan; conceptos anidados pueden sumar varios déficits por una misma frase. La ausencia de alertas de negación o medicamento no demuestra seguridad ni cobertura exhaustiva. Diferencias como `one`/`1`, `1400`/`1,400`, abreviaturas y ortografía británica/estadounidense afectan la métrica sin implicar necesariamente cambio de significado.

En cardio_01, los tres baseline contienen `140 over 19` donde la referencia provisional dice `140 over 90`: candidato prioritario para revisar escuchando el audio, aunque el WER global sea bajo. En cardio_03, `small` pierde gran parte de las formas de `primary aldosteronism` y `aldosterone`; `medium` mejora el WER pero conserva déficits importantes de esos términos. Turbo conserva más ocurrencias, sin dominar las otras dos muestras. Todas las diferencias y contextos completos permanecen en los reportes privados.

## Glosario inglés v2

Se encontró `C:\Users\JF\Downloads\medical_base_en_tolerancias_v2.json`; es idéntico a `glossaries\medical_base_en.json`, 42577 bytes, SHA-256 `4a4920d3ff9404db5601c1c8f832dde4fdeb180dc95d3f06037576ec726c2896`. Se trabajó sobre una copia privada, sin activarlo en LIVE.

La auditoría final con el loader real admite 294 términos: 148 exact y 146 fuzzy. No detecta colisiones exactas; identifica 32 pares canónicos para revisión fuzzy, 66 entradas con cues sensibles y 44 variantes/aliases sensibles. El screening de pares no prueba que el matcher runtime efectúe esas sustituciones. Evidencia: [glossary_audit.final.json](C:/live-captions/logs/trad_lab/20261020T074247Z/glossary_audit.final.json).

`auto_apply=exact` aplica alias/variantes con confidence 1, independientemente de auto_threshold. En fuzzy, la ruta de una palabra técnica partida puede elevar el score al umbral: `hyper tenson` → `hypertension`, score previo 0.983333, confidence emitida 0.99. Es un score heurístico, no probabilidad calibrada. `suggest` no reemplaza términos, aunque el espaciado determinista sigue activo. Se conservan todos los reemplazos médicos para revisión humana, incluidos exactos.

| Perfil | WER sin corrección | Candidato glosario no aprobado | Controlado: solo espaciado |
|---|---:|---:|---:|
| small | 3.52 % | 6.30 % | 3.52 % |
| medium | 2.78 % | 5.45 % | 2.78 % |
| large-v3-turbo | 3.14 % | 5.76 % | 3.14 % |
| small-context | 3.59 % | 6.37 % | 3.59 % |

La expansión de siglas (`ASCVD`, `ESC`, etc.) y la conversión de sinónimos/formas numéricas aumentan la distancia lexical a estas referencias; ese aumento no equivale automáticamente a deterioro semántico. Tampoco hay evidencia para activar automáticamente todo el v2. El shadow se ejecuta por conferencia completa, sin reproducir límites READY ni contexto cruzado de LIVE.

El backend offline instalado admite `initial_prompt`; el experimento usa los primeros 30 canónicos del glosario en orden fijo, con límite de 160 tokens, idénticos para las tres muestras y sin selección desde las referencias. WER 3.59 % frente a 3.52 % y cardio_03 sin mejora. No demuestra utilidad de esta receta ni prueba todas las formas de contexto. No se inyectó contexto en WLK.

## Diagnóstico diferencial de streaming

Se completó una captura real mediante Operator/CAPTURE sin modificar, usando Chrome headless y el WAV derivado de los primeros 60 s de cardio_01. Se verificaron autenticación localhost, propietario, dirección EN→ES, handshake full/PCM/idioma, CLEAR, STOP y EOF binario. Sesión final `ecb0ad5dc137`: cierre `complete`, 19 segmentos READY, traducciones encoladas/exitosas/fallidas **0/0/0**. El usuario autorizó el inicio; ambos servicios aislados y sus launchers fueron cerrados después del STOP. Producción en 8000/8010 siguió detenida.

El capturador tuvo intentos fallidos por su manejo de popups y eventos CDP finales. Se corrigió únicamente código nuevo del laboratorio, se conservaron esos intentos y se repitió hasta obtener config, PCM, ASR final y frame STOP completos. No se presentan capturas incompletas como pruebas válidas.

Evidencia: [STREAMING.md](C:/live-captions/logs/trad_lab/20261020T074247Z/streaming_capture_complete/STREAMING.md), [control_evidence.json](C:/live-captions/logs/trad_lab/20261020T074247Z/streaming_capture_complete/control_evidence.json), [DIFFERENTIAL.md](C:/live-captions/logs/trad_lab/20261020T074247Z/same_pcm_differential/DIFFERENTIAL.md) y [differential.json](C:/live-captions/logs/trad_lab/20261020T074247Z/same_pcm_differential/differential.json).

Tras cerrar los servicios se ejecutó el mismo perfil offline `small` sobre el WAV fuente y sobre `capture.sent_pcm.wav`, que contiene los bytes binarios efectivamente enviados. Son 960000 muestras fuente (60 s) frente a 980529 enviadas (61.283 s): la captura del navegador añade temporización y no debe suponerse idéntica al archivo.

| Comparación de hipótesis | Discrepancia de palabras normalizadas | S / D / I |
|---|---:|---:|
| Offline fuente → offline PCM capturado | 7.94 % | 0 / 10 / 0 |
| Offline PCM capturado → WLK RAW | 6.90 % | 3 / 1 / 4 |
| WLK RAW → READY real de TRAD | 0.00 % | 0 / 0 / 0 |

Estas son discrepancias **entre hipótesis**, no WER de exactitud clínica: no existe una referencia revisada específica de ese recorte y no se utilizó el TXT completo para puntuar 60 s. Los porcentajes tienen denominadores diferentes y no se suman.

La hipótesis offline del PCM capturado omite diez palabras iniciales que aparecen en la hipótesis del WAV fuente. Esto identifica una diferencia anterior a la comparación de decoders y exige controlar el arranque del audio sintético; no demuestra un defecto del micrófono real. Con el mismo PCM enviado, WLK incorpora diferencias como `2024` → `2020/24` y `57` → `567`, además de muletillas y una etiqueta de música. Son candidatos para revisión, sin atribuir verdad clínica a la hipótesis offline. Los 119 tokens normalizados de WLK RAW coinciden con READY: **SegmentManager no añadió ni perdió tokens en esta captura**, aunque sí organizó 19 segmentos. Esto no certifica todas las revisiones o escenarios de segmentación.

El probe registró la configuración del decoder construido: solicitud, cfg, tokenizer y decode_options todos `en`; modelo `small`, política `simulstreaming`, encoder `int8_float16`, parámetros del decoder PyTorch `float32` en CUDA:0, beam 1. El decoder offline es CT2 float16 con beam 5. El código instalado de SimulStreaming usa Faster-Whisper para el encoder y PyTorch/AlignAtt para decodificar; compartir la etiqueta `small/faster-whisper` no iguala ambos caminos. El dtype registrado es el de parámetros, no una medición de todas las operaciones internas.

SHA-256 WAV fuente: `982995311f213fd2e483d227e92e272e028793cfbc89f199df130a94dc269416`; WAV enviado: `e811818ec0ebd41bc5d0efb2cac1cddca3e5f911b6863a69e79c39fb54b2179d`; payload PCM s16le: `e61016753946e2cfc206e4c9c24784a080233166063bf63cddaa331e9060d7d7`. Decoder PyTorch `C:\Users\JF\.cache\whisper\small.pt`: 483617219 bytes, SHA-256 `9ecf779972d90ba49c06d968637d720dd632c55bbf19d441fb42bf17a411e794`.

Conclusión delimitada: se reprodujeron diferencias antes de SegmentManager, tanto en el frente de captura como entre los caminos ASR sobre PCM común. No se observó un decoder en español en esta sesión EN. Aún no se determina cuál originó la mala calidad del ensayo anterior: faltan su audio/condiciones y ensayos que cambien por separado beam, cómputo y política de streaming. La prueba no verifica aislamiento entre sesiones EN/ES concurrentes ni autoriza cambios operativos para el congreso.

## Validación y siguiente milestone propuesto

Pruebas del laboratorio y regresiones del normalizador, SegmentManager y validación de release: 78 PASS. No requieren GPU ni red. Incluyen distancia exacta contrastada con DP independiente, vacíos, cifras/dosis/negaciones/signos crudos, glosario con colisiones y umbrales, archivos ambiguos, conservación de entradas, rechazo de reanudación alterada, guard LIVE y contrato de análisis RAW/READY. Los tests sintéticos no se presentan como evidencia de una captura real.

La herramienta rechaza sobrescribir inferencias completas; resume verifica corpus, hashes, perfil y artefactos. Archiva intentos fallidos, registra bloqueos sin cambiar dependencias y limita el tiempo del worker. El monitor puede terminar únicamente su worker si producción se activa o deja de ser verificable. Los reportes preservan métricas crudas y recalculan la política de alertas sin cambiar WER/CER.

Propuestas para un siguiente milestone, sin implementarlas aquí:

1. Revisar por escucha los candidatos médicos y disponer de referencias certificadas de fragmentos, con cifras/unidades/negaciones adjudicadas.
2. Repetir el diferencial con el audio y micrófono del ensayo fallido, y luego con voces/acento/ruido representativos del congreso. Fijar criterios clínicos y de latencia antes de cambiar el modelo operativo.
3. Comparar cambios de encoder, decoder, beam y política de streaming uno por uno, manteniendo PCM e idioma; no atribuir al modelo un efecto de varios parámetros mezclados.
4. Separar equivalencia léxica del glosario y mejora ASR; revisar alias clínicos y preparar una política de sugerencias supervisadas antes de autorizar reemplazos.
5. Resolver en un entorno de prueba la compatibilidad Faster-Whisper/PyAV y fijar versiones reproducibles antes de migrar paquetes operativos.

No se inició el siguiente milestone.
