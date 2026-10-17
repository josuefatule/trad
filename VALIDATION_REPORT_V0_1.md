# M8 — Validación integral y candidato v0.1.0-rc1

Fecha: 2026-10-17. Baseline Git **6b4d729**, limpio al iniciar. Sin AGENTS.md
aplicable. Se revisaron README, ARCHITECTURE, PLAN, OPERATOR_CONSOLE, OBS_OVERLAY,
M7_REPORT, RELIABILITY_RUNBOOK, M5.2 y código/tests relacionados.

**Resultado: candidato técnico; aprobación final PENDIENTE.** M8 no está cerrado.
No se modificó código de producción, configuración A, reconciliación, WLK/modelo,
normalizador, glosarios, DeepLProvider, Hub, protocolos ni persistent_rolling.
No se reinició ningún servidor operativo ni se hicieron llamadas DeepL reales.

## Estados de evidencia

| Área | Estado | Alcance / límite |
|---|---|---|
| M7 con Blue Yeti/WLK/DeepL/Operator/CAPTURE/OBS, START/STOP/CLEAR y recovery | VALIDADO MANUALMENTE, informado por usuario | Confirmación explícita en brief M8; sin inventar una duración ni nuevas mediciones |
| Regresión baseline M1–M7 | VALIDADO AUTOMÁTICAMENTE | 175 Python PASS, 415.819 s; seis suites JS PASS |
| Regresión final M1–M8 | VALIDADO AUTOMÁTICAMENTE | 180 Python PASS y seis suites JS PASS; acta al final |
| Cadena integrada con fixture y Chrome | VALIDADO AUTOMÁTICAMENTE | Audio sintético, WLK y provider simulados; FastAPI/PCM/normalización/Hub/WS/DOM reales |
| Replay médico A y latencias por segmento | VALIDADO AUTOMÁTICAMENTE | Mismo stream y timing original; no voz nueva ni latencia física |
| Seguridad local / límites / fallos | VALIDADO AUTOMÁTICAMENTE + auditoría local | Tests y revisión; no pentest ni auditoría de toda dependencia externa |
| Nueva lectura física M8 y salida OBS/proyector | PENDIENTE | M7 informado no sustituye aceptación de este RC |
| Sesión real 60–90 min / consumo / CPU / RSS / GPU | PENDIENTE | Soak virtual no acredita hardware sostenido |
| Instalación limpia Windows/GPU y revisión clínica | PENDIENTE | Inventario/pins auditados; no reinstalación del entorno operativo |
| Release definitivo v0.1.0 | PENDIENTE | Validación manual y autorización explícita |
| Impedimentos técnicos actuales | Ninguno BLOQUEADO en la automatización | Si falla un gate manual, registrar BLOQUEADO con causa; no transformarlo en PASS |

## Recorrido end-to-end reproducible

`tests/test_release_e2e_browser.py` arranca ASGI y WLK simulado en puertos efímeros
y un perfil Chrome temporal, sin interferir con 8000/8010. CAPTURE produce PCM
mediante un dispositivo fake real del navegador, sin bypass de autoplay. WLK
reproduce los 888 mensajes del fixture con sus offsets originales; EOF solo se
envía tras STOP del navegador. El fixture procede de voz real histórica, pero
**en este test el PCM no genera ese ASR**. El provider inyectado devuelve etiquetas
`Validation caption N`, nunca se presenta esto como traducción médica.

| Paso solicitado | Evidencia automática | Verificación física M8 |
|---|---|---|
| 1–2 backend y WLK disponibles | Arranque real ASGI, config/handshake WS simulado y fallos M7 | Arranque modelo WLK real PENDIENTE |
| 3–5 Operator, CAPTURE, selección/captura | Chrome real, popup, fake media, frames PCM positivos | Blue Yeti/permisos/dispositivo PENDIENTE |
| 6–8 ASR, READY, normalización | Payloads reales históricos a ritmo original; normalizador real y correcciones observadas | Lectura nueva PENDIENTE |
| 9 DeepL | Cola/provider fake + tests HTTP/retry/fallo; inglés histórico exacto del fixture | Llamada real y revisión del inglés PENDIENTES |
| 10–12 Hub, overlay, rolling | Publicación real WS y texto DOM Chrome; suites geometry/rolling | OBS Browser Source/compositor/proyector PENDIENTES |
| 13–14 CLEAR y continuidad | Watermark/generación, DOM vacío y siguiente caption; historiales conservados por tests M6/M7 | PENDIENTE |
| 15–17 STOP, limpieza, START aislado | Dos EOF, dos sesiones, complete, cola 0, sin historia anterior | Liberación física del micro y STOP PENDIENTES |
| 18 recarga Operator LIVE | Mismo session_id, una conexión WLK, owner y controles recuperados | Continuidad audible PENDIENTE |
| 19 reconexión overlay | Recarga Chrome, restauración una vez, sin llamadas duplicadas | Refresh cache y salida real OBS PENDIENTES |

