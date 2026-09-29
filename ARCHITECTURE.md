# Arquitectura — Milestones 1 y 2

Inspección local: 24 de septiembre de 2026, **whisperlivekit 0.2.26**.
La fuente principal fue `.venv/Lib/site-packages/whisperlivekit/`, sin modificar
el paquete ni consultar implementaciones de otras versiones.

**Validación con voz real, 2026-09-29:** el comando actual usa la política
`simulstreaming` por defecto. Con idioma fijo `es`, el backend observado no expone
hipótesis parciales: los 887 snapshots de la sesión incluyeron
`buffer_transcription: ""`, aunque 831 contenían texto confirmado. No es una pérdida
en nuestro proxy. Ver [PARTIAL_INVESTIGATION.md](PARTIAL_INVESTIGATION.md) para
payloads reales, causa en el código instalado y pruebas de regresión.

## Fuentes inspeccionadas

| Archivo instalado | Evidencia relevante |
| --- | --- |
| `basic_server.py` | `websocket_endpoint`, `handle_websocket_results`, `/health` |
| `web/live_transcription.js` | apertura WebSocket, espera de config, micrófono, captura PCM y STOP |
| `web/pcm_worklet.js` | reenvío de muestras Float32 del primer canal |
| `web/recorder_worker.js` | remuestreo a 16000 Hz y conversión s16le |
| `audio_processor.py` | `process_audio`, `convert_pcm_to_float`, `handle_pcm_data`, snapshots y EOF |
| `timed_objects.py` | `FrontData.to_dict`, `Segment.to_dict`, `format_time` |
| `tokens_alignment.py` | `get_lines`, buffers de diarización y retención en modo full |

## Una conexión es una sesión independiente

`/asr` crea un **AudioProcessor nuevo por conexión**, sus colas, tareas y estado.
El motor de transcripción es compartido, pero no hay suscripción/broadcast al
audio o texto de otra conexión. Un segundo cliente no observa una sesión existente.

```text
Micrófono → navegador (/operator)
          → ws://localhost:8010/ws/session (nuestro FastAPI)
          → ws://localhost:8000/asr?mode=full&language=es (WLK)
          → nuestro proxy → TranscriptState → SegmentManager → navegador
```

Hay una conexión upstream por conexión del navegador. Nuestra app no carga modelos
ni importa WLK. WLK sigue siendo un proceso independiente. START abre una sesión
nueva y limpia el estado; no intentamos reconectar audio a una sesión perdida.
No se implementan traducción, normalización, glosarios, servicios cloud ni OBS.

## Protocolo WLK real

### Apertura

El frontend incluido abre `/asr`, sin enviar un JSON de configuración inicial.
El servidor lee parámetros de consulta: `language`, `mode` (predeterminado `full`)
y `target_language`. Existe `mode=diff`, pero no lo usamos. Nuestra app fija
`mode=full`, pasa `language=es` por defecto y elimina `target_language` de su URL.
Si el servidor tiene autenticación configurada, acepta token en consulta o Bearer;
el comando de desarrollo de este proyecto no la activa.

WLK responde primero:

```json
{"type":"config","useAudioWorklet":true,"mode":"full"}
```

`useAudioWorklet` proviene de `--pcm-input`. Nuestro proxy exige `true` y `full`
antes de autorizar la captura. Los parámetros de sesión inválidos pueden producir
`{"type":"error","error":"..."}` y cierre 4400 (4401 para autenticación inválida).

### Navegador → WLK

- Frames WebSocket **binarios**, PCM signed 16-bit little-endian, mono, **16000 Hz**.
- Sin cabecera WAV, sin contenedor WebM, sin base64, sin timestamps en el frame.
- El AudioContext usa su frecuencia real; el worklet copia el primer canal como
  Float32. El worker instalado remuestrea cada bloque por promedios y convierte
  las muestras limitadas a [-1, 1] a Int16 LE (negativos ×32768, positivos ×32767).
- El frontend envía cada bloque convertido como un mensaje, sin un tamaño de
  frame contractual fijo. El servidor acumula bytes y procesa muestras completas.
- `AudioProcessor` usa 16000 Hz y `np.int16 / 32768.0` para convertir a float.
- **Un frame binario de longitud cero es EOF**, no silencio ni un keepalive.
  El servidor vacía PCM pendiente y señaliza fin de entrada.
