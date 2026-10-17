# Arquitectura — Milestones 1–5

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
          → nuestro proxy → TranscriptState → SegmentManager
          → TerminologyNormalizer → navegador
```

Hay una conexión upstream por conexión del navegador. Nuestra app no carga modelos
ni importa WLK. WLK sigue siendo un proceso independiente. START abre una sesión
nueva y limpia el estado; no intentamos reconectar audio a una sesión perdida.
La descripción inicial de M1 aparece abajo; las capas posteriores de traducción
y overlay se documentan en las secciones M4 y M5.

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
| `asr` | `payload`, `transcript`, `segmentation` y nuevas salidas en `normalization` |
| `segmentation` | ticks que emiten READY sin un snapshot ASR nuevo, también normalizados |
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
| `silence` | silencio explícito `speaker=-2` o gap entre líneas ≥1,0 s; candidato estable y con ≥7 palabras, salvo puntuación fuerte |
| `target_words` | desde 13 palabras, buscar `safe_cut` estable hasta 8 palabras hacia atrás |
| `max_words` | 21 palabras pendientes; límite fuerte con `safe_cut` cerca del objetivo |
| `soft_max_age` | edad ≥3,3 s y ≥7 palabras pendientes; emitir solo si existe `safe_cut` estable |
| `hard_max_age` | edad ≥5,5 s; intentar `safe_cut` y garantizar progreso sin dividir tokens |
| `session_end` | `ready_to_stop` de WLK; vaciar pendiente sin esperar estabilidad |

`safe_cut` examina límites anteriores al ancla, dentro de la ventana configurable, y
prioriza: puntuación fuerte, punto y coma, coma, límite estable entre líneas WLK y
finalmente whitespace. Entre candidatos de la misma clase escoge el más cercano al
objetivo. Para edad blanda, el whitespace debe dejar al menos `minimum_words` en READY;
la puntuación o una línea útil pueden justificar un corte menor. El texto posterior
permanece en PENDING.

La palabra terminal sin whitespace se conserva cuando existe un límite anterior,
pues WLK puede completarla o añadirle puntuación. Nunca se dividen palabras técnicas.
`hard_max_age` y `max_words` son límites fuertes; si no existe un límite estable, la
edad dura garantiza progreso. El flush de EOF puede superar el máximo si recibió mucho
texto final.

Un decimal como `3.5` no cierra frase. No hay analizador de abreviaturas ni sintaxis;
`Dr.` puede cerrar un candidato. READY significa estable según estas reglas de
desarrollo, no una garantía gramatical/médica. El benchmark mostró que la causa de
la fragmentación original era la edad única de 2,8 s sin mínimo: produjo 21 de sus
25 cortes. La primera afinación bajó a 10 segmentos pero elevó la mediana a 7,04 s.
La política `safe_cut` final produce 16 segmentos con mediana de 3,83 s.

Un solo bucle de descarga atiende WLK y ticks de 100 ms; mantiene el recv pendiente
sin cancelarlo en cada tick. Puede publicar aunque no llegue otro snapshot.
**Inactividad de red no es silencio.** STOP envía EOF y espera `ready_to_stop`;
`finish()` publica lo restante antes de `status=stopped`. START crea manager/IDs nuevos.

### Datos y protocolo

`CaptionSegment` es frozen: `id`, `text`, `start_time`, `end_time`, `emitted_at`,
`reason`, `boundary_kind`, `first_seen_at`, `latency_ms`, `word_count`,
`revisions_before_ready`, `source_ids`, `timing_precision`. `boundary_kind` permite
medir cuántos cortes forzados terminaron usando whitespace.

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
16 segmentos, mediana 3,83 s, cero late revisions y sus 81 palabras finales en orden.
Integración FastAPI + WLK simulado reproduce payloads reales y dos sesiones completas.
Smoke con WLK real y PCM de silencio valida transporte/cierre. La prueba final de
segmentación con Blue Yeti queda al usuario. Sin traducción ni cambios ASR.

## Milestone 3: Terminology Normalizer

Cada `CaptionSegment` READY se procesa exactamente una vez dentro de su sesión. El
normalizador no consume PENDING ni `buffer_transcription`, y no altera el objeto READY:

```text
CaptionSegment.text (RAW ES, inmutable)
    → TerminologyNormalizer
    → NormalizedSegment(raw_text, normalized_text, corrections, suggestions)
