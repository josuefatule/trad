# M7 — Reliability, Recovery & Operational Resilience

Despliegue local, un proceso FastAPI y un proceso WLK externo. No usar varios
workers de Uvicorn: autoridad, journal y CaptionHub viven en memoria. No se
recupera audio que no llegó ni se preserva una sesión tras reiniciar esos procesos.
La configuración lingüística A de M5.2 permanece intacta.

Actualización M8: el usuario confirmó la validación física M7 en su brief. Las
indicaciones históricas de "pendiente M7" al final se conservan como procedimiento;
la nueva aceptación v0.1 y la sesión real de 60–90 min están **PENDIENTES** en
[MANUAL_VALIDATION_V0_1.md](MANUAL_VALIDATION_V0_1.md). No equiparar el soak virtual
a una hora de hardware real. Baseline nuevo: [LATENCY_BASELINE_V0_1.md](LATENCY_BASELINE_V0_1.md).

## Operación normal y recuperación de consola

1. Arrancar WLK como antes y FastAPI con el micrófono detenido. Abrir `/operator`
   en Chrome/Edge y permitir ventanas emergentes de este origen.
2. Elegir Blue Yeti y pulsar START. Se abre **CAPTURE**, que posee el micrófono,
   AudioContext y único `/ws/session`. Mantener esa ventana abierta durante LIVE.
   No minimizar aplicaciones con políticas de suspensión de pestañas agresivas.
3. La consola recibe su historial mediante el endpoint local autorizado. Se puede
   recargar `/operator`: `sessionStorage` conserva un par token/secreto. Resume
   rota ambos, revoca la autorización anterior y conserva session_id, captura,
   SegmentManager y traductor. No es un START ni una traducción nueva.
   El monitor se actualiza cada 2 s: esa espera visual adicional no se añade al
   WebSocket del overlay ni a las mediciones backend de segmentación/traducción.
4. STOP en la consola envía el comando al socket de CAPTURE. CAPTURE conserva la
   barrera worklet → worker → EOF, sin enviar comandos de control a WLK. Esperar
   STOPPED antes de cerrar CAPTURE. Cerrar esa ventana durante LIVE pierde audio
   y termina la sesión **INCOMPLETA**; restaurarla exige un START nuevo.
5. Después de STOP, cerrar la ventana CAPTURE anterior antes del siguiente START.
   Tras recargar la consola su referencia a esa ventana puede perderse, pero el
   backend sigue impidiendo sesiones LIVE duplicadas.

El navegador no garantiza continuidad si se cierra todo Chrome/Edge, se suspende
Windows, se desconecta el dispositivo o se reinicia FastAPI. La recuperación de
consola cubre su refresh/cierre mientras CAPTURE sigue funcionando. La prueba con
Chrome real utiliza dispositivo sintético; validar también el hardware real.

## Propietario perdido

La consola propietaria renueva su heartbeat mediante status cada 2 s. CAPTURE no
lo renueva. Tras 15 s sin heartbeat, se informa `operator_owner_missing`; el audio
sigue procesándose. Otra pestaña con un token nuevo **no** adquiere controles.

Si la pestaña original conserva `sessionStorage`, recargarla utiliza su secreto
de recuperación. Si se perdió también ese secreto:

1. Abrir una consola nueva en **el mismo origen exacto** (localhost y 127.0.0.1 son
   orígenes distintos). Desplegar Diagnostics → Reliability / recovery.
2. Identificar el archivo `.runtime/operator-<PID>.json` indicado por esa consola.
   El PID debe ser el de este servidor FastAPI. Abrirlo localmente y copiar el
   campo `code` en el input de contraseña. No pegarlo en logs, chats o URLs.
   `python -m app.operator_admin` puede localizar el archivo; no imprime el código
   ni toma controles por su cuenta. Se ignora `.runtime/` en Git.
3. Esperar al menos 15 s desde el último heartbeat del propietario y pulsar
   RECOVER OWNER. La petición exige loopback, Host/Origin exactos, nonce válido,
   session_id vigente, propietario ausente y el secreto administrativo del proceso.
