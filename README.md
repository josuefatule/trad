# Live Captions local — M5.1: Persistent Captions & Latency Diagnostics

Operador propio y proxy FastAPI para WhisperLiveKit 0.2.26 instalado en `.venv`.
Captura PCM desde el micrófono, muestra parcial/confirmado y registra el protocolo.
**Blue Yeti validado por el usuario para CONFIRMED.** La investigación con voz real
del 2026-09-29 confirmó que WLK entrega `buffer_transcription` vacío con la política
SimulStreaming predeterminada e idioma `es`. PARTIAL permanece vacío por esa
limitación; no se fabrica texto parcial. Evidencia y pruebas en
[PARTIAL_INVESTIGATION.md](PARTIAL_INVESTIGATION.md).

El flujo actual es ASR CONFIRMED → SEGMENT PENDING → RAW ES → NORMALIZED ES →
TranslationEngine → ENGLISH. RAW y NORMALIZED permanecen inmutables. La traducción
se ejecuta en una cola secuencial independiente y está deshabilitada por defecto;
el operador nunca presenta el español como si fuera inglés.

M5 comparte esa misma traducción con un overlay transparente en
**http://localhost:8010/overlay**. No abre otro micrófono, conexión WLK ni llamada
DeepL. El operador sigue siendo la única fuente de audio y control.
Preview local sin voz ni API: **http://localhost:8010/overlay/preview** → Play demo.
Configuración y pasos completos: [OBS_OVERLAY.md](OBS_OVERLAY.md).

M5.1 usa persistent_rolling: tres líneas (configurable a dos), reflow continuo y
actualización inmediata. Las pausas no borran texto; STOP limpia tras 8 s. El modo
timed_queue anterior sigue disponible. Operator añade latencias por etapa, cola y
telemetría de Browser Source con mediciones y estimaciones claramente separadas.

## Arranque (PowerShell)

No recrear `.venv` ni actualizar la pila ASR. Las dependencias ya están presentes.

Terminal 1:

```powershell
cd C:\live-captions
.\.venv\Scripts\wlk.exe --backend faster-whisper --model small --language es --pcm-input
```

Esperar a `Application startup complete`. Terminal 2:

