# Milestone 1: protocolo y arquitectura

Inspección local: 24 de septiembre de 2026, **whisperlivekit 0.2.26**.
La fuente principal fue `.venv/Lib/site-packages/whisperlivekit/`, sin modificar
el paquete ni consultar implementaciones de otras versiones.

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
          → nuestro proxy → TranscriptState → navegador
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