```

Hay dos glosarios JSON cargados al abrir la conexión: una base médica y otro de
conferencia. Cada término declara forma canónica, variantes, aliases y política
`exact`, `fuzzy` o `suggest`; puede sobrescribir los umbrales generales. La carga
rechaza documentos inválidos, umbrales invertidos y formas que apuntan a dos términos
canónicos distintos.

El matching normaliza internamente Unicode, mayúsculas y diacríticos. Guiones y
espacios son equivalentes dentro de una expresión, sin absorber puntuación vecina.
Las coincidencias exactas conocidas tienen confianza 1. El fuzzy usa similitud de la
frase espaciada y compacta, más una penalización por diferencia de tokens. Se evalúa
para frases y para el caso restringido de un canónico técnico unido desde dos tokens;
una palabra ASR aislada nunca se corrige por distancia. `auto_threshold=0.90` y
`suggest_threshold=0.86`; el primero debe ser mayor. Una coincidencia fuzzy intermedia
queda como sugerencia y no cambia el texto.

Los solapamientos se resuelven de modo estable por acción, confianza, longitud,
posición y orden del glosario. Las sustituciones se aplican desde el final para que
los offsets de auditoría sigan señalando `raw_text`. `Correction` guarda fuente,
reemplazo, offsets, regla, confianza y canónico. `Suggestion` guarda candidato y los
mismos datos de decisión. `NormalizedSegment` es frozen e incluye el tiempo de proceso.

El normalizador conserva las últimas ocho palabras RAW del segmento previo. Si una
coincidencia cruza la frontera, emite `cross_segment_glossary_*` con ambos IDs como
sugerencia. Nunca modifica el segmento previo ni une silenciosamente dos READY. Un
normalizador nuevo por conexión y `reset()` impiden que el contexto pase entre sesiones.

Los mensajes `asr` y `segmentation` añaden en paralelo:

```json
{
  "normalization": {
    "segments": [{
      "segment_id": "sesión:3",
      "raw_text": "arterial systólica y/o diastólica.",
      "normalized_text": "arterial sistólica y/o diastólica.",
      "corrections": [{
        "source": "systólica", "replacement": "sistólica",
        "start": 9, "end": 18, "rule": "exact_variant",
        "confidence": 1.0, "canonical": "sistólica"
      }],
      "suggestions": [],
      "known_terms": ["sistólica"],
      "processing_ms": 6.5
    }]
  }
}
```

El mensaje inicial `config` declara
`capabilities.terminology_normalizer=1`. El operador exige esa capability y un objeto
normalizado para cada READY. Esto detecta procesos FastAPI antiguos: los estáticos se
leen desde disco en cada request, mientras los módulos Python permanecen importados en
memoria hasta reiniciar el servidor.

La UI agrega RAW y NORMALIZED por el mismo ID y muestra la auditoría. El replay usa
la ruta de producción y conserva las métricas de segmentación. Sobre los 16 READY del
fixture médico con la configuración local actual: 3 correcciones, 1 sugerencia y 13 segmentos sin
cambios y ninguna corrección falsa conocida. `Suficio` queda como sugerencia y
`pertenecios` permanece intacto; en particular no existe una regla que convierta
este último en `hipertensos`. Las pruebas negativas fijan `renal ≠ renina`, `arterial ≠ arteria`,
`tensión ≠ hipertensión` y bloquean expansiones arbitrarias de `receptor`.

El perfil reproducible de 1.600 segmentos medidos tras Milestone 3.1 dio 25,867 ms
de mediana, 53,079 ms p95 y 72,956 ms máximo en este equipo. La mediana sigue por
debajo del 1 % de la latencia mediana READY del benchmark (3,826 s). Los tiempos
dependen del equipo y del tamaño
del glosario; el algoritmo actual recorre términos y ventanas, por lo que un glosario
mucho mayor requerirá indexación antes de producción.

### Afinación Milestone 3.1

El fuzzy de una palabra ASR contra todo el glosario sigue deshabilitado. Para corregir
separaciones del reconocedor, una entrada técnica canónica de una palabra con política
fuzzy puede comparar contra exactamente dos tokens. El canónico debe tener al menos
10 caracteres. Se usa evidencia compactada y Jaro-Winkler cuando el ASR produjo más
tokens que el canónico; una distancia compactada de hasta una edición satisface el
umbral auto. Ambos límites son configurables. Las ventanas nunca omiten tokens que el
canónico requiere, lo cual evita sugerencias como `angiotensina → angiotensina II`.

Los cruces entre segmentos requieren contenido léxico a ambos lados y omiten formas
canónicas que ya son idénticas. Siguen siendo solo sugerencias. El matching exacto no
participa en fuzzy: únicamente reconoce canónicos, variantes y aliases configurados.

Después de las sustituciones terminológicas se aplican ediciones de espaciado basadas
en offsets RAW: colapsar whitespace, retirarlo antes de puntuación y añadirlo después
de `,;:!?` si sigue una letra. Estas ediciones tienen regla `deterministic_spacing`,
confianza 1 y `canonical=null`. No se añaden signos ni reglas gramaticales.

## Milestone 4: Translation Engine ES → EN

La traducción consume exclusivamente `NormalizedSegment` correspondientes a READY:

```text
CaptionSegment RAW (inmutable) + NormalizedSegment (inmutable)
    → TranslationRequest + hasta N context_segments NORMALIZED
    → queue acotada → TranslatorProvider.translate()
    → TranslationResult → mensaje WebSocket translation → ENGLISH