```powershell
cd C:\live-captions
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

Abrir **http://localhost:8010/operator** en Chrome o Edge. No utilizar `0.0.0.0`
como dirección del navegador. Ctrl+C detiene cada servidor; STOP detiene la sesión
de audio y deja disponibles los servidores. Si un puerto ya está ocupado, revisar
si el proceso correspondiente sigue abierto antes de iniciar otro.

## Prueba exacta con Blue Yeti

1. Conectar el Blue Yeti y arrancar ambos servidores. Esperar a que WLK esté listo.
2. Abrir `/operator`. Pulsar **Permitir / actualizar micrófonos** y aceptar el
   permiso de micrófono para localhost.
3. Seleccionar explícitamente la entrada cuyo nombre corresponda al **Blue Yeti**;
   el nombre exacto depende de Windows. No dejar Predeterminado si hay varios.
4. Pulsar **START**. Debe aparecer `Connected` y el nombre del dispositivo con
   su frecuencia de captura y el destino `PCM s16le mono 16000 Hz`.
5. Decir: «La hipertensión arterial es un factor de riesgo cardiovascular».
   Hacer una pausa y decir: «El paciente necesita seguimiento y control de la presión».
   Para el benchmark, leer `benchmarks/medical_reference.txt` con pausas y de corrido.
6. Observar el confirmado en **ASR CONFIRMED**. **PARTIAL** solo muestra hipótesis que
   WLK realmente envía; con la configuración actual se ha observado siempre vacío.
   La última línea confirmada puede crecer. Abrir **Segmentos / timestamps** para
   ver los tiempos reales. La latencia y visibilidad del parcial dependen de WLK.
   **SEGMENT PENDING** crece/se revisa; **RAW ES** agrega unidades inmutables con
   razón, palabras y latencia. **NORMALIZED ES** muestra la salida derivada y
   **CORRECTIONS / SUGGESTIONS** su auditoría. Los timestamps son límites de líneas
   fuente; pueden solaparse y no equivalen a tiempos precisos de palabras.
7. Pulsar **STOP**, esperar `sesión finalizada` y comprobar que el final se conserva,
   que no se repite todo el historial y que se apaga el indicador de micrófono.
   Probar también una lectura sin punto final: el remanente debe salir como `session_end`.
8. Pulsar START otra vez: CONFIRMED, PENDING y READY deben estar vacíos; sesión nueva.
9. Para comprobar errores, detener WLK después de acabar una sesión y pulsar START:
   debe aparecer un error visible, sin quedar el micrófono capturando indefinidamente.

Si la lista no muestra nombres, volver a permitir/actualizar y revisar el permiso
del navegador. Si se desconecta el Yeti, reiniciar la sesión tras reconectarlo.
Para esta GPU de 4 GB, probar inicialmente **una sesión activa**.

## Configuración sencilla

Variables opcionales antes de arrancar nuestra app:

| Variable | Predeterminado |
| --- | --- |
| `WLK_WS_URL` | `ws://localhost:8000/asr` |
| `CAPTIONS_LANGUAGE` | `es` |
| `CAPTIONS_LOG_RAW` | `0` (usar `1` para registrar payloads) |
| `CAPTIONS_LOG_DIR` | `C:\live-captions\logs` (relativo a la ubicación del proyecto) |
| `CAPTIONS_CONNECT_TIMEOUT` | `15` segundos |
| `CAPTIONS_STOP_TIMEOUT` | `120` segundos |
| `SEGMENT_STABILIZATION_SECONDS` | `0.8` segundos |
| `SEGMENT_SILENCE_SECONDS` | `1.0` segundos de silencio/gap ASR |
| `SEGMENT_MINIMUM_WORDS` | `7` palabras pendientes antes de habilitar la edad blanda |
| `SEGMENT_TARGET_WORDS` | `13` palabras; ancla de búsqueda retrospectiva |
| `SEGMENT_MAX_WORDS` | `21` palabras; límite fuerte |
| `SEGMENT_SAFE_CUT_LOOKBACK_WORDS` | `8` palabras de búsqueda hacia atrás |
| `SEGMENT_SOFT_MAX_AGE_SECONDS` | `3.3` segundos; requiere un `safe_cut` estable |
| `SEGMENT_HARD_MAX_AGE_SECONDS` | `5.5` segundos; garantiza progreso |
| `SEGMENT_TICK_SECONDS` | `0.1` segundos entre evaluaciones |
| `NORMALIZER_AUTO_THRESHOLD` | `0.90`; debe superar el umbral de sugerencia |
| `NORMALIZER_SUGGEST_THRESHOLD` | `0.86` |
| `NORMALIZER_MAX_TOKEN_DELTA` | `1` palabra de diferencia para candidatos fuzzy |
| `NORMALIZER_CONTEXT_WORDS` | `8` palabras recientes para sugerencias entre segmentos |
| `NORMALIZER_COLLAPSED_MIN_CHARACTERS` | `10`; longitud mínima para un canónico técnico unido |
| `NORMALIZER_COLLAPSED_MAX_EDITS` | `1`; distancia máxima fuerte tras unir dos tokens ASR |
| `NORMALIZER_MEDICAL_GLOSSARY` | `glossaries/medical_base.json` |
| `NORMALIZER_CONFERENCE_GLOSSARY` | `glossaries/conference.json` |
| `TRANSLATION_ENABLED` | `0`; ASR y normalización siguen funcionando |
| `TRANSLATION_PROVIDER` | vacío; valores implementados: `mock`, `deepl` |
| `TRANSLATION_SOURCE_LANGUAGE` | `es` |
| `TRANSLATION_TARGET_LANGUAGE` | `en` |
| `TRANSLATION_CONTEXT_SEGMENTS` | `2` segmentos NORMALIZED anteriores |
| `TRANSLATION_TIMEOUT_SECONDS` | `8` por intento |
| `TRANSLATION_RETRIES` | `1` retry máximo |
| `TRANSLATION_QUEUE_MAXSIZE` | `32`; desborde visible como error de segmento |
| `DEEPL_API_KEY` | vacío; requerido cuando provider=`deepl`; acepta también `DEEPL_AUTH_KEY` |
| `DEEPL_API_URL` | `https://api-free.deepl.com/v2/translate` |

Valores de desarrollo, leídos al arrancar. Ejemplo para comparar configuraciones:

```powershell
$env:SEGMENT_HARD_MAX_AGE_SECONDS = "8"
.\.venv\Scripts\python.exe replay_fixture.py benchmarks/medical_real_snapshots.json
```

Para probar M4 sin credenciales, usar el mock explícito. Su salida empieza por
`[MOCK EN]` y no representa una traducción real:

```powershell
$env:TRANSLATION_ENABLED = "1"
$env:TRANSLATION_PROVIDER = "mock"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

Para DeepL, definir además `DEEPL_API_KEY`. El adaptador envía únicamente el
segmento actual en `text`; los segmentos anteriores viajan en `context`, que DeepL
usa como contexto sin traducirlo. FastAPI y replay cargan automáticamente el `.env`
de la raíz del proyecto. Acepta valores entre comillas simples o dobles; las variables
de la terminal tienen prioridad. No se expanden variables dentro de los valores.
Para activar DeepL al arrancar, configurar en `.env`:

```ini
TRANSLATION_ENABLED=1
TRANSLATION_PROVIDER=deepl
DEEPL_API_KEY="tu-clave"
```

`.env` sigue ignorado por Git. Reiniciar FastAPI después de editarlo.

Reiniciar FastAPI para aplicar variables a la UI. `safe_cut` busca hacia atrás y
prioriza puntuación fuerte, punto y coma, coma, límite de línea WLK y whitespace.
La edad blanda exige suficiente contenido y un límite estable; la edad dura y el
máximo de palabras garantizan progreso. El sufijo posterior al corte permanece en
PENDING. Pausa requiere evidencia ASR, no inactividad de red. EOF vacía el pendiente
sin esperar. Reconciliación y limitaciones explicadas en ARCHITECTURE.md.

Ejemplo para analizar protocolo original:

```powershell
$env:CAPTIONS_LOG_RAW = "1"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

Los eventos están en `logs/development.log` y los mensajes originales, si se
habilitan, en `logs/wlk-raw.log`. Incluyen texto transcrito; ambos están ignorados
por Git. No se guardan muestras de audio.

## Pruebas y evidencia

