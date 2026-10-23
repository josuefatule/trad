# M5-B — transporte Turbo experimental

## Revisión M5-B2: crédito PCM y diagnóstico por fase

No arrancar servidores ni repetir E2E sin autorización posterior del plan nuevo.
La copia histórica y sus resultados no se modifican. El modelo, perfil M5-A,
TranscriptState, SegmentManager y sus parámetros permanecen intactos.

`flow.py` limita a **un frame de hasta 64000 bytes pendiente** entre TRAD y
Turbo. El backend negocia `pcm_credit=1` en config y devuelve `pcm_ack` con
sesión, secuencia, bytes acumulados y SHA del bloque después de procesarlo.
El consumidor serial de TRAD lee ese crédito después de entregar los snapshots
anteriores. Solo entonces se recibe otro PCM y se notifica crédito al CAPTURE.
No son votos LA2 ni confirmaciones clínicas. Un crédito duplicado, ajeno o con
hash incorrecto invalida el flujo; no existe fallback al envío acelerado anterior.

El CAPTURE de archivo verifica el mismo manifiesto y ahora espera crédito por
bloque. La opción predeterminada **Tiempo real** no ofrece un bloque antes de
su instante de disponibilidad a 32000 bytes/s. La opción acelerada sigue
respetando el crédito: no mide latencia LIVE. No se ha ensayado por TCP esta
revisión. El cliente con crédito requiere Turbo; el rollback WLK de protocolo
se comprueba en memoria, y para un rollback de navegador debe utilizarse la
revisión histórica compatible, preparada en otro directorio/runtime nuevo.

Los plazos existentes no aumentan: envío TRAD 3 s, entrega al navegador 2 s,
decoder 30 s, salida backend 5 s y drenaje EOF 120 s. La espera nueva de crédito
es un plazo **compuesto** de decoder + salida backend + entrega al navegador
(37 s); el cliente añade los 2 s de notificación de crédito (39 s). La espera
de crédito ocurre antes de recibir el siguiente bloque, fuera del plazo de
escritura de socket. Los tests pueden escalar sus plazos sin cambiar los defaults.

`transport.jsonl` del backend registra admisión, decoder y producción/envío de
snapshots. El log privado `operational_logs/transport/<sesión>.jsonl` registra
las esperas y entrega en TRAD con `perf_counter_ns`. Solo metadata, máximo 8 MiB
por sesión para este último; se mantienen los límites de PCM, JSON, colas y
tiempo del backend. Los resúmenes distinguen producido, envío ASGI retornado,
recibido y entregado al navegador. Un envío ASGI no acredita recepción o pintado.
RAW y ASR conservan contenido no entregado; una interrupción nunca se convierte
en cierre completo. Un native call cancelado sigue en cuarentena hasta terminar.

`prepare.py` instala las clasificaciones por fase y sus mensajes solo en la
**copia nueva**. Un timeout de streaming no se muestra como STOP solicitado.
La cola EOF se marca no evaluada mientras no haya terminal; nunca se confirma
artificialmente. Los campos clínicos y los timestamps ASR no cambian.

Controles adicionales sin servicios, desde la raíz y después desde la copia:

```powershell
.\.venv-wlk\Scripts\python.exe -m unittest trad_lab.m5b.test_flow -v
& 'C:\Program Files\nodejs\node.exe' trad_lab/m5b/test_flow.cjs
# Solo desde la copia experimental, sin TCP/GPU:
C:\live-captions\.venv-wlk\Scripts\python.exe -m trad_lab.m5b.check_failures --out DIRECTORIO_NUEVO
```

El control de cuatro PCM usa palabras ya registradas de M5-A para verificar
ventanas y entrega; no es otra inferencia ni una medida clínica. La comparación
de consumidor lento se conserva separada del E2E histórico: demuestra un
mecanismo de congestión y su corrección en memoria, no cuál await exacto venció
en aquella conexión TCP sin instrumentación por fase.

## Procedimiento M5-B histórico

Solo laboratorio. La versión LIVE de `app/` no se edita. No se inicia ningún
servicio al importar módulos, preparar una copia o ejecutar los controles ASGI.
El arranque TCP queda pendiente de autorización humana posterior.

`transport.py` adapta ASGI `/asr?mode=full&language=en` a M5-A sin modificar el
motor, modelo o perfil. Solo loopback y cabecera de servicio privada, separada
de las credenciales del Operator. La sesión también lleva su ID autenticado.
Un único hilo/decoder y una única sesión admitida; no existe fallback automático.