- No se envían mensajes JSON `start`/`stop` a `/asr`: el bucle usa `receive_bytes()`.

Los dos módulos de audio en `app/static/` se basan en los archivos instalados,
con la conversión de muestras conservada exactamente. Se añadió una barrera
de cierre: detener el reenvío del worklet, drenar sus mensajes y los del worker,
y después enviar EOF. Así ningún PCM ya encolado se envía después del fin.
La licencia del código reutilizado está en `third_party/WhisperLiveKit-LICENSE.txt`.

**Limitación heredada:** el remuestreo redondea la longitud por bloque y no conserva
fase entre bloques; no es un remuestreador de alta fidelidad. Se mantiene por
compatibilidad con el frontend instalado y debe evaluarse en pruebas largas.

### WLK → navegador: snapshots completos

Los resultados normales no tienen `type`; se serializan desde `FrontData`:

```json
{
  "status": "active_transcription",
  "lines": [
    {"speaker":1,"text":"La hipertensión","start":"0:00:00.40","end":"0:00:01.80"}
  ],
  "buffer_transcription": "arterial",
  "buffer_diarization": "",
  "buffer_translation": "",
  "remaining_time_transcription": 0.0,
  "remaining_time_transcription_processing": 0.0,
  "remaining_time_transcription_policy": 0.0,
  "remaining_time_diarization": 0.0
}
```

Este es un ejemplo de texto con la forma real del serializador, no una grabación
de voz. La prueba local real con silencio recibió `status=no_audio_detected`,
buffers vacíos y los mismos campos de tiempos. También existe `status=error`
con `error` opcional. Los campos `remaining_time_*` son medidas de demora,
no timestamps de palabras.

- `lines`: historial de tokens confirmados, agrupados en segmentos. La última
  línea puede crecer en el siguiente snapshot; no es un evento «frase final».
- `buffer_transcription`: hipótesis inestable; **reemplazar**, nunca acumular.
- `buffer_diarization`: tokens confirmados por ASR pendientes de atribuir a un
  hablante. Se conservan como texto confirmado sin timestamps inventados y se
  exponen por separado en el estado. Normalmente vacío con nuestro comando.
- `speaker=-2` representa silencio, conservado en segmentos pero excluido del texto.
  Sin diarización, el serializador transforma el speaker interno -1 a 1.
- `start` / `end`: strings **H:MM:SS.cc**, relativos al audio de la sesión, con
  precisión de centésimas. No son hora de pared. Se conservan exactamente.
- Puede aparecer `detected_language` y, si se activa traducción en WLK,
  `translation`. No se usa traducción en esta aplicación.
- No hay IDs estables ni flag `is_final` por línea en este modo.

Al finalizar el generador, WLK envía `{"type":"ready_to_stop"}`. Hay que esperar
ese mensaje y los snapshots anteriores antes de cerrar. No se promueve la última
hipótesis a confirmado por cuenta propia. El servidor no necesariamente cierra
el WebSocket por sí solo; nuestro proxy lo cierra tras entregar el estado stopped.

## TranscriptState y ausencia de duplicación

Cada snapshot reemplaza `segments`, `partial_text` y `confirmed_text`. El texto
confirmado se reconstruye desde las líneas no silenciosas y el buffer de
diarización. Recibir dos veces el mismo snapshot no agrega nada. Una línea que
pasa de «La hipertensión» a «La hipertensión arterial» sustituye la anterior.
Una repetición genuina en segmentos diferentes se conserva.

En WLK instalado, el modo full mantiene todo el historial por defecto. No iniciar
WLK con una retención positiva que recorte ese historial: nuestro estado no intenta
recuperar segmentos que WLK haya eliminado. El coste en memoria y tamaño de los
mensajes crece con la duración de la sesión; evaluar `diff` corresponde a otro hito.

## Protocolo propio y operación

`GET /health` comprueba vida de nuestra app, no disponibilidad de WLK.
`GET /operator` y `/static/*` sirven la interfaz. `WS /ws/session` acepta solo
PCM binario y EOF, reenviados sin transformación. Envía objetos JSON:

| type | Contenido |
| --- | --- |
| `status` | `state=connecting` y `session_id`; al acabar, `state=stopped` |
| `config` | `state=connected`, `session_id`, `sample_rate=16000`, config original en `wlk` |
| `asr` | mensaje original decodificado en `payload`, estado derivado en `transcript` |
| `error` | `message` legible; después se cierra la sesión |

