# Instalación reproducible candidata v0.1.0-rc1 (Windows)

**Estado: auditado en el entorno existente; instalación desde cero PENDIENTE.**
No ejecutar estos pasos encima del `.venv` que está prestando servicio. Ensayar en
otro directorio/PC y conservar el entorno anterior para rollback. No hay Docker.

## Entorno observado el 2026-10-17

- Windows x64, CPython **3.12.10**. Otras versiones no están validadas.
- FastAPI 0.141.1, Uvicorn 0.53.0, websockets 17.1, httpx 0.28.1.
- WhisperLiveKit **0.2.26**, faster-whisper **1.2.1**, CTranslate2 **4.8.2**.
- torch **2.14.0+cu126**, torchaudio **2.11.0**, build CUDA 12.6.
- GTX 1650 SUPER, 4096 MiB, driver 616.92. `torch.cuda.is_available()` devolvió
  True; CTranslate2 detectó un dispositivo CUDA. Esto no mide rendimiento sostenido.
- `python -m pip check`: **No broken requirements found**.
- Inventario completo, sin URLs ni credenciales: [m8_environment.json](benchmarks/m8_environment.json).

`requirements-release.lock` fija la aplicación y dependencias transitivas de sus
tests HTTP, sin sustituir `requirements.txt`. Es un pin de versiones observadas,
sin hashes de wheels ni garantía de que exista cada artefacto en cualquier índice.
`.gitattributes` conserva LF en glosarios, evidencia JSON M8 y pins para evitar
que `core.autocrlf=true` cambie entradas con SHA-256 al clonar. El generador de
informes M8 normaliza solo finales de línea y actualiza el manifiesto de evidencia.
No cambia el contenido de los glosarios ni la política del pipeline.
El inventario ASR/GPU **no es un lock portable**: wheels CUDA, DLL, driver y caché
del modelo deben verificarse en el equipo de ensayo. No se actualizó ningún paquete.

## Preparación en una copia limpia

Instalar CPython 3.12.10 x64 y Git; para todas las suites JS, disponer de Node y
registrar `node --version`. Chrome/Edge permite ejecutar pruebas de layout, popup,
audio sintético y WebSocket reales; una omisión por falta de navegador no aprueba
esa parte del gate. En esta máquina las seis suites JS se ejecutaron mediante el
runtime Node de Codex; `node` no está en PATH. No se validó aquí un instalador Node.

```powershell
cd C:\live-captions-clean
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-release.lock
.\.venv\Scripts\python.exe -m pip check
Copy-Item .env.example .env
```

La aplicación no importa modelos ASR. Puede usarse un entorno WLK separado.
En ese entorno, partir de los pins observados `whisperlivekit==0.2.26`,
`faster-whisper==1.2.1`, `ctranslate2==4.8.2`; resolver primero los wheels de
torch/torchaudio y las DLL compatibles con el hardware objetivo. El inventario
anterior documenta el equipo operativo, pero **no constituye una receta CUDA
desde cero validada**. No instalar una versión más reciente para resolver a ciegas
un conflicto. Guardar resultado de instalación, `pip check` y smoke test antes de
aprobar este gate. El modelo `small` puede necesitar descarga inicial; prepararlo
antes de una conferencia. No enviar audio privado para probar la instalación.

En el entorno ASR verificar, sin abrir micrófono:

```powershell
.\.venv\Scripts\python.exe -c "import torch,ctranslate2; print(torch.__version__,torch.version.cuda,torch.cuda.is_available(),ctranslate2.get_cuda_device_count())"
.\.venv\Scripts\wlk.exe --help
```

Si las versiones observadas no se pueden instalar en el equipo limpio, registrar
el error como **BLOQUEADO**; no cambiar las versiones ni afirmar reproducibilidad.
La aceptación debe incluir un arranque real de WLK y una lectura con su modelo.

## Configuración y arranque

`.env` acepta comillas literales. No ejecuta shell ni interpola variables. Las
variables de la terminal prevalecen sobre el archivo. `.env.example` inicia sin
traducción facturable. Para una prueba autorizada escribir localmente
`DEEPL_API_KEY="..."`, `TRANSLATION_ENABLED=1`, `TRANSLATION_PROVIDER=deepl`.
El endpoint observado es Free; si la cuenta requiere otro endpoint, configurarlo
según esa cuenta. No imprimir ni compartir la clave. Dos segmentos de contexto,
timeout 8 s, un retry y cola 32 permanecen como baseline. Un retry puede repetir
consumo cuando la respuesta anterior se perdió.

Con el micrófono detenido y sin otro proceso ocupando los puertos:

```powershell
# Terminal WLK (usar su entorno si está separado)
.\.venv\Scripts\wlk.exe --backend faster-whisper --model small --language es --pcm-input
# Terminal aplicación
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

WLK 0.2.26 usa `localhost` por defecto; se verificaron listeners IPv4/IPv6 loopback
en 8000 y FastAPI en 127.0.0.1:8010. Nunca usar `0.0.0.0` ni múltiples workers.
`GET /health` verifica FastAPI, **no** carga/disponibilidad del modelo WLK ni DeepL.
WLK se valida al handshake START; DeepL solo queda verificado tras un resultado.
Ante WinError 10048 revisar el proceso del puerto, no iniciar un segundo backend.

Abrir `http://localhost:8010/operator`, permitir micrófono y popups en Chrome/Edge,
actualizar dispositivos, seleccionar Blue Yeti y START. Mantener CAPTURE abierta;
recargar únicamente Operator para probar recuperación. Usar el mismo hostname/origen
durante toda la operación. No copiar nonces, resume secrets ni archivos `.runtime`.

Ver [OBS_OVERLAY.md](OBS_OVERLAY.md) para 1920×1080 y
[MANUAL_VALIDATION_V0_1.md](MANUAL_VALIDATION_V0_1.md) para aceptación física.
STOP debe finalizar flush/drain y mostrar outcome completo antes de cerrar CAPTURE.
Después Ctrl+C en FastAPI y WLK. Un reinicio pierde el estado en memoria; no recupera
audio ni reproduce traducciones anteriores. Rollback: STOP, cerrar servidores,
volver al checkout/entorno M7 conservado y reiniciar. Nunca hacerlo durante LIVE.

## Regresión sin cuota

En una terminal de prueba (no la que iniciará producción):

```powershell
$env:TRANSLATION_ENABLED='0'
$env:M8_E2E_OUTPUT='benchmarks/m8_e2e_results.json'
$env:M7_SOAK_OUTPUT='benchmarks/m8_soak_results.json'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node tests/test_operator_console.cjs
node tests/test_operator_partial.cjs
node tests/test_overlay_renderer.cjs
node tests/test_persistent_captions.cjs
node tests/test_overlay_geometry.cjs
node tests/test_reliability.cjs
.\.venv\Scripts\python.exe -m benchmarks.release_validation --output benchmarks/m8_replay_results.json
```

Python incluye una hora **virtual** de carga y aproximadamente un minuto de replay
a tiempo real en Chrome aislado; no son una conferencia física. Guardar salida y
comprobar que no haya skips de navegador. Cerrar esta terminal de pruebas antes de
iniciar producción: `TRANSLATION_ENABLED=0` prevalece sobre `.env`.