El test espera el documento nuevo después de reload y el estado LIVE de la consola
antes de STOP de la segunda sesión. Sus primeros fallos fueron del harness
(selector CLEAR equivocado y snapshot STOPPED anterior aún visible), corregidos
sin cambios al producto. No se identificó un bug reproducible del pipeline M7.

Los archivos `benchmarks/m8_e2e_results.json`, `m8_replay_results.json` y
`m8_soak_results.json` son evidencia automatizada diferenciada. El recorrido manual
completo está en [MANUAL_VALIDATION_V0_1.md](MANUAL_VALIDATION_V0_1.md).

## Latencia

Ver [LATENCY_BASELINE_V0_1.md](LATENCY_BASELINE_V0_1.md) para n/mediana/p90/p95/máximo,
relojes por etapa, cola, tasa, evolución por tercios y sesiones históricas separadas.
El replay A da **17 READY, mediana 3751 ms, p90 5529 ms, p95/máximo 5539 ms** desde
primera aparición confirmada. READY→normalizador se mide en milisegundos; no se
redujeron thresholds. El poll de Operator añade hasta 2 s de percepción visual.
Captura/voz→ASR y voz→pantalla física no están medidas; doble-rAF no mide OBS.

## Calidad lingüística

Fixtures: stream completo 888 eventos/58.300 s, reducido 61 eventos de la misma
grabación, anotaciones manuales `medical_units.json`, observación textual M3.1 y
controles sintéticos de revisión/negaciones/números/unidades. No hay otra grabación
independiente con timing verificado. Los guiones `medical_reference*.txt` son
referencias de lectura/traducción, no una transcripción humana alineada y validada
del audio. **No se calculan WER real, BLEU ni COMET.**

- RAW READY: **81/81 palabras**, igualdad ordenada exacta, IDs únicos, cero pérdidas,
  duplicaciones o late revisions y PENDING vacío al EOF. Esto conserva ASR, no prueba
  que ASR haya reconocido correctamente las palabras pronunciadas.
- Palabras/READY min/mediana/media/máximo: **1 / 5 / 4.765 / 8**. Flush: soft 10,
  hard 3 (17.65%), puntuación 3, session_end 1; **9 forced_whitespace_cut_count**.
- 5/12 unidades médicas anotadas fragmentadas, con 5 límites internos. Las anotaciones
  son una muestra manual, no una métrica clínica generalizable.
- Tres correcciones locales: `systólica→sistólica`, `Suficio patología→Fisiopatología`,
  `al dosterona→aldosterona`. Cambiar número de tokens por una corrección esperada no
  viola la integridad RAW; no se exige igualdad de palabras entre RAW y NORMALIZED.
- El caso textual M3.1 conserva sus siete correcciones y sugerencia incierta; incluye
  fármacos y 24 horas, sin timestamps para medir segmentación/ASR de ese caso.
- El control sintético nuevo conserva literalmente `No`, `ni`, `5 mg`, `120/80 mmHg`,
  `3,5 mmol/L`, `edema` y `disfunción renal` al normalizar. No demuestra conservación
  por ASR ni por DeepL real. `angiotensina 2→II` es una corrección farmacológica
  histórica intencional del glosario, no una promesa de preservar cada carácter numérico.

Se reutilizan 17 salidas inglesas históricas A **solo tras verificar** fixture,
glosarios, configuración, RAW, NORMALIZED y dos segmentos de contexto idénticos.
No se crean solicitudes duplicadas. Los tiempos offline históricos de DeepL no se
mezclan con el E2E sintético. Texto completo por segmento:
[M8_MEDICAL_SEGMENTS.md](benchmarks/M8_MEDICAL_SEGMENTS.md).

