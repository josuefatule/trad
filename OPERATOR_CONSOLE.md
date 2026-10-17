# Operator Console v1 — M6

Abrir http://localhost:8010/operator en Chrome/Edge. Mantener FastAPI en
`--host 127.0.0.1` y un solo worker. Se requieren los estáticos y el backend M6
juntos: reiniciar FastAPI **solo con la sesión detenida** y recargar Operator y
la caché de Browser Source después de actualizar. No se reinicia ni configura WLK/OBS.

## Operación

1. Permitir/actualizar micrófonos y seleccionar Blue Yeti u otro dispositivo.
2. Comprobar IDLE/STOPPED, START habilitado, proveedor configurado y clientes del
   overlay. `Configured; not verified` significa que el adaptador está configurado,
   **no** que DeepL haya aceptado credenciales o respondido. `Verified by result`
   requiere una traducción exitosa de la sesión. Mock siempre se identifica como MOCK.
3. START SESSION solicita audio y espera el handshake real de WLK antes de capturar.
   STARTING → LIVE. START duplicado se bloquea en frontend y backend. El cronómetro
   comienza al pulsar START e incluye conexión/permisos.
4. ENGLISH es el panel principal. NORMALIZED ES y RAW ES / ASR CONFIRMED se mantienen
   a la derecha, con reflow compacto y scroll interno. Si se está al final del
   historial, se sigue el texto nuevo; si se sube para revisar, se conserva la posición.
   El confirmado puede revisar su última línea; READY y las salidas derivadas no se reescriben.
5. CLEAR CAPTIONS limpia la ventana de todos los overlays sin detener el audio ni
   borrar los paneles/historiales del operador. El siguiente caption publicado
   normalmente vuelve a aparecer. Una traducción que ya estaba en curso puede ser
   ese próximo caption: CLEAR no cancela ni vuelve a traducir nada.
6. STOP SESSION hace la barrera FIFO existente worklet → worker → EOF binario.
   STOPPING espera `ready_to_stop`, READY final, normalización y drain de traducción.
   Después pasa a STOPPED. No cerrar la pestaña durante ese flush final.

START/STOP/CLEAR incompatibles con una transición quedan deshabilitados. CLEAR
sin sesión es un no-op. Si otra pestaña posee una sesión, una nueva consola no
puede iniciarla otra vez ni limpiarla; no se implementa transferencia de control.
Ante fallo del micrófono o de sesión se liberan los recursos. Corregir el problema
y usar START de nuevo; no existe reconexión automática del audio. Los fallos de
traducción ocupan su secuencia y no detienen los siguientes resultados, conforme
a la política ya existente.

## Qué verifica cada estado

- IDLE / STARTING / LIVE / STOPPING / STOPPED / ERROR reflejan el ciclo de sesión
  y las transiciones locales de permisos/captura. El rechazo del backend prevalece.
- WLK `Not checked` no es un servicio Ready. `Connected` significa que se recibió
  el handshake real de la sesión; no es una prueba de disponibilidad futura.
- El proveedor puede estar Disabled, Misconfigured, Configured, Verified by result
  o tener un error de segmento. La existencia de la API key nunca basta para Verified.
- `Overlay clients: N` cuenta WebSockets de observadores. Puede incluir OBS y
  pestañas Chrome. No se identifica OBS por user agent ni se afirma OBS conectado.
- `Overlay page: available` es una comprobación HTTP separada, realizada una vez
  al abrir la consola. Tampoco demuestra que OBS la esté mostrando.
- El micrófono seleccionado es local a esa consola. Una pestaña que observa el
  estado de otra sesión no conoce el dispositivo de aquella sesión.

## Diagnósticos y auditoría

Abrir **Diagnostics & segment audit** para ver configuración de overlay, última
publicación, latencias, colas, observadores, descartes y errores. READY RAW conserva
segment ID, tiempos y motivo; NORMALIZED conserva IDs; ENGLISH conserva IDs,
sequence y errores por segmento. CORRECTIONS/SUGGESTIONS y snapshots WLK siguen
accesibles. Debug conserva los últimos 100 eventos. No se inserta HTML procedente
de la transcripción/traducción.

Las métricas usan las muestras M5.1 existentes: ASR first appearance → READY,
READY → normalized/translation started, provider total, queue delay, traducción →
Hub y recepción/DOM/doble-rAF de cada observador. Backend y observadores se muestran
separados; no se suman medianas ni relojes incompatibles. El doble-rAF es una
estimación de pintado, no salida física de OBS. Los agregados backend existentes
provienen de publicaciones exitosas; los fallos siguen disponibles en la auditoría
de traducción. Muestras ausentes muestran `—`, no cero artificial. El cero real
de cola o una duración cuantizada a cero se conservan como datos.

