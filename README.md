# Live Captions local — Milestone 2: Segment Manager

Operador propio y proxy FastAPI para WhisperLiveKit 0.2.26 instalado en `.venv`.
Captura PCM desde el micrófono, muestra parcial/confirmado y registra el protocolo.
**Blue Yeti validado por el usuario para CONFIRMED.** La investigación con voz real
del 2026-09-29 confirmó que WLK entrega `buffer_transcription` vacío con la política
SimulStreaming predeterminada e idioma `es`. PARTIAL permanece vacío por esa
limitación; no se fabrica texto parcial. Evidencia y pruebas en
[PARTIAL_INVESTIGATION.md](PARTIAL_INVESTIGATION.md).

Milestone 2 añade ASR CONFIRMED → SEGMENT PENDING → TRANSLATION READY, en español.
No implementa traducción ni normalización. Implementación validada con tests y replay
real; la validación final de voz del Segment Manager queda al usuario.

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
   **SEGMENT PENDING** crece/se revisa; **TRANSLATION READY** agrega unidades
   inmutables con razón, palabras y latencia. Sus timestamps son límites de líneas
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
| `SEGMENT_MINIMUM_WORDS` | `6` palabras para que silencio/edad blanda sean útiles |
| `SEGMENT_TARGET_WORDS` | `16` palabras objetivo para buscar un corte natural |
| `SEGMENT_MAX_WORDS` | `24` palabras; límite fuerte |
| `SEGMENT_SOFT_MAX_AGE_SECONDS` | `4.5` segundos; solo corta en límite natural y tras el mínimo |
| `SEGMENT_HARD_MAX_AGE_SECONDS` | `7.0` segundos; garantiza progreso |
| `SEGMENT_TICK_SECONDS` | `0.1` segundos entre evaluaciones |

Valores de desarrollo, leídos al arrancar. Ejemplo para comparar configuraciones:

```powershell
$env:SEGMENT_HARD_MAX_AGE_SECONDS = "8"
.\.venv\Scripts\python.exe replay_fixture.py benchmarks/medical_real_snapshots.json
```

Reiniciar FastAPI para aplicar variables a la UI. Puntuación y pausa esperan
estabilidad. La edad blanda requiere mínimo y un límite lingüístico; la edad dura y
el máximo de palabras sí garantizan progreso. Una palabra terminal sin whitespace se
retiene cuando existe un corte anterior seguro, porque WLK todavía puede completarla
o añadir puntuación. Pausa requiere evidencia ASR, no inactividad de red. EOF vacía
el pendiente sin esperar. Reconciliación y limitaciones explicadas en ARCHITECTURE.md.

Ejemplo para analizar protocolo original:

```powershell
$env:CAPTIONS_LOG_RAW = "1"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

Los eventos están en `logs/development.log` y los mensajes originales, si se
habilitan, en `logs/wlk-raw.log`. Incluyen texto transcrito; ambos están ignorados
por Git. No se guardan muestras de audio. No se carga `.env` automáticamente.

## Pruebas y evidencia

```powershell
cd C:\live-captions
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

**59 pruebas pasaron**: parcial, confirmación, líneas crecientes, frases consecutivas,
silencio/timestamps, duplicados, repetición legítima, reset, controles, diarización,
copia de snapshots, rutas HTTP, error visible, proxy PCM/EOF, modo incompatible,
timeout y desconexión. Usan unittest, websockets y el httpx ya instalado para
TestClient; no requieren pytest ni GPU. Los errores de conexión deliberados del
test aparecen en el log y no son fallos de la suite.

Incluyen SegmentManager, replay médico con conservación de palabras, late revisions,
cortes, métricas, timer sin nuevos mensajes y dos sesiones FastAPI completas contra
un WLK simulado que entrega payloads reales. Prueba adicional del operador con DOM
simulado: `node tests/test_operator_partial.cjs`, si Node está disponible. Se ejecutó
con el runtime de la herramienta, sin instalarlo.

Replay sin servidores, GPU ni micrófono:

```powershell
.\.venv\Scripts\python.exe replay_fixture.py benchmarks/medical_real_snapshots.json
```

Imprime PENDING, READY con métricas, late revisions y resumen. Reproduce virtualmente
el tiempo de 61 eventos reales capturados en M1. Ver `benchmarks/README.md`.

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
- `app/templates/operator.html`: página de operador.
- `app/static/operator.js`, `operator.css`: controles, estados y renderizado.
- `app/static/pcm_worklet.js`, `recorder_worker.js`: captura y conversión basada en WLK.
- `tests/test_transcript_state.py`, `test_proxy.py`, `smoke_live.py`: pruebas.
- `tests/test_segment_manager.py`, `test_session_replay.py`: segmentación e integración.
- `replay_fixture.py`, `benchmarks/`: replay y lectura médica sin corregir.
- `ARCHITECTURE.md`, `PLAN.md`, `requirements.txt`, `third_party/`: documentación y licencia.

**Paquetes instalados o actualizados: ninguno.** `requirements.txt` contiene solo
las dependencias de ejecución de nuestra aplicación ya presentes: FastAPI 0.141.1,
Uvicorn 0.53.0 y websockets 17.1. No es un freeze del entorno.

## Límites y siguiente decisión

- Milestone 1 validado; confirmar ahora la experiencia de segmentación con voz.
- La afinación reduce el replay médico de 25 a 10 segmentos. Conserva sus 81
  palabras exactamente y no genera late revisions; ver `benchmarks/README.md`.
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
- Antes de otro milestone, validar estos thresholds con el Yeti, probar una sesión
  larga y decidir si se admitirán correcciones explícitas de READY y timestamps más finos.
  No se ha implementado traducción ni normalización.

Git ya estaba inicializado y `.venv/` está explícitamente ignorado. Se utiliza
la identidad ya configurada en Git, sin modificarla.
