# M7 — Reliability, Recovery & Operational Resilience

Fecha: 2026-10-17. Base auditada: M6 `0d4eb6c`. La aceptación real de M6 con
START/voz/DeepL/OBS/CLEAR/STOP fue proporcionada por el usuario. Este informe
distingue esa evidencia de las pruebas sintéticas M7.

## Resultado y alcance

M7 añade recuperación exclusiva del controlador sin reiniciar la captura,
supervisión de flujo, fallos/reintentos diferenciados, STOP finito y presupuestos
operativos. **No modifica configuración A, SegmentManager, reconciliación, READY,
late revisions, TerminologyNormalizer, glosarios o modelo WLK.** No implementa M8
ni Sprint 2. Tras las pruebas se activó M7 reiniciando únicamente FastAPI, después
de verificar STOPPED dos veces. WLK conservó su proceso/configuración. No se hicieron
peticiones DeepL reales durante este trabajo.

La auditoría previa está en [M7_AUDIT.md](M7_AUDIT.md); decisiones y procedimientos
en [RELIABILITY_RUNBOOK.md](RELIABILITY_RUNBOOK.md). Se revisaron README, arquitectura,
plan, consola, overlay y reportes M5.1/M5.2. Baseline: **143 tests Python y cinco
suites JS PASS** (`logs/m7-baseline.log`).

## Cambios de arquitectura

- El cierre/refresh del documento dueño de AudioContext destruye la captura. Por
  ello se separa CAPTURE, un popup del mismo origen, de la consola controladora.
  La recuperación de la consola rota token/secreto, revoca el anterior y conserva
  socket, session_id, manager y cola. Se restaura una proyección acotada del
  historial, sin invocar otra vez la normalización o DeepL.
  La consola consulta cada 2 s y puede añadir 0–2 s a su vista; OBS mantiene su
  WebSocket inmediato. Ese coste del monitor no se atribuye a SegmentManager.
- La recuperación administrativa no es un endpoint de takeover libre: requiere
  nonce local, origen exacto, secreto de archivo protegido, sesión vigente y 15 s
  de ausencia del propietario. CAPTURE no mantiene vivo ese lease.
- No es seguro recrear un procesador WLK tras perder PCM durante LIVE y conservar
  los cursores antiguos. Se reintenta únicamente antes de comenzar PCM; pérdidas
  posteriores terminan incompletas y requieren intervención/nuevo START.
- No se confunde socket abierto con actividad: frames, energía y mensajes ASR
  se miden separadamente. Falta de texto durante silencio no dispara fallo.
- Los errores permanentes auth/cuota evitan solicitudes posteriores; transitorios
  tienen backoff/deadline/cooldown. Cada pérdida, expiración, rechazo o cancelación
  conserva identificación y métricas, sin publicar español como inglés.
- Se mantienen overlay v3 y su watermark. Los únicos cambios del Hub son metadatos
  acotados de transporte por observador; orden, dedup y CLEAR siguen iguales.