Backpressure: un frame en proceso, máximo 1 MiB por frame, ocho mensajes/8 MiB
en la cola de salida más uno en envío, mensaje JSON máximo 2 MB. Servidor propuesto
con cola WS de cuatro frames. Audio máximo 230400000 bytes y trazas JSON 256 MiB
por sesión. Al superar un límite se declara fallo, nunca se descartan muestras
para presentar un resultado completo. Defaults de transporte: decoder 30 s,
envío 5 s, espera de PCM 30 s, sesión 7200 s. No son parámetros médicos/ASR.

Un timeout nativo pone el broker en cuarentena y rechaza otra sesión. No mata
una llamada CUDA ni permite otra sobre el mismo estado. El writer se cierra al
retornar esa llamada; ante un bloqueo nativo permanente se requiere revisar y
cerrar exclusivamente el proceso experimental. Un abort nativo puede dejar
evidencia parcial. No hay retry automático.

`runtime.py` añade en la copia diagnósticos autenticados y recuperables:
`transport_completion` y `transcription_completion`. La cola EOF mantiene texto
y timestamps, fuera de confirmado/PENDING/READY. CLEAR no la convierte ni reinicia
ASR. `complete` operativo no certifica una transcripción clínicamente completa.
Las alertas conocidas son metadatos de revisión, nunca prompts ni correcciones.

`prepare.py` crea directorio nuevo, sin copiar `.env` o credenciales. Copia app,
glosarios y laboratorio con hashes; aplica hooks solo a esa copia. Worklet,
resampler, TranscriptState, SegmentManager y CaptionHub quedan byte a byte iguales.
No se sobrescribe una copia congelada. Se rechazan fuentes cambiadas durante la
copia o archivos extra en el manifiesto al verificar.

La copia inicial usa CAPTURE de **archivos** con el intercambio original
`capture_ready`/`capture_start` del Operator. Se bloquea getUserMedia, no se crea
MediaStream ficticio ni se reproduce sonido. Los cuatro archivos tienen SHA
M5-A: raw s16le o WAV PCM mono 16 kHz, sin resampling. El popup permanece abierto
durante una recarga del Operator. El navegador real sigue pendiente de validación.

Controles offline (no TCP):

```powershell
.\.venv-wlk\Scripts\python.exe -m unittest trad_lab.m5b.test_transport trad_lab.m5b.test_runtime -v
& 'C:\Program Files\nodejs\node.exe' trad_lab/m5b/test_file_capture.cjs
.\.venv-wlk\Scripts\python.exe -m trad_lab.m5b.prepare --out logs/trad_lab/NUEVO/environment
# Desde NUEVO/environment/copy, usando el Python absoluto existente:
C:\live-captions\.venv-wlk\Scripts\python.exe -m trad_lab.m5b.check_copy --out C:/live-captions/logs/trad_lab/NUEVO/integration
C:\live-captions\.venv-wlk\Scripts\python.exe -m trad_lab.m5b.replay control --out C:/live-captions/logs/trad_lab/NUEVO/control
C:\live-captions\.venv-wlk\Scripts\python.exe -m trad_lab.m5b.replay gpu --out C:/live-captions/logs/trad_lab/NUEVO/gpu
```

El control reutiliza palabras de M5-A y valida sus ventanas exactas; no es una
nueva inferencia. El replay GPU reutiliza solo pesos locales y compara todos los
registros de palabras/cola con M5-A. Las referencias no entran al decoder.

`serve.py` está preparado para 18000/18010, exige plan íntegro, backend explícito
`turbo` o `wlk`, cwd de copia y la interlock CLI de autorización. La interlock no
sustituye la autorización humana. No ejecutar hasta recibirla. No hay selección
predeterminada ni posibilidad de 8000/8010. DeepL y micrófono están deshabilitados.

Rollback propuesto: STOP/EOF/cierre de ambos procesos; después seleccionar
`--backend wlk` en ambos launchers de la copia. Se comprueba el WLK original small
cacheado y su handshake; no se sustituyen paquetes ni se descargan pesos. Un
handshake que no corresponde al selector falla antes de PCM. La cola EOF del
WLK original se marca como no reportada; no se inventa una garantía de confirmación.

No hay promoción a LIVE, declaración clínica/congreso o M5-C en esta entrega.