Mediana/p95 aparecen desde cinco muestras numéricas válidas (configurable). p95
usa nearest rank; muestras acotadas a las 128 existentes. No hay un agregado de
varios observadores fingiendo ser una única fuente OBS. Cambiar el diagnóstico no
cambia thresholds del SegmentManager. M5.2 sigue recomendando configuración A.

Variables opcionales, validadas y leídas al arrancar FastAPI:

| Variable | Default | Rango / significado |
| --- | ---: | --- |
| OPERATOR_POLL_SECONDS | 2 | 1–10 s; un solo sondeo de estado sin solapamiento |
| OPERATOR_SUSTAINED_SECONDS | 6 | 2–120 s antes de alertar |
| OPERATOR_QUEUE_DEPTH_WARNING | 3 | 1–1000 resultados en cola |
| OPERATOR_QUEUE_DELAY_WARNING_MS | 1000 | 100–120000 ms; exige cola aún ocupada |
| OPERATOR_RENDER_WARNING_MS | 500 | 50–30000 ms; exige muestra reciente del observador |
| OPERATOR_MINIMUM_SAMPLES | 5 | 3–128 muestras para mediana/p95 |

Las alertas solo se sostienen durante LIVE/STOPPING y se reinician cuando la
condición desaparece. Las muestras de renderer vencidas no sostienen alertas.
Un mal resultado aislado no se presenta como un atraso sostenido.

## CLEAR y contrato versionado

El protocolo de Operator es **v1**, con capabilities `operator_console=1` y
`captions_clear=1`, además de las anteriores. Un frontend nuevo ante backend viejo
muestra incompatibilidad y bloquea START antes de pedir audio. El overlay pasa de
v2 a **v3** para impedir que un renderer viejo ignore CLEAR silenciosamente.

Control HTTP independiente del canal PCM:

```text
POST /api/operator/clear
Origin: mismo esquema/host/puerto que FastAPI
X-Operator-Token: nonce de esta pestaña, nunca una API key
{"protocol_version":1,"session_id":"actual","visual_generation":0}
```

El servidor comprueba propietario, sesión y generación esperada sin await entre
validación y mutación del hub. Un control viejo obtiene 409; no se reintenta
automáticamente. Sin sesión responde `applied:false`. Durante conexión o drain se
rechaza para mantener acciones compatibles con la UI.

Evento de broadcast, ordenado junto con las publicaciones:

```json
{"type":"captions_cleared","protocol_version":3,"event_id":42,
 "session_id":"actual","visual_generation":1,"sequence":12,
 "cleared_through_sequence":12}
```

Se incrementa solo la generación visual, se conserva sequence de traducción y se
vacían `last_caption`/historial visual del hub. No se llama al manager, normalizador
ni traductor. Los snapshots incluyen generación y watermark. El overlay cancela
su ventana/timers de presentación, conserva el watermark y rechaza generaciones,
snapshots, secuencias y sockets anteriores. La siguiente sequence >12 se muestra
normalmente. START nueva reinicia generación/watermark junto con el nuevo session ID.
La telemetría de una generación anterior se ignora para no presentar un paint viejo
como estado posterior a CLEAR. Los historiales RAW/NORMALIZED/ENGLISH y las métricas
backend no se borran.

## Seguridad local proporcional

`GET /api/operator/bootstrap` emite un nonce aleatorio de 256 bits, no almacenable
en caché. Solo admite peer loopback y Host local válido; si hay Origin debe coincidir.
M7 conserva token y secreto de resume en sessionStorage, sin localStorage/cookie/URL. El handshake de audio
usa subprotocolos `operator.v1` y el nonce; el servidor selecciona solo `operator.v1`.
El token no aparece en URLs/logs de acceso ni en eventos de los overlays.

`/ws/session` y POST CLEAR exigen peer loopback, Host y Origin exactos, más nonce
válido. La sesión conserva el propietario que logró abrirla; obtener otro nonce
no permite limpiar esa sesión. Las peticiones cross-origin/remote y las fuentes
Browser públicas sin autoridad no pueden mutar sesión/captions. `/ws/overlay`
continúa aceptando solo la telemetría acotada existente; un supuesto comando CLEAR
en ese socket se ignora. `GET /api/operator/status` requiere nonce y acceso local.
Los mensajes de error proyectados a UI se categorizan y sanitizan; el resultado
original no se reescribe. M7 omite contenido y secretos de los logs por defecto.

