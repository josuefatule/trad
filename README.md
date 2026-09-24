# Live Captions local — Milestone 1

Operador propio y proxy FastAPI para WhisperLiveKit 0.2.26 instalado en `.venv`.
Captura PCM desde el micrófono, muestra parcial/confirmado y registra el protocolo.
**Implementación lista para la prueba física; el hito sigue pendiente de validar
captura y transcripción española con el Blue Yeti en un navegador.**

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
6. Observar el texto cambiante en **PARTIAL** y el confirmado en **CONFIRMED**.
   La última línea confirmada puede crecer. Abrir **Segmentos / timestamps** para
   ver los tiempos reales. La latencia y visibilidad del parcial dependen de WLK.
7. Pulsar **STOP**, esperar `sesión finalizada` y comprobar que el final se conserva,
   que no se repite todo el historial y que se apaga el indicador de micrófono.
8. Pulsar START otra vez: debe comenzar con texto vacío y una sesión nueva.
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

**16 pruebas pasaron**: parcial, confirmación, líneas crecientes, frases consecutivas,
silencio/timestamps, duplicados, repetición legítima, reset, controles, diarización,
copia de snapshots, rutas HTTP, error visible, proxy PCM/EOF, modo incompatible,
timeout y desconexión. Usan unittest, websockets y el httpx ya instalado para
TestClient; no requieren pytest ni GPU. Los errores de conexión deliberados del
test aparecen en el log y no son fallos de la suite.

Prueba opcional contra los dos servidores **ya arrancados**:

```powershell
.\.venv\Scripts\python.exe tests/smoke_live.py
```

Esta prueba pasó con WLK real: HTTP 200 en ambos health y `/operator`, config PCM,
un segundo de silencio a través del proxy, snapshots y `ready_to_stop`. Solo genera
silencio en memoria; no valida habla ni el navegador.

También se verificó sintaxis de los tres JavaScript y que el worker produce los
mismos bytes que el instalado para bloques a 16000, 44100 y 48000 Hz, incluida
la barrera FIFO antes de EOF. No fue posible validar visualmente ni capturar
Blue Yeti: la herramienta de automatización no tenía navegadores conectados.

## Archivos y dependencias

- `app/main.py`: rutas, configuración y logs.
- `app/asr/whisperlivekit_client.py`: conexión WLK y proxy bidireccional.
- `app/captions/transcript_state.py`: reconstrucción desde snapshots completos.
- `app/templates/operator.html`: página de operador.
- `app/static/operator.js`, `operator.css`: controles, estados y renderizado.
- `app/static/pcm_worklet.js`, `recorder_worker.js`: captura y conversión basada en WLK.
- `tests/test_transcript_state.py`, `test_proxy.py`, `smoke_live.py`: pruebas.
- `ARCHITECTURE.md`, `PLAN.md`, `requirements.txt`, `third_party/`: documentación y licencia.

**Paquetes instalados o actualizados: ninguno.** `requirements.txt` contiene solo
las dependencias de ejecución de nuestra aplicación ya presentes: FastAPI 0.141.1,
Uvicorn 0.53.0 y websockets 17.1. No es un freeze del entorno.

## Límites y siguiente decisión

- No cerrar Milestone 1 hasta superar la prueba manual anterior.
- WLK mostró un aviso sobre Triton: usa un median kernel más lento como fallback.
  Aun así arrancó con CUDA y completó la prueba de transporte. No se modificó CUDA.
- TestClient emitió una deprecación por httpx y sugirió httpx2; los tests pasan
  con la dependencia existente, por lo que no se cambió el entorno.
- El modo full crece con la duración; no activar recorte de historial en WLK.
- Se conserva el remuestreo por bloques del frontend instalado, con su redondeo.
- Al perder una conexión hay que iniciar una sesión nueva; no hay recuperación
  de texto persistente. No existe vista pasiva de otra sesión.
- Antes de otro milestone, registrar calidad y latencia con el Yeti, probar una
  sesión larga y decidir qué unidad confirmada consumirá el futuro Segment Manager.
  No se ha implementado traducción.

Git ya estaba inicializado y `.venv/` está explícitamente ignorado. La preparación
del scaffold se añadió al índice; el commit no pudo crearse porque faltan
`user.name` y `user.email`. No se inventó identidad ni se cambió configuración global.