4. La operación revoca el token anterior y rota el código administrativo. La
   consola anterior pierde controles; CAPTURE sigue con el mismo socket autenticado.
   Confirmar el mismo session_id, frames crecientes y STOP disponible.

Archivo protegido con ACL del usuario de Windows y SYSTEM (0600 en POSIX),
eliminado al cerrar normalmente FastAPI. Un cierre forzado puede dejar un archivo
antiguo; usar solo el PID vigente. No exponer FastAPI a la red. Esta protección no
defiende contra código malicioso que ya se ejecuta como el mismo usuario/origen.
Un duplicado de pestaña que copie el par solo podrá rotarlo una vez: la autorización
anterior queda revocada. La pantalla puede tardar hasta un poll en reflejarlo;
las mutaciones comprueban propiedad inmediatamente en el servidor.

## Señales de salud

`/health` indica exclusivamente liveness de FastAPI. El status protegido muestra
READY, DEGRADED, DISCONNECTED, RECOVERING o ERROR por componente, `last_seen_mono`,
edades, duración, razón y contadores. Tiempos monotónicos pertenecen al proceso;
no compararlos directamente con relojes de Chrome/OBS.

| Señal | Interpretación / acción |
| --- | --- |
| `audio_frames_missing` | Más de 5 s sin PCM esperado. Comprobar CAPTURE y dispositivo. Un socket abierto no prueba captura. |
| `asr_messages_missing` | Más de 15 s sin mensajes WLK mientras llega señal PCM por encima del umbral. Comprobar WLK; no reinicia procesos. |
| `silence_or_unverified` | PCM sin energía reciente o ASR sin prueba de actividad. No se declara fallo solo por falta de palabras. |
| `overlay_no_subscribers` | No hay clientes de overlay; revisar Browser Source. Un cliente conectado no prueba salida física de OBS. |
| `translator_error` | Circuito por auth/cuota; corregir la causa antes de rearmar. |
| `translator_degraded` / `recovering` | Fallos/cola/reintentos; revisar IDs y métricas de intentos. |
| `operator_owner_missing` | Consola ausente; seguir el procedimiento anterior. |
| `stop_timeout` / `incomplete` | No asumir entrega completa. Consultar ASR final, pendientes, fallidos y rango cancelado. |

RMS sobre PCM s16le mide energía, no detecta voz ni interpreta el contenido. Su
umbral configurable no modifica WLK, VAD, SegmentManager ni normalización. Un
dispositivo que envíe ceros permanentemente es indistinguible de silencio solo con
esta señal; no se promete detectar esa avería. ASR puede ser silencioso legítimamente.
El estado configurado de DeepL no prueba Internet/autenticación: se verifican con
resultados reales y no se consumen peticiones facturables de health-check.

## WLK / red / OBS

WLK tiene hasta tres intentos **antes de enviar PCM**, con backoff exponencial,
jitter y cancelación. Cada intento tiene un plazo de conexión+handshake de 15 s.
Un STOP durante arranque impide el siguiente intento; no reanuda audio antiguo.
Si se pierde WLK durante LIVE, se cancela la cadena, se muestra INCOMPLETA y se
descartan publicaciones inconsistentes. Comprobar y arrancar WLK manualmente con
el comando del README; después realizar un nuevo START. No relanzar WLK con una
sesión activa. El envío PCM también tiene un timeout de 3 s.

El overlay conserva protocolo v3, snapshot/generación y watermark CLEAR. Hasta
ocho reconexiones consecutivas, espera inicial 500 ms, techo 10 s, jitter 75–100%.
Un snapshot válido reinicia el contador. Unload cancela temporizadores. Tras
agotarlos, restaurar FastAPI y **recargar Browser Source**. CLEAR efectuado durante
la desconexión sigue filtrando texto anterior en el snapshot; no reinicia ASR/DeepL.

## Proveedor y cola