| Origen | Ejemplo observado | Consecuencia | Severidad |
|---|---|---|---|
| ASR | `En pacientes y pertencios` | El normalizador conservador no reescribe el pasaje; inglés histórico `patients and their relatives` altera el sentido del guion | Alta, semántica médica |
| ASR / normalización | `herenina` separado del resto del sistema | RAW conserva el error; no hay corrección terminológica local garantizada | Media, revisión requerida |
| Segmentación | `...sistólica y/o` separado de `diastólica.` | Unidad de presión rota; contexto desigual en traducciones | Alta si se pierde cualificador |
| Traducción histórica B, NO activa | `sistólica y/o` → `and/or` | Omite sistólica; A histórico conserva `systolic blood pressure and/or` | Alta; mantener ejemplo de regresión contextual |
| Segmentación + traducción A | `hipertrofia ventricular` / `izquierda,` → `ventricular hypertrophy` / `,` | Se pierde lateralidad en inglés | Alta |
| Segmentación + traducción A | `...infarto agudo de` / `miocardio.` → `...acute myocardial infarction` / `myocardial infarction.` | Duplicación semántica inglesa aunque RAW tiene 81/81 | Alta |
| Normalización esperada | `al dosterona` → `aldosterona` | Corrige un término partido dentro del READY; no fusiona READY anteriores | Corrección positiva; no certifica todos los fármacos |
| Negaciones/números/unidades | Cobertura positiva sintética en normalizador; corpus cronometrado limitado | No hay datos suficientes para afirmar exactitud end-to-end de dosis, unidades o negaciones | PENDIENTE, revisión manual |

M8 documenta estos errores; no los corrige cambiando segmentación o traducción.
La persona que apruebe v0.1 debe revisar su impacto y aceptar explícitamente los
límites o bloquear el release. La referencia clínica requiere revisión competente.

## Duración y recursos

Se repite la prueba sintética M7 sin modificarla. `m8_soak_results.json` conserva los
resultados nuevos; `m7_soak_results.json` queda intacto como histórico. Simula más de
3600 s con fallos deliberados, límites de memoria/historial/colas y cleanup.
Un outcome **incomplete** es el resultado esperado al inyectar fallos de traducción,
no un fallo oculto ni un STOP completo.

Resultado M8 nuevo: **3603.304 s virtuales / 394.795 s de ejecución**, 36000 frames,
115.2 MB de PCM sintético, 901 mensajes/300 fuentes, **600 READY y 5400/5400 palabras**.
591 traducciones simuladas completadas, 9 fallos deliberados, 608 intentos, 16 retries
y 16 posibles solicitudes duplicadas simuladas. Cola máxima 2; journal máximo 512
eventos/599244 bytes, 388 recortes explícitos; Hub 128 captions, cola de observador 2
y una expulsión lenta deliberada. Memoria Python trazada final 4768402 bytes, pico
4938087 bytes; tasks 1→1, threads 2→2, workers/cola/suscriptores 0 tras STOP.
El historial ASR crece dentro del presupuesto (300 fuentes en este ensayo): no se
demuestra memoria plana ni operación ilimitada. No se mide CPU/RSS/GPU de una hora real.

No confundir segundos simulados con tiempo real de ejecución. Memoria tracemalloc
es Python trazado, no RSS, Chrome, WLK, OBS ni VRAM. La hora real con Blue Yeti/DeepL/
OBS, CPU/memoria/GPU, consumo y lag inicio/final sigue **PENDIENTE**; el protocolo
incluye registro cada cinco minutos y una grabación audiovisual opcional autorizada.

## Seguridad y privacidad