```powershell
cd C:\live-captions
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

**121 pruebas Python pasan**, además de las pruebas DOM de Operator y overlay:
parcial, confirmación, líneas crecientes, frases consecutivas,
silencio/timestamps, duplicados, repetición legítima, reset, controles, diarización,
copia de snapshots, rutas HTTP, error visible, proxy PCM/EOF, modo incompatible,
timeout y desconexión. Usan unittest, websockets y el httpx ya instalado para
TestClient; no requieren pytest ni GPU. Los errores de conexión deliberados del
test aparecen en el log y no son fallos de la suite.

Incluyen SegmentManager, replay médico con conservación de palabras, late revisions,
cortes, métricas, normalización exacta/fuzzy, negativos, solapamientos, contexto entre
segmentos y transporte FastAPI contra WLK simulado. La prueba adicional del operador
con DOM simulado es `node tests/test_operator_partial.cjs`, si Node está disponible.
El renderer y transporte del overlay se prueban con `node tests/test_overlay_renderer.cjs`.
M5.1: `node tests/test_persistent_captions.cjs`; comparación reproducible en
`benchmarks/renderer_arrivals.py` y `benchmarks/renderer_policy.cjs`.
Para ejecutar toda la suite sin usar DeepL real aunque `.env` esté configurado:

```powershell
$env:TRANSLATION_ENABLED = "0"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
Remove-Item Env:TRANSLATION_ENABLED
```

Replay sin servidores, GPU ni micrófono; usa el mock por defecto:

```powershell
.\.venv\Scripts\python.exe replay_fixture.py benchmarks/medical_real_snapshots.json
```

Imprime PENDING, READY y, por segmento, RAW ES, NORMALIZED ES, CONTEXT, ENGLISH,
provider y latencia. Resume éxitos, fallos, retries, timeouts, latencia de traducción
y demora de cola. `--translation-provider configured` usa las variables de entorno;
`disabled` prueba el flujo sin traducción. Ver `benchmarks/README.md`.

Prueba opcional contra los dos servidores **ya arrancados**:

```powershell
.\.venv\Scripts\python.exe tests/smoke_live.py
```

Esta prueba pasó con WLK real: HTTP 200 en ambos health y `/operator`, config PCM,
un segundo de silencio a través del proxy, snapshots y `ready_to_stop`. Solo genera
silencio en memoria; no valida habla ni el navegador.

También se verificó sintaxis de los tres JavaScript y que el worker produce los
mismos bytes que el instalado para bloques a 16000, 44100 y 48000 Hz, incluida
la barrera FIFO antes de EOF durante M1. El usuario validó voz real con Blue Yeti
en M1; queda a su cargo la validación final de las nuevas reglas de segmentación.

## Archivos y dependencias

- `app/main.py`: rutas, configuración y logs.
- `app/asr/whisperlivekit_client.py`: conexión WLK y proxy bidireccional.
- `app/captions/transcript_state.py`: reconstrucción desde snapshots completos.
- `app/captions/segment_manager.py`: reconciliación, reglas, reloj, datos y métricas.
- `app/captions/terminology_normalizer.py`: glosarios, matching y auditoría.
- `app/translation/models.py`: contratos inmutables request/result/context.
- `app/translation/providers.py`: abstracción, mock determinístico y adaptador DeepL.
- `app/translation/engine.py`: contexto, cola, ordering, timeout, retries y métricas.
- `app/overlay/`: hub de sesión, suscriptores y configuración visual validada.
- `app/static/caption_renderer.js`, `overlay.js`, `overlay.css`: presentación y transporte del overlay.
- `app/templates/overlay.html`, `overlay_preview.html`: overlay público y demo aislado.
- `tests/test_overlay.py`, `test_overlay_renderer.cjs`: broadcast, integración y presentación.
- `glossaries/medical_base.json`, `conference.json`: términos base y del evento.
- `app/templates/operator.html`: página de operador.
- `app/static/operator.js`, `operator.css`: controles, estados y renderizado.
- `app/static/pcm_worklet.js`, `recorder_worker.js`: captura y conversión basada en WLK.
- `tests/test_transcript_state.py`, `test_proxy.py`, `smoke_live.py`: pruebas.
- `tests/test_segment_manager.py`, `test_session_replay.py`: segmentación e integración.
- `tests/test_terminology_normalizer.py`: exactos, fuzzy, negativos y replay real.
- `replay_fixture.py`, `benchmarks/`: replay y lectura médica sin corregir.
- `ARCHITECTURE.md`, `PLAN.md`, `requirements.txt`, `third_party/`: documentación y licencia.

**Paquetes instalados o actualizados: ninguno.** `requirements.txt` contiene solo
las dependencias de ejecución de nuestra aplicación ya presentes: FastAPI 0.141.1,
Uvicorn 0.53.0 y websockets 17.1. No es un freeze del entorno.

## Normalización y límites

Las formas exactas conocidas se corrigen con confianza 1. El matching fuzzy solo se
habilita para términos de varias palabras y exige el umbral alto para modificar texto;
entre ambos umbrales solo crea una sugerencia. Los términos solapados se resuelven de
forma determinista. Mayúsculas, acentos, guiones/espacios y puntuación adyacente se
preservan cuando corresponde. El contexto reciente puede detectar un término dividido
entre dos READY, pero siempre genera `cross_segment_suggestion`: nunca reescribe READY
anteriores.

Milestone 3.1 permite además unir un span ASR de dos tokens contra un canónico técnico
de una palabra, con longitud mínima y distancia de edición configurables. No habilita
fuzzy global de palabras aisladas. El espaciado repetido y alrededor de puntuación se
normaliza mediante correcciones auditables, sin añadir signos. La UI exige la capability
del backend y deja de copiar RAW silenciosamente cuando falta `normalization`; un error
visible indica que hay que reiniciar FastAPI. Evidencia en
`benchmarks/MILESTONE_3_1_REPORT.md`.

Editar `glossaries/conference.json` permite añadir vocabulario del evento sin cambiar
la base. Cada entrada admite `canonical`, `variants`, `aliases`, `auto_apply`
(`exact`, `fuzzy` o `suggest`) y umbrales opcionales. Reiniciar FastAPI tras cambiar
el archivo. El formato completo está en `glossaries/README.md`.

En el replay médico real se conserva RAW 81/81. Se aplican
`systólica → sistólica` y `al dosterona → aldosterona`; `Suficio` produce una
sugerencia, `pertenecios` queda intacto y el término partido
`herenina angiotensina | al dosterona` produce otra sugerencia contextual.
Con el glosario de Milestone 3.1, el perfil de 1.600 evaluaciones dio mediana
25,867 ms, p95 53,079 ms y máximo 72,956 ms por segmento. Ver
`benchmarks/NORMALIZER_REPORT.md`.

- Milestone 1 validado; confirmar ahora la experiencia de segmentación con voz.
- La afinación final produce 16 segmentos con mediana de 3,83 s, frente a 25/2,88 s
  originalmente y 10/7,04 s en la iteración anterior. Conserva exactamente las 81
  palabras y no genera late revisions; ver `benchmarks/README.md`.
- Los tiempos ASR son por línea; cortes distintos pueden solaparse. Abreviaturas
  y reorganizaciones arbitrarias de líneas siguen siendo limitaciones. Revisiones
  ambiguas que cruzan lo publicado se registran y no se republican silenciosamente.
- WLK mostró un aviso sobre Triton: usa un median kernel más lento como fallback.
  Aun así arrancó con CUDA y completó la prueba de transporte. No se modificó CUDA.
- TestClient emitió una deprecación por httpx y sugirió httpx2; los tests pasan
  con la dependencia existente, por lo que no se cambió el entorno.
- El modo full crece con la duración; no activar recorte de historial en WLK.
- Se conserva el remuestreo por bloques del frontend instalado, con su redondeo.
- Al perder una conexión hay que iniciar una sesión nueva; no hay recuperación
  de texto persistente. No existe vista pasiva de otra sesión.
- Antes de otro milestone, validar los cortes y la normalización con el Yeti, probar
  una sesión larga y revisar cualquier sugerencia falsa. No se ha implementado traducción.

Git ya estaba inicializado y `.venv/` está explícitamente ignorado. Se utiliza
la identidad ya configurada en Git, sin modificarla.