Errores de conexión, modo incompatible, errores ASR y timeout de finalización son
visibles. Una desconexión antes de `ready_to_stop` se señala como posible pérdida
del final. Al cerrar, se cancelan tareas y se cierra la conexión upstream.
El navegador libera pistas, AudioContext y worker al terminar o fallar.

`logs/development.log` registra eventos con ID de sesión. `CAPTIONS_LOG_RAW=1`
habilita `logs/wlk-raw.log`: timestamp, sesión y mensaje de texto original dentro
de `raw` (escapado JSON reversible). Los archivos rotan; **no se guarda audio**.
El debug de pantalla conserva los últimos 100 eventos, no todo el payload.

La configuración usa variables de entorno, documentadas en README. Se mantiene
la estructura sugerida y se añaden dos archivos de audio necesarios para AudioWorklet
y Worker. Ninguna dependencia ni versión del motor ASR fue modificada.

## Milestone 2: Segment Manager

`TranscriptState` y CONFIRMED no cambian. Un `SegmentManager` nuevo por conexión
consume exclusivamente `segments` (snapshot completo de `lines`). No utiliza
`buffer_transcription` ni inventa parciales. El flujo es:

```text
WLK → TranscriptState.confirmed_text / segments
    → SegmentManager.pending_segment
    → nuevos CaptionSegment inmutables → UI de desarrollo
```

### Reconciliación basada en evidencia

La sesión real `8ac73eec87da` tuvo 887 snapshots y 60 cambios en `lines`: una línea
de voz mantuvo inicio `0:00:02.58`, mientras fin y texto crecían, incluso dentro
de palabras. `benchmarks/medical_real_snapshots.json` conserva esos 60 payloads
y EOF con los tiempos de recepción originales.

Cada línea se asocia a una fuente por timestamp de inicio y ocurrencia ordenada,
no por texto ni hablante. Si falta el tiempo o hay retiming, se usa la posición
anterior y solapamiento temporal cuando ambos intervalos existen. Cada fuente
mantiene texto observado, cursor de caracteres consumidos, IDs publicados y tiempos
de primera aparición/último cambio por carácter. Cada snapshot reemplaza su cola
pendiente; las zonas idénticas preservan sus tiempos mediante prefijo y sufijo
**exactos**. No hay fuzzy matching ni `replace` de texto previo. Los snapshots
repetidos no generan contenido ni reinician estabilidad. Extender el final no
reinicia la estabilidad de una frase anterior idéntica.

Una revisión del contenido consumido genera `late_revision_detected` con old/new
text, timestamps e IDs afectados. El cursor se mapea por el intervalo cambiado
delimitado por prefijo/sufijo exactos. Si ese cambio cruza la frontera publicada,
se excluye de pending la región revisada ambigua y se conserva el sufijo posterior
idéntico; se registra `boundary_crossed`. Esta política evita republicar el pasado,
pero puede omitir texto nuevo ambiguo. READY no cambia. Extender un token ya emitido
(`arter` → `arterial`) también se registra; no se publica `ial` como otra unidad.

El retiming y la desaparición de líneas publicadas se registran. Una división exacta
de una línea totalmente consumida se reconoce si el texto nuevo aparece una sola
vez en el anterior y su intervalo está contenido en él. Las repeticiones genuinas
en tiempos distintos se conservan. Fusiones/divisiones arbitrarias con cambios
simultáneos de texto y tiempos o timestamps reutilizados siguen siendo ambiguas
sin IDs/token times; no se promete reconciliación general de esos casos no observados.

### Reglas, relojes y configuración

Los timestamps del audio sirven para intervalos/pausas; el reloj monotónico de
recepción sirve para estabilidad, edad y latencia. Valores iniciales configurables:

| Regla | Condición |
| --- | --- |
| `punctuation` | primer `.?!` seguido de espacio o fin, candidato estable 0,8 s |
| `silence` | silencio explícito `speaker=-2` o gap entre líneas ≥1,0 s; candidato estable y con ≥6 palabras, salvo puntuación fuerte |
| `target_words` | desde 16 palabras, coma, punto y coma o dos puntos estable después del mínimo de 6 |
| `max_words` | 24 palabras pendientes; límite fuerte y corte seguro cerca del objetivo de 16 |
| `soft_max_age` | edad ≥4,5 s, ≥6 palabras y límite débil estable; si no existe, sigue pendiente |
| `hard_max_age` | edad ≥7,0 s; corte seguro que garantiza progreso sin dividir tokens |
| `session_end` | `ready_to_stop` de WLK; vaciar pendiente sin esperar estabilidad |

Puntuación/pausa no saltan el máximo de palabras si hay un corte seguro. Los cortes
prefieren la última coma, punto y coma o dos puntos antes del objetivo; si no, usan
whitespace. Conservan la palabra terminal sin whitespace cuando ya existe un límite
anterior, pues WLK puede completarla o añadirle puntuación. Nunca dividen palabras
técnicas. `soft_max_age` no crea fragmentos por sí solo antes del mínimo;
`hard_max_age` y `max_words` son límites fuertes. Si solo existe una palabra abierta,
la edad dura la publica completa para garantizar progreso. El flush de EOF puede
superar el máximo si recibió mucho texto final.

Un decimal como `3.5` no cierra frase. No hay analizador de abreviaturas ni sintaxis;
`Dr.` puede cerrar un candidato. READY significa estable según estas reglas de
desarrollo, no una garantía gramatical/médica. El benchmark mostró que la causa de
la fragmentación era la edad única de 2,8 s sin mínimo: produjo 21 de sus 25 cortes.
Con edad blanda/dura separadas y mínimo explícito genera 10 segmentos.

Un solo bucle de descarga atiende WLK y ticks de 100 ms; mantiene el recv pendiente
sin cancelarlo en cada tick. Puede publicar aunque no llegue otro snapshot.
**Inactividad de red no es silencio.** STOP envía EOF y espera `ready_to_stop`;
`finish()` publica lo restante antes de `status=stopped`. START crea manager/IDs nuevos.

### Datos y protocolo

`CaptionSegment` es frozen: `id`, `text`, `start_time`, `end_time`, `emitted_at`,
`reason`, `first_seen_at`, `latency_ms`, `word_count`, `revisions_before_ready`,
`source_ids`, `timing_precision`.

`start_time`/`end_time` son límites de las líneas de origen en segundos de audio,
**no tiempos exactos de cada subsegmento**. Varios cortes de una línea comparten
inicio y pueden solaparse; se indica en UI y como `timing_precision=source_line_bounds`.
No se inventan timestamps por palabra; datos ausentes son null. `emitted_at` y
`first_seen_at` son segundos monotónicos desde el inicio del manager; `latency_ms`
mide primera aparición del contenido conservado → READY, no captura → ASR.

Los mensajes `type=asr` conservan payload/transcript de M1 y añaden `segmentation`:

```json
{"confirmed_text":"texto ASR completo","pending_segment":"cola pendiente","ready_segments":[],"events":[]}
```

`ready_segments` contiene **solo emisiones nuevas de la llamada**. Los ticks envían
`type=segmentation` con esa misma propiedad, sin fabricar un mensaje ASR. La UI
reemplaza PENDING y agrega READY por ID; START limpia paneles e IDs. El manager
también conserva el historial inmutable durante la sesión.

Logs: `segment_manager_reset`, `segment_pending_updated` solo cuando cambia,
`segment_ready` con `flush_reason`/métricas, y `late_revision_detected`.
`revisions_before_ready` cuenta sustituciones del pendiente desde la emisión anterior,
no simples extensiones ni snapshots repetidos; es una métrica de ventana pendiente,
no un contador de correcciones por palabra. Late revisions se cuentan por evento.
RAW continúa desactivado salvo `CAPTIONS_LOG_RAW=1`. No se guarda audio.

### Validación

Tests con reloj explícito cubren crecimiento, revisión, varias líneas, estabilidad,
pausas, cortes, EOF, reset, timestamps, inmutabilidad y late revisions. Replay real:
10 segmentos, cero late revisions y sus 81 palabras finales en orden sin duplicación.
Integración FastAPI + WLK simulado reproduce payloads reales y dos sesiones completas.
Smoke con WLK real y PCM de silencio valida transporte/cierre. La prueba final de
segmentación con Blue Yeti queda al usuario. Sin traducción, normalización ni cambios ASR.