```

`TranslationRequest` conserva `session_id`, `segment_id`, `sequence`, RAW,
NORMALIZED, idiomas, contexto y tiempos disponibles. `TranslationResult` añade
texto traducido, provider, éxito/error, intentos, timestamps, latencia del provider
y demora en cola. El traductor nunca escribe sobre RAW ni NORMALIZED.

### Contexto y providers

La ventana predeterminada contiene los dos NORMALIZED inmediatamente anteriores.
El segmento actual nunca forma parte de su propio contexto. El provider recibe el
contexto como dato separado y debe devolver solamente la traducción del segmento
actual. El mock cumple este contrato de forma determinística y etiqueta toda salida
con `[MOCK EN]`.

`TranslatorProvider` es abstracto. El adaptador real preparado es DeepL, aislado en
`providers.py`; usa `/v2/translate`, coloca el segmento actual en `text` y concatena
la ventana previa en el parámetro `context`. No hay credenciales en el repositorio.
Provider ausente o incompleto produce estados `disabled` o `misconfigured`; ninguna
salida española se copia a ENGLISH.

### Ordering, backpressure y fallos

Cada sesión crea un engine y un único worker. `submit()` solo valida y hace
`put_nowait`, por lo que recepción WLK, audio, SegmentManager y normalización no
esperan la red del provider. El worker procesa secuencialmente y un buffer de
resultados publica únicamente la siguiente `sequence`; un error ocupa su posición
y no bloquea segmentos posteriores.

La cola tiene tamaño máximo configurable. Se registran `translation_queue_depth`,
máximo observado y `translation_queue_delay_ms`. Un desborde genera un resultado
fallido `translation_queue_full` en su orden, sin espera infinita. Cada intento tiene
timeout y el número de retries es finito. Se registran `translation_queued`,
`translation_started`, `translation_completed`, `translation_timeout`,
`translation_retry`, `translation_failed`, `translation_discarded_stale_session` y
`translation_engine_reset` con sesión y segmento cuando corresponde.

START crea otra sesión, contexto, cola, secuencia y estado DOM. El engine también
expone `reset(session_id)`: incrementa una generación y cancela el worker anterior.
Cualquier finalización tardía cuyo `session_id` o generación ya no coincide se
descarta antes del callback.

### Protocolo y tiempos

El handshake declara `capabilities.translation_engine=1`,
`capabilities.translation_provider` y `translation_status`. Cada resultado viaja en
un mensaje `type=translation` separado con su snapshot de métricas. El navegador
valida `session_id`, vuelve a ordenar por sequence como segunda defensa y avanza aun
si una secuencia falló.

Se propagan `first_seen_at` y `emitted_at` de SegmentManager, el tiempo de proceso del
normalizador, y timestamps wall-clock de queued/started/completed. Queue delay y
translation latency sí son medidas directas. Todavía no existe un reloj absoluto
común entre el primer audio, WLK y todos los stages; por eso no se publica como exacta
la métrica speech onset → English. `first_seen_at → READY` tampoco incluye captura →
primera hipótesis ASR. Unificar ese reloj queda para instrumentación futura.

El replay usa el engine de producción, mock por defecto, y no lee
`benchmarks/medical_reference_en.txt`. Esa referencia humana está separada y sirve
solo para evaluación posterior. Como el replay comprime 58,3 segundos de eventos en
tiempo de CPU, su queue delay mide esa ejecución acelerada y no predice la cola de
una sesión en vivo.

## Milestone 5: Session Caption Hub y overlay (política original timed_queue)

```text
Operator → /ws/session → WLK → TranscriptState → SegmentManager
    → TerminologyNormalizer → TranslationEngine → TranslationResult
        ├→ Operator (protocolo M4 conservado + capability caption_overlay=1)
        └→ CaptionHub → /ws/overlay → uno o varios overlays /overlay