- HTTP 401/403 (autorización) y 456 (cuota) abren un circuito: los nuevos segmentos
  quedan fallidos, ordenados y auditados sin más llamadas. REARM TRANSLATOR requiere
  propietario y origen local. Solo permite intentos futuros: no reenvía fallos ni
  cambia credenciales en memoria. Si se modifica `.env`, STOP y reinicio manual
  de FastAPI para cargarla; nunca reiniciar una sesión LIVE por detrás del operador.
- HTTP 429 y 5xx, red y timeout tienen reintentos limitados con backoff. 429 respeta
  `Retry-After` numérico en segundos; si supera el deadline no mantiene la cola
  bloqueada, falla ese segmento y establece cooldown. Respuestas vacías/malformadas
  y otros 4xx no se reintentan para esa entrada.
- Timeout por intento 8 s, un retry, deadline total por entrada 20 s, backoff base
  0.25 s/techo 2 s. Cola 32; antigüedad máxima 30 s al comenzar. Un elemento caducado
  o rechazado no aparece como traducción correcta: quedan session_id, segment_id,
  sequence, código y contadores. Una ráfaga que agota 128 resultados pendientes
  termina explícitamente la sesión incompleta para acotar el buffer de orden.
- Orden secuencial y generación de sesión se conservan. Un éxito posterior no
  borra el contador histórico de fallos. No hay reenvío automático de esos segmentos.
- `urllib` ejecuta un único socket admitido por proceso. Cancelar su waiter no
  mata el thread: conserva la plaza hasta terminar/timeout. No se acumula una cola
  HTTP entre sesiones; nuevas entradas reciben `provider_busy` con política limitada.
  La respuesta se limita a 1 MB. Se mantiene contexto lingüístico configurado.
  El timeout de urllib se aplica a operaciones del socket: DNS o una respuesta que
  gotea datos pueden prolongar el thread. El deadline libera la cola asíncrona y
  las siguientes entradas fallan visiblemente como busy, sin acumular más threads.
  Si la plaza nunca se libera, STOP y reinicio manual de FastAPI; no se promete
  matar una llamada síncrona en ejecución.
- Si una respuesta se pierde, DeepL pudo procesar y cobrar. Se registra
  `retry_may_repeat_billable_request` / `possible_in_flight_charge`; no existe una
  garantía de cobro exactamente una vez. Consultar Usage de DeepL para consumo real.

