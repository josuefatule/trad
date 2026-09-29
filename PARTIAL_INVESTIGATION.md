# PARTIAL: investigación con voz real — 2026-09-29

## Resultado

No se pierde texto parcial dentro de nuestra aplicación. WhisperLiveKit 0.2.26,
con el comando indicado, entrega `buffer_transcription: ""` aun cuando `lines`
contiene voz reconocida. La política predeterminada es **simulstreaming**, no
LocalAgreement; `--backend faster-whisper` por sí solo no cambia esa política.
No se cambió el backend, la política, ninguna dependencia ni el procesamiento de
CONFIRMED. No se implementó una heurística de partial.

## Evidencia real

Se reinició únicamente nuestro FastAPI con `CAPTIONS_LOG_RAW=1`, manteniendo WLK
en 8000 con `--backend faster-whisper --model small --language es --pcm-input`.
Se capturó una sesión del operador con voz del usuario a través del proxy:

- Sesión: `8ac73eec87da`.
- 889 mensajes WLK: config, 887 snapshots y ready_to_stop.
- 831 snapshots contenían texto de voz en `lines`.
- Los 887 snapshots incluían `buffer_transcription`.
- **0 snapshots con `buffer_transcription` no vacío**.
- Trazas del envío al navegador: `raw_present=True raw_chars=0 state_chars=0`.
- La sesión finalizó con `ready_to_stop` y `session stopped`.
- El usuario confirmó después que el pasaje médico leído apareció en CONFIRMED
  y que PARTIAL no se mostró. El texto transcrito que compartió coincide con la
  sesión capturada. No se corrigieron sus errores de reconocimiento.

Primer snapshot con voz, completo y sin corregir ni reformular la transcripción:

```json
{
  "status": "active_transcription",
  "lines": [{
    "speaker": 1,
    "text": " La hipertensión arter",
    "start": "0:00:02.58",
    "end": "0:00:03.30",
    "detected_language": "es"
  }],
  "buffer_transcription": "",
  "buffer_diarization": "",
  "buffer_translation": "",
  "remaining_time_transcription": 0.7,
  "remaining_time_transcription_processing": 0.7,
  "remaining_time_transcription_policy": 0.7,
  "remaining_time_diarization": 0
}
```

El siguiente snapshot seleccionado amplía la misma línea hasta
` La hipertensión arterial es una condición cardiovascular`, con partial todavía
vacío. Ambos payloads exactos se conservaron en
`tests/fixtures/wlk_0_2_26_simulstreaming_es_real_voice.json`, con procedencia.
El log RAW completo permanece en `logs/wlk-raw.log`, ignorado por Git. No se guardó
audio. Tras terminar la captura, se reinició FastAPI con `CAPTIONS_LOG_RAW=0`.

## Seguimiento en el orden solicitado

1. **RAW WLK:** capturado antes de interpretar el JSON mediante el logger existente.
2. **Campo recibido:** presente y vacío en todos los snapshots, incluidos los de voz.
3. **Cliente WLK:** conserva el payload completo. No elimina `buffer_transcription`.
4. **TranscriptState:** asigna `partial_text` en cada snapshot con `lines`; no exige
   que cambien las líneas. Su comparación incluye partial, confirmed y segmentos.
5. **Publicación:** `send_json` está fuera del `if state.update(payload)`. Ese `if`
   únicamente controla un evento de logging. Todos los mensajes se publican,
   incluso snapshots idénticos y cambios exclusivamente parciales.
6. **Operador:** el handler `type=asr` asigna siempre `transcript.partial_text` a
   `#partial.textContent`. Se añadió un diagnóstico opcional con
   `/operator?trace_partial=1` que muestra RAW, estado y DOM después de asignarlo.
   Se ejecutó el handler real con DOM simulado; no se inspeccionó visualmente el
   navegador del usuario ni se presenta esa prueba como captura de micrófono.
7. **Filtro por lines:** no existe en nuestro proxy. Tampoco se introdujo uno.

## Punto de origen dentro de WLK instalado

Fuentes locales bajo `.venv/Lib/site-packages/whisperlivekit/`:

- `parse_args.py:235`: `--backend-policy` tiene default `simulstreaming`.
- `core.py:462`: esa política selecciona `SimulStreamingOnlineProcessor`.
- `simul_whisper/backend.py:52`: `self.buffer` comienza vacío.
- `simul_whisper/backend.py:227`: `process_iter()` llama a `model.infer()`.
  Solo acumula `timestamped_words` en `self.buffer` en la rama de idioma `auto`
  sin `detected_language`; esa condición no corresponde al idioma fijo `es`.
  La ruta de tokens estables vacía `self.buffer` y devuelve los tokens confirmados
  (`self.buffer = []` en la línea 259). Los tokens que no emite el decodificador
  no se exponen como una hipótesis de partial mediante esta API.
- `simul_whisper/backend.py:117`: `get_buffer()` serializa precisamente `self.buffer`.
- `audio_processor.py:757`: obtiene ese buffer después de `process_iter()` y lo
  asigna a `state.buffer_transcription`; el formateador lo convierte a string en
  `FrontData.buffer_transcription` alrededor de la línea 945.

Por tanto, con esta configuración **no se genera una hipótesis parcial expuesta
en el protocolo**. Lo confirma la sesión real; no es una deducción basada solo
en el nombre del backend ni un problema de PCM. LocalAgreement tiene otra ruta:
`local_agreement/online_asr.py:212` devuelve su buffer no validado. No se probó ni
activó esa alternativa: cambiarla puede afectar latencia y confirmación, y queda
fuera de esta corrección limitada a investigar el comportamiento actual.

## Pruebas

`python -m unittest discover -s tests -v`: **20 tests pasan**. Se añadieron cuatro:

- Estado: cambios solo en partial con líneas confirmadas idénticas, incluido borrado.
- Proxy: publicación de parciales con líneas idénticas, incluido snapshot repetido.
- Estado: los dos payloads reales conservan partial vacío y confirmed creciente.
- Proxy: replay por WebSocket de los dos payloads reales, sin perder campos.

`tests/test_operator_partial.cjs` ejecuta `operator.js` con DOM/media simulados:
verifica cambio y borrado de PARTIAL sin modificar CONFIRMED, y reproduce las dos
muestras reales. Pasó usando el runtime Node de la herramienta; si Node está en
PATH, se reproduce con `node tests/test_operator_partial.cjs`. No se instaló Node.
Los casos con partial no vacío son **sintéticos** y están identificados como tales.

PARTIAL sigue vacío con voz real bajo la configuración actual, por la limitación
de WLK descrita. CONFIRMED mantiene su comportamiento. Milestone 1 permanece como
único alcance; no se implementaron traducción ni normalización.