Límite: 64 nonces, caducidad 24 h o reinicio del proceso; recargar la consola si
caducan. No protege frente a un proceso malicioso **local** ni a scripts capaces
de ejecutar código en el mismo origen. No son cuentas ni permisos de red. No
publicar FastAPI con 0.0.0.0 ni usar proxy externo en esta versión. Las rutas
públicas de overlay siguen mostrando texto; localhost es parte del despliegue.

## Verificación visual y pruebas

Chrome headless verificó viewports exactos **1366×768** y **1920×1080**: controles
visibles, ENGLISH predominante, reflow, scroll interno, cabecera sticky, diagnósticos
y ausencia de scroll horizontal. Capturas generadas con fixtures, sin voz ni API:

- `logs/m6-operator-1366x768.png`
- `logs/m6-operator-1920x1080.png`

También se comprobó la página servida por FastAPI real, sin pulsar START: bootstrap
autorizado, IDLE, DeepL configurado pero no verificado, y cero clientes de overlay
después de reiniciar. Esta comprobación no consume DeepL ni comprueba voz real.

Los tests verifican estados, permisos, START duplicado, STOP/EOF, CLEAR LIVE/sin
sesión, varios overlays, snapshot/reconexión, watermark, aislamiento de sesiones,
autorización/origen/remoto, frontend/backend viejos, errores WLK/DeepL, alertas
sostenidas, datos ausentes, integridad y renderer persistent_rolling conservado.
Baseline M6: **143 tests Python y cinco suites JavaScript PASS**, sin credenciales reales.
Resultados M7 y cobertura adicional en [M7_REPORT.md](M7_REPORT.md).

```powershell
$env:TRANSLATION_ENABLED="0"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node tests/test_operator_console.cjs
node tests/test_operator_partial.cjs
node tests/test_overlay_renderer.cjs
node tests/test_persistent_captions.cjs
node tests/test_overlay_geometry.cjs
node tests/test_reliability.cjs
```

En OBS real: recargar caché, abrir Operator actualizado, START y hablar. Comprobar
inglés, pulsar CLEAR durante LIVE, confirmar que desaparece en todas las fuentes
y reaparece con la siguiente traducción; los tres historiales deben permanecer.
Cerrar/reabrir una fuente inmediatamente después de CLEAR no debe recuperar texto
anterior. STOP debe preservar el flush final. Esta aceptación con voz queda al
operador; las capturas son QA del layout, no prueba de salida física de OBS.

## M7: operación recuperable

START abre CAPTURE en una ventana dedicada (permitir popups). Mantenerla abierta
durante LIVE: es la propietaria del micrófono, no la consola. El permiso de audio
sigue siendo el del navegador para este origen. STOP en consola conserva la barrera
EOF de esa captura. Tras STOP se puede cerrar CAPTURE. No cerrar todo el navegador
ni la ventana de captura mientras se está hablando.

Recargar la consola rota automáticamente su autorización a partir del par guardado
en sessionStorage y reconstruye ASR/NORMALIZED/ENGLISH desde un journal acotado.
No abre un segundo WLK ni repite DeepL. Solo una autorización posee controles. Si
se pierde el par, abrir otra consola requiere recuperación administrativa local:
Diagnostics → Reliability / recovery, código de `.runtime/operator-<PID>.json` y
propietario sin heartbeat durante 15 s. Esa operación revoca el token anterior.

Las alertas operativas muestran falta de frames, señal sin mensajes WLK, traductor
degradado, propietario ausente, overlay sin suscriptores y STOP incompleto. Debajo,
JSON técnico con edades/última actividad, causas, pendientes y métricas. No hay
ping facturable de DeepL: Configured no prueba conectividad; un resultado sí.
Los errores auth/cuota bloquean llamadas innecesarias. REARM TRANSLATOR habilita
solo entradas futuras después de corregir la causa; nunca reenvía fallos anteriores.

La vista conserva hasta 500 segmentos y 60000 caracteres por flujo; paneles de
auditoría y ASR, 60000 caracteres. Journal de recuperación, 512 eventos y 2 MB
serializados. Los recortes están contados y
visibles; son límites del monitor y no modifican captions o segmentos publicados.
El pipeline tiene un presupuesto de duración/historial con STOP preventivo, sin
alterar configuración A. Las estadísticas no validan calidad médica.

Pérdida de WLK durante LIVE o de CAPTURE: final INCOMPLETO y nuevo START manual;
no se simula continuidad. Overlay v3 recupera su snapshot/CLEAR con hasta ocho
intentos; tras agotarlos requiere recargar Browser Source. No se reinician procesos
externos ni se ofrece persistencia tras reinicio. Procedimientos completos y ensayo
con Blue Yeti/DeepL/OBS: [RELIABILITY_RUNBOOK.md](RELIABILITY_RUNBOOK.md).