Clasificación contrastada con la [documentación oficial de errores DeepL](https://support.deepl.com/hc/en-us/articles/9773964275868-DeepL-API-error-messages)
y el [contrato oficial OpenAPI](https://github.com/DeepL/openapi/blob/main/openapi.yaml).

## Finalización y límites

STOP solo es completo después de EOF de captura, `ready_to_stop`, flush de PENDING
y resultados de traducción sin fallos. Un `ready_to_stop` inesperado antes de EOF
es un error incompleto. El relay espera hasta 120 s después de EOF. Si CAPTURE no
confirma flush en 5 s, el proxy fuerza EOF, lo cuenta y marca
INCOMPLETA. No hay STOPPING infinito. El máximo normal desde la orden es 5 s de
flush + 120 s de drain, más cierre acotado del socket. Un envío bloqueado falla
antes. Timeout deja registrado el contenido pendiente y el rango de secuencias
canceladas; no se vende como recuperación. No se conoce el número exacto de palabras
que WLK nunca entregó. Desconexión/error limpia la ventana como en M6; STOP normal
retiene persistent_rolling y la limpieza tras 8 s. CLEAR sigue siendo solo visual.

| Recurso | Predeterminado / política |
| --- | --- |
| Sesión | 7200 s; STOP controlado al alcanzar duración |
| ASR retenido/full | 300000 caracteres, 6000 fuentes, 100000 mensajes; STOP al 90% de tamaños/conteos; exceso abrupto aborta INCOMPLETA |
| READY | 12000 segmentos / 600000 caracteres; STOP al 90%, exceso abrupto incompleto |
| Mensaje WLK | 8 MB; frame PCM entrante máximo 1 MB |
| Journal autorizado | 512 eventos / 2 MB serializados; contador `journal_truncated`, bytes y `history_gap` |
| UI | Últimos 500 segmentos por flujo, con techo adicional de 60000 caracteres por flujo/panel; truncamiento contado y visible |
| Hub existente | 128 captions y 20000 caracteres totales de historial; caption individual hasta 20000; 128 muestras por historial, 32 observadores y cola 64 por observador |
| Tokens | 64, TTL 24 h; rotación de resume no aumenta el conteo |
| HTTP | Un worker y una plaza admitida, sin backlog oculto entre sesiones |
| Logs | development.log 5 MB × 4; raw opt-in 10 MB × 4; sin audio guardado |

Los límites ASR envuelven al manager sin podar su reconciliación. Esto exige una
pausa/START nuevo al llegar al presupuesto; no se finge una conferencia ilimitada.
Los objetos del manager/normalizador se liberan al terminar el relay. El journal
acotado permanece hasta el próximo START para recuperar la consola; no es archivo
persistente ni exportación completa. Revisar counters antes de empezar otra sesión.
Un evento individual mayor que el presupuesto del journal no se retiene y se
registra explícitamente. La recuperación omite huecos visuales ya contados, sin
esperar para siempre una traducción que ya salió del historial y sin reenviarla.

Variables configurables: `RELIABILITY_` seguido del campo en mayúsculas de
`ReliabilityConfig` en `app/reliability.py`; nuevas de traducción:
`TRANSLATION_RETRY_BACKOFF_SECONDS`, `TRANSLATION_RETRY_BACKOFF_MAX_SECONDS`,
`TRANSLATION_REQUEST_DEADLINE_SECONDS`, `TRANSLATION_MAX_QUEUE_AGE_SECONDS`,
`TRANSLATION_MAX_PENDING_RESULTS`. Timeout/retries/queue/context existentes conservan
sus nombres. Overlay: `CAPTION_RECONNECT_ATTEMPTS`, `CAPTION_RECONNECT_BASE_MS`,
`CAPTION_RECONNECT_MAX_MS` (también parámetros URL en minúsculas). Valores se validan;
cambiar `.env` no altera un proceso que ya está ejecutándose.

## Diagnóstico y validación manual pendiente

Logs estructurados con timestamp, componente, evento, IDs, severidad, motivo,
transiciones y duración. Texto de eventos de segmentación se reemplaza por conteos
por defecto; errores arbitrarios y secretos no se registran. `CAPTIONS_LOG_RAW=1`
es un opt-in de diagnóstico que guarda transcripciones completas: usar solo en una
sesión autorizada y volver a desactivarlo. Nunca registra audio ni credenciales.

1. Con sesión detenida, reiniciar FastAPI actualizado y recargar consola/OBS.
2. START con Blue Yeti; comprobar CAPTURE y frames/ASR crecientes, NORMALIZED/ENGLISH.
3. Recargar solo `/operator` durante voz: mismo session_id, inglés continuo, STOP/CLEAR
   disponibles y una sola cadena. Hablar antes/durante/después para detectar huecos.
4. CLEAR, cerrar/reabrir Browser Source y comprobar que no regresa texto limpiado.
5. Cerrar solo la consola, mantener CAPTURE, esperar 15 s y recuperar en otra pestaña
   con el código local. Verificar exclusividad y STOP. No probar con una conferencia.
6. STOP normal y revisar outcome completo. En sesión de prueba, detener WLK manualmente
   para comprobar aviso incompleto; restaurarlo y hacer START nuevo. No reinicio oculto.
7. Validar pausas de 30 s, varias fuentes OBS y dejar sesión de ensayo prolongada.
   Internet/DeepL real y OBS físico siguen pendientes de esta aceptación. Los tests
   automáticos no simulan el GPU, el dispositivo físico ni una factura real.