```

El hub pertenece a una instancia FastAPI y un event loop. Admite una sola sesión
productora activa: un START concurrente se rechaza antes de conectar WLK y no cambia
el estado del productor. El callback del engine publica una proyección sanitizada
de cada resultado antes de enviar la respuesta al Operator. Hub.publish no tiene
await: un observador jamás bloquea audio o traducción. No se comparten RAW,
NORMALIZED, mensajes de error del provider ni configuración sensible con overlays.

Se eligió WebSocket dedicado para reutilizar el servidor existente, detectar cierre
de observadores y aceptar únicamente telemetría validada de descartes. No acepta
audio, start, stop, traducciones ni cambios de estado desde observadores.

### Contrato v1 y memoria

Al conectar, /ws/overlay recibe un snapshot con `protocol_version=1`, `event_id`,
`session_id`, `state`, última `sequence`, estado del traductor, `server_time` y
`caption` vigente o null. Registro del suscriptor y encolado del snapshot ocurren
sin await; los siguientes eventos quedan después del snapshot, sin carrera.

Eventos incrementales: `session` (connecting/live/draining/stopped/disconnected/error),
`caption` (session_id, sequence, segment_id, text, provider, published_at, expires_at)
y `translator` (error/mock_filtered/invalid_caption). Nunca se transporta el error
privado del provider. Sequence avanza también ante fallos y resultados mock para que
el siguiente resultado real conserve su orden. Gaps inesperados se rechazan y se
registran; duplicados y sesiones stale se descartan.

Límites: 32 observadores; 64 eventos por observador; solo el último caption retenido,
máximo 20.000 caracteres; timeout de envío 2 s. Cola llena elimina al suscriptor y
cierra su socket; la reconexión recibe estado vigente, no historial acumulado. Se
cuentan broadcast_errors. No se promete entrega completa a observadores desconectados.

Snapshot caption caduca max_display_ms después de publicación y se excluye si el
estado ya no admite texto. El JS conserva la secuencia aceptada durante reconexiones
y no repite una entrega ya aceptada, incluso si fue interrumpida. Una página nueva
puede mostrar el último caption aún vigente. No se reenvían históricos: se prefiere
recuperar el presente. El reloj de expiración del cliente usa expires_at-server_time,
evitando depender de que su reloj absoluto esté sincronizado.

### Unidad de traducción frente a unidad visible

TranslationResult sigue siendo inmutable y no se vuelve a traducir. CaptionRenderer
genera VisibleCaption {text, fontSize, duration, queuedAt, deadline} por paginación
de palabras y medición Canvas de la misma Arial 600 usada en CSS. Cada bloque tiene
hasta max_lines líneas calculadas, no line-clamp. Una palabra indivisible demasiado
ancha ocupa su propio bloque con fuente reducida; si requeriría menos de 8 px se
rechaza explícitamente todo el caption (`unreadable_token`). No se corta un token.

La cola visual es distinta de TranslationQueue. Duración = palabras / reading_wps,
acotada a min/max. Se mantiene el caption actual hasta completar su lectura y se
reemplaza directamente por el siguiente. Al vaciarse queda totalmente invisible.
No hay toolbar ni datos técnicos en el overlay público; se usa textContent.

La cola limita frames y atraso estimado; elimina los más antiguos aún no mostrados
si supera 64 frames o 20 s, preservando el bloque en lectura. También vence frames
con más de 20 s de espera. El compromiso es omitir texto durante sobrecarga para no
mostrar discurso antiguo indefinidamente. Cada decisión emite overlay_display_drop
en consola y telemetría acotada al backend; Operator muestra el contador. Resize
limpia medidas antiguas y reporta el descarte, evitando ocultar palabras por clipping.

### Ciclo de vida y límites operativos

EOF marca draining. Se espera ready_to_stop, se normaliza/traduce lo pendiente y
después se publica stopped. Los overlays ya conectados terminan la cola visual
dentro de sus límites y se limpian. START nueva borra todo inmediatamente. Un error
del provider no finaliza audio ni borra la cola en lectura; el siguiente English
correcto puede mostrarse. Cerrar el Operator durante captura cancela upstream y
traducciones; se publica disconnected y se limpia. Si ya se aceptó EOF, la política
existente termina el drain; el overlay nunca se marca live después de STOP.

La demo /overlay/preview usa fixtures English locales con aviso DEMO permanente,
sin socket productivo, micrófono ni API. El hub y renderer públicos filtran provider
mock y prefijos [MOCK]. Diagnósticos de conexión/estado/último caption/errores quedan
en /api/overlay/status y Operator; config visual pública en /api/overlay/config.

Un solo proceso Uvicorn y acceso localhost son requisitos de esta versión. Varios
workers necesitarían un hub externo compartido. No hay autenticación ni aislamiento
de espectadores en red; mantener --host 127.0.0.1. No se modifica OBS ni se crean
overlays de otros idiomas. La validación de UI real en OBS queda pendiente.

## M5.1: persistent_rolling y trazabilidad temporal

El usuario validó M5 en OBS con WLK y DeepL. La política temporal original de M5
queda disponible como timed_queue; M5.1 sustituye el predeterminado por
persistent_rolling y eleva max_lines a 3 (configurable a 2).

Retención y orden son independientes. Cada caption nuevo se acepta una vez y se
añade inmediatamente a los tokens visibles. Canvas mide reflow de palabras sobre
la cola retenida; salen las líneas más antiguas hasta caber en la ventana. No hay
espera por min_display_ms ni TranslationQueue adicional. No se inventan signos ni
se insertan saltos por READY. Durante LIVE no hay timer de desaparición.
STOP (después del drain del engine) programa stop_clear_ms=8000. START y desconexión
limpian; resize refluye tokens actuales. Rolling normal y texto nuevo demasiado
largo que sale sin verse se distinguen mediante rolled_out_lines y rolling_overflow.

Hub conserva hasta 128 captions / 20.000 caracteres por sesión. Snapshot LIVE no
caduca por inactividad; STOP caduca según configuración backend. Restauración
reconstruye la ventana y mantiene el watermark de secuencia, sin concatenarla dos
veces. Los límites de memoria y evicción de observadores de M5 se mantienen.

### Relojes y métricas

SegmentManager expone únicamente su monotonic_origin para anclar first_seen_at y
emitted_at. No cambia ninguna decisión. El proxy registra fin de normalización.
TranslationRequest/Result añaden TranslationTiming frozen con queued/start/end
monotónicos y duraciones de intentos del provider. Hub mide publicación con ese
mismo reloj y conserva 128 muestras numéricas. Campos wall-clock de M4 siguen
presentes para compatibilidad, pero no calculan las nuevas duraciones.

El protocolo overlay sube a v2; capabilities existentes se conservan y se añaden
persistent_captions=1 y caption_latency=1. El socket permite clock_probe/clock_sync:
cuatro timestamps estiman offset y RTT sin mezclar procesos arbitrariamente. La
muestra reciente de menor RTT se utiliza hasta 30 s; la incertidumbre indicada es
RTT de red/2 más resolución backend y no incluye deriva/asimetría no observables. Las respuestas de reloj
y broadcast comparten un lock de envío por observador.

Browser mide recepción→DOM localmente con performance.now. Dos rAF generan una
muestra de oportunidad de pintado, descartada si la ventana cambió antes de medirla.
No prueba salida visible de OBS/encoder/display. El resultado READY→visible es una
estimación: READY→Hub medido + entrega sincronizada estimada + tiempo local hasta
doble-rAF. Sin sincronización válida o al restaurar snapshots no se inventa esa
cifra. coalesced_render_updates informa actualizaciones DOM entre pintados.

El observador solo envía render_sample con números validados y session/sequence
vigentes; cada cliente conserva una muestra reciente y el hub 128 en total. No
envía texto ni credenciales. Operator muestra mediciones, estimaciones, profundidad
de ambas colas, captions/líneas visibles y alertas. La duración provider incluye
adaptador/thread/red y retries por separado, no solo tiempo HTTP de DeepL.

Sigue sin medirse el inicio físico del habla → primera hipótesis ASR; ni composición,
buffering, encoder y pantalla de OBS. Las pruebas sintéticas aíslan el renderer y
no permiten afirmar mejora end-to-end real hasta otra lectura instrumentada.