La política HTTP sigue los códigos del [contrato oficial DeepL](https://github.com/DeepL/openapi/blob/main/openapi.yaml).
No se promete facturación exactamente una vez cuando se pierde una respuesta.

## Matriz de fallos y fault injection

Todos los escenarios se ejercitan sin servicios externos facturables. `R` indica
`tests/test_reliability.py`, `P` `tests/test_proxy.py`, `O` `tests/test_operator_control.py`,
`H` `tests/test_overlay.py`, `T` `tests/test_translation_engine.py`.

| # | Escenario | Tratamiento implementado / evidencia |
| --- | --- | --- |
| 1 | WLK ausente antes de START | Tres intentos, error visible, sin PCM; R startup + P connection_error_visible |
| 2 | WLK perdido durante LIVE | Sin reconexión insegura; error/incompleto y cancelación; P upstream_disconnect_is_error + R live_failure_never_reconnects |
| 3 | WLK recuperable antes de PCM | Segundo intento y un solo upstream entregado; R wlk_startup_recovers_once_before_any_pcm |
| 4 | Fallos repetidos / cancelación | Límite exacto de tres; cancelación del backoff sin segundo socket; R repeated_startup_failure / cancel_backoff |
| 5 | Browser Source desconecta/reconecta | Snapshot vigente sin nueva traducción; H subscription_never_connects_wlk y JS overlay_renderer |
| 6 | Reload después de CLEAR | Generación/watermark filtran historia anterior; O live_clear_all_observers_reconnect + JS overlay_renderer |
| 7 | Operator refresh LIVE | Par rotado, mismo socket/sesión/audio; R refresh_rotates_owner + JS reliability + Chrome real con media falsa |
| 8 | Propietario perdido | Heartbeat expira sin cortar CAPTURE ni dar controles a otro nonce; R owner_loss + carga prolongada |
| 9 | Recuperación autorizada | Secreto local + lease ausente, revocación previa y código rotado; R authorized_admin_only_after_lease_lost |
| 10 | Recuperación no autorizada | Nonce/secret/origen/Host rechazados; R resume_secret_and_admin_control y prueba administrativa |
| 11 | Timeout DeepL | Deadline/retry/backoff y riesgo de cobro registrados; R timeout_and_temporary_internet + T timeout tests |
| 12 | HTTP 429 | Retry-After/cooldown y deadline, incluso en último intento; R 429 tests |
| 13 | Auth/cuota | 401/403/456 abren circuito; rearme solo explícito para entradas futuras; R auth_and_quota_latch |
| 14 | Internet temporal | OSError → backoff → éxito y orden preservado; R timeout_and_temporary_internet |
| 15 | Respuestas fuera de orden | Buffer ordenado, duplicado ignorado y generación vieja rechazada; R out_of_order_completion + T reset |
| 16 | START duplicado | Hub rechaza segunda cadena; H operator_disconnect_marks_hub y JS operator_console |
| 17 | STOP duplicado | Una orden/EOF, segunda petición idempotente; R refresh_rotates_owner y JS reliability |
| 18 | STOP durante fallo DeepL | Plazo y resultado incompleto, rango cancelado; R stop_waiting_on_provider_is_bounded |
| 19 | Nueva sesión con tareas viejas | Generación/session_id rechaza resultados y libera worker viejo; T reset + R out_of_order_completion |
| 20 | Saturación | Cola limitada, fallos ordenados, presupuesto de completed; T bounded_queue + R completed_results_and_context_zero |
| 21 | Pausa larga legítima | 240 s de PCM silencioso sin alerta de captura/ASR; R prolonged_speaker_silence + pausas del soak |
| 22 | Varios overlays | Observadores independientes, lento expulsado; H multiple_subscribers + carga de tres lectores y uno lento |
| 23 | CLEAR durante reconexión | Snapshot posterior respeta watermark y siguiente inglés válido; O live_clear + JS renderer + soak |
| 24 | Liberación tras STOP | Workers/cola/subs liberados; R stop/provider cancellation, Chrome STOP y soak |

Pruebas adicionales: exceso de payload ASR rechazado antes de normalizar/traducir;
final WLK inesperado antes de EOF rechazado; presupuesto de texto READY antes de
solicitudes facturables, incidentes de límites con conteos y causa;
rechazo a datos de transporte inválidos/repetidos; protección de logs; journal/gap y
truncamiento UI y límites por bytes/caracteres; contexto cero sin retención accidental; una sola plaza HTTP aun si
se cancela su waiter; respuesta vacía/malformada; expiración de cola; callback de
entrega fallido aunque el proveedor haya respondido. Reconexiones JS: ocho intentos
sin snapshot, agotamiento y ningún timer tardío después de unload.

## Prueba con navegador real

`test_reliability_browser.py` ejecuta Chrome headless, un FastAPI aislado y un WLK
WebSocket falso. Chrome usa `--use-fake-device-for-media-stream` y permiso de media
falso; **no** se fuerza una política permisiva de autoplay. El popup produce PCM
real del dispositivo sintético, se recarga solo la consola, se observan más frames
con el mismo session_id y una sola conexión WLK, y STOP transmite un EOF y termina
completo. El test espera un documento nuevo, la rotación de autoridad y STOP
habilitado; no acepta como recuperación el snapshot de la página anterior.
Esto valida la frontera entre documentos/AudioContext y autorización;
no demuestra continuidad del Blue Yeti, GPU, Internet, factura DeepL o salida OBS.

La regresión de geometría Chrome conserva controles, reflow, predominio ENGLISH y
layout a 1366×768 y 1920×1080. No se rediseñó la consola.

## Sesión prolongada simulada

Generador: [benchmarks/reliability_soak.py](benchmarks/reliability_soak.py).
Artefacto numérico: [benchmarks/m7_soak_results.json](benchmarks/m7_soak_results.json).
Reloj virtual, 10 frames PCM/s, habla durante 40 s/pausa 20 s por minuto, snapshots
full cada 4 s, nuevas líneas de 18 palabras cada 8 s durante habla. SegmentManager
usa su tick de 0.1 s y configuración A; se ejecutan TranscriptState, manager,
normalizador real, engine asíncrono y Hub. Proveedor determinista de simulación,
con errores de red, auth y rearme explícito; tres lectores normales, uno lento,
desconexión/reconexión, CLEAR y pérdida temporal de heartbeat del controlador.
Jitter inyectado con semilla 7. No se utiliza el texto médico real como traducción
inglesa: la salida está marcada SIMULATED EN y nunca se proyecta a OBS de producción.

| Métrica medida | Resultado |
| --- | ---: |
| Duración virtual | 3603.304 s (60 min + 3.304 s de backoff) |
| Tiempo de ejecución con tracemalloc | 436.994 s |
| Audio simulado | 36000 frames / 115200000 bytes PCM |
| Mensajes ASR / fuentes | 901 / 300 |
| READY / integridad ordenada | 600 / **5400 de 5400 palabras**, sin pérdida ni duplicación |
| Flush reasons | 600 punctuation |
| Traducciones simuladas exitosas / fallidas | 591 / **9 fallos visibles** |
| Llamadas simuladas / retries | 608 / 16 |
| Errores permanentes / posibles solicitudes repetidas | 1 / 16 |
| Máxima profundidad de traducción | 2 (límite 32) |
| Journal máximo | 512 eventos / 599236 bytes (límites 512 / 2000000) |
| Eventos retirados del journal | 388, contados y visibles |
| Historial visual Hub máximo | 128 captions |
| Máxima cola de lectores normales | 2 eventos |
| Lectores lentos expulsados | 1 |
| Muestras de salud READY / DEGRADED | 3520 / 80 |
| Asignaciones Python trazadas al final / pico | 4766774 / 4936364 bytes (~4.55 / 4.71 MiB) |
| Tareas antes / después | 1 / 1 (la tarea del test) |
| Threads antes / después | 2 / 2 (incluye worker HTTP ya creado por otros tests) |
| Workers / cola / suscriptores después de STOP | **0 / 0 / 0** |
| Outcome final | **incomplete**, por los fallos auth inyectados |

Checkpoints a ~15/30/45/60 minutos virtuales: 2087723 / 3324655 / 4074088 /
4771424 bytes trazados, respectivamente. Journal: 225 / 450 / 512 / 512 eventos;
ASR: 9974 / 19949 / 29924 / 39899 caracteres. La retención ASR creciente está
prevista y tiene presupuesto; no se afirma memoria constante durante la sesión.

El resultado INCOMPLETO es intencional: el proveedor simulado tiene fallos auth
durante varios segmentos y esos fallos no se ocultan aunque luego se recupere.
La integridad 5400/5400 se refiere a ASR → READY; no se afirma que los segmentos
fallidos hayan sido traducidos. La ventana de retención se estabiliza, mientras el
historial ASR/cursor crece dentro de su presupuesto explícito. Las asignaciones
trazadas incluyen el harness y sus listas de comprobación; **no son RSS ni memoria
GPU/Chrome**. El worker HTTP real se prueba aparte con un opener bloqueado falso;
el soak no mide red/threads HTTP reales. No hay evidencia de tareas acumuladas bajo
esta carga, pero no se presenta como garantía de ausencia de toda fuga ni como una
conferencia física de una hora.

## Tests y repetición

**175 tests Python PASS** en 451.599 s (`logs/m7-release-tests.log`), incluidos
los 143 de baseline, 30 nuevos tests de fallos/límites y los tests adicionales de
Chrome con audio sintético y hora virtual. **Seis suites JavaScript PASS**, con
módulos frescos: las cinco anteriores y `test_reliability.cjs`. `git diff --check`
sin errores de whitespace. La última revisión de diagnóstico y texto de UI se
comprobó con **174 tests de regresión PASS** en 14.175 s
(`logs/m7-final-regression.log`), sin repetir la hora virtual ya medida.

```powershell
$env:TRANSLATION_ENABLED="0"
$env:M7_SOAK_OUTPUT="C:\live-captions\benchmarks\m7_soak_results.json"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node tests/test_operator_console.cjs
node tests/test_operator_partial.cjs
node tests/test_overlay_renderer.cjs
node tests/test_persistent_captions.cjs
node tests/test_overlay_geometry.cjs
node tests/test_reliability.cjs
# Solo carga + JSON, sin repetir todas las pruebas:
.\.venv\Scripts\python.exe -m benchmarks.reliability_soak
```

Node no está en PATH en este equipo: las seis suites se ejecutaron mediante el
runtime Node disponible en la herramienta local, limpiando cache de módulos entre
rondas. No se instaló ninguna dependencia ni se actualizó la pila ASR. El replay
completo del benchmark médico existente permanece entre las regresiones anteriores.

## Intervención manual y límites restantes

Pérdida de WLK durante LIVE, cierre de CAPTURE/navegador, suspensión del PC y reinicio
de FastAPI no tienen recuperación sin pérdida; terminar incompleto y START nuevo.
La recuperación segura de consola necesita CAPTURE abierta. Archivos administrativos
residuales tras cierre forzado se identifican por PID; no reutilizar un código viejo.
Auth/clave cambiada en `.env` requiere reinicio manual con sesión detenida; cuota/429
exige resolver el proveedor. Ocho fallos de overlay requieren recargar Browser Source.
El presupuesto predeterminado de sesión es 2 h; planificar pausas/START o configurar
límites validados según ensayo, sin podar el estado lingüístico a escondidas.

Pendiente antes de usar M7 en una conferencia: ensayo del runbook con Blue Yeti,
DeepL real y OBS físico, refresh de consola durante voz, recuperación administrativa,
CLEAR/reload de fuentes, pausa prolongada y STOP normal/incompleto. Las pruebas
usaron procesos aislados; la activación local de FastAPI fue posterior y sin sesión
activa. Se verificaron `/health` OK, `operator_recovery=1`, estado waiting, modo
persistent_rolling y DeepL configurado pero **no verificado mediante llamada real**.
Recargar Operator y Browser Source para cargar los scripts M7 antes del ensayo.