| Hallazgo / control | Evidencia M8 | Severidad / límite |
|---|---|---|
| Clave DeepL fuera de Git | `.env` ignorado; búsqueda del valor real en archivos tracked y tres logs actuales: 0 coincidencias; no se imprimió la clave | Sin fuga observada en ese alcance; no es barrido de todos los archivos/historial |
| Loopback | WLK 8000 en ::1 y 127.0.0.1; FastAPI 8010 en 127.0.0.1 | Verificado localmente; no abrir interfaces LAN |
| Host/Origin/nonce/owner | Tests rechazan clientes remotos, sin nonce, owner antiguo y generaciones obsoletas | PASS; no protege frente a código malicioso local/mismo origen |
| Estado/control | Status requiere nonce, CLEAR/STOP owner y contexto vigente; bootstrap local no llama DeepL | PASS; configured no prueba conectividad |
| Overlay readonly | Tests no permiten control desde observadores; no nonce/key en eventos; mock público filtrado | PASS; inglés/snapshots disponibles a procesos locales sin nonce |
| Resume/admin | Rotación/revocación, lease y ACL local comprobados por M7/tests M8 | PASS; no compartir `.runtime` ni tokens; sin auth remota |
| Logs | RAW desactivado; redacción de secretos/texto probada; rotación acotada | Persisten logs RAW históricos locales opt-in: protegerlos, no incluirlos en release |
| Audio y datos | E2E fake PCM descartado; no archivo de audio ni llamadas DeepL reales durante M8 | No se cargó contenido confidencial; fixtures médicos genéricos sin pacientes identificados |
| Reinicio | Estado, autoridad, sesiones y contextos nuevos; no traducción/replay oculto | PASS automático; no recuperación de audio tras caída |

No se cambió el modelo de seguridad ni se ejecutó un escáner de vulnerabilidades
de toda la cadena de dependencias. La auditoría no certifica ausencia universal de
credenciales ni hace de localhost un entorno seguro frente a malware local.

## Reproducibilidad y operación

[INSTALL_WINDOWS.md](INSTALL_WINDOWS.md) documenta Python 3.12.10, pins app/test,
inventario ASR/CUDA, creación de venv separado, entorno, permisos, arranque/cierre,
diagnóstico de puertos y rollback. `pip check` pasa en el entorno existente.
**No se hizo instalación limpia** ni descarga/reinstalación ASR; ese gate es manual.
`.env.example` no contiene credenciales y mantiene traducción deshabilitada hasta
configuración explícita. Los paquetes del entorno operativo no se actualizaron.
Se fijó LF para glosarios/evidencia M8/pins mediante `.gitattributes` y se normalizó
la serialización de evidencia: autocrlf podía invalidar hashes sin cambiar el JSON.
No se modificó ningún glosario; se conservan sus hashes históricos en nuevos checkouts.

OBS usa 1920×1080, PowerPoint arriba conservando aspecto, franja inferior y Browser
Source transparente encima. Geometría real Chrome valida dos líneas a 48 px/150 px,
tres a 36 px/150 px; aumentar únicamente a 180 px sigue dejando dos líneas a
48 px/line-height 1.2. Se limita capacidad sin encoger arbitrariamente la fuente.
OBS/proyección física requieren la comprobación manual indicada en
[OBS_OVERLAY.md](OBS_OVERLAY.md).

## Release y pendientes

Solo crear commit M8 y tag local `v0.1.0-rc1` después de PASS automático completo.
No publicar remotamente, no tag `v0.1.0`, no Sprint 2. Consultar
[RELEASE_CHECKLIST_V0_1.md](RELEASE_CHECKLIST_V0_1.md). M8 sigue abierto hasta acta
manual de E2E/OBS, hora real, instalación limpia, revisión lingüística y autorización.

## Acta automatizada final

- Baseline existente: **175 tests Python PASS en 415.819 s**, sin skips; seis suites JS PASS.
- Final: **180 tests Python PASS en 475.326 s**, sin skips; seis suites JS PASS.
  Salidas locales ignoradas por Git: `logs/m8-baseline-python.log`, `logs/m8-final-python.log`.
- Nuevos tests: cuatro controles de evidencia (integridad/proveniencia histórica,
  percentiles/ausencia de muestras, correlación de relojes/generaciones y preservación
  de negaciones/números/unidades) y un E2E Chrome integrado de dos sesiones.
- JS: `test_operator_console.cjs`, `test_operator_partial.cjs`, `test_overlay_renderer.cjs`,
  `test_persistent_captions.cjs`, `test_overlay_geometry.cjs`, `test_reliability.cjs`.
  Ejecutados con runtime Node de Codex, ya que `node` no está en PATH; no se omiten suites.
- Replay y generador de tablas ejecutados sin red. `pip check` PASS; enlaces locales
  de documentación comprobados; `git diff --check` sin errores de whitespace.
- Fuente ejecutada conservada en commit RC. `benchmarks/m8_validation_results.json`
  registra resultados, hashes de evidencia y ausencia de cambios app/glossaries.
