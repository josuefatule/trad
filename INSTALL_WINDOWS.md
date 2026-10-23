# Instalación reproducible candidata v0.1.0-rc1 (Windows)

**MVP bidireccional posterior a M1:** para usar el selector EN↔ES se requiere el
[nuevo punto de entrada WLK](#mvp-bidireccional--arranque-posterior-a-s2-m1).
El comando WLK estándar de M1 se conserva como referencia histórica y rollback;
no confirma aislamiento de idioma para las nuevas sesiones bidireccionales.

**Actualización S2-M1, 2026-10-20:** migración funcional a Alienware verificada;
ver el [procedimiento vigente RTX 4070](#s2-m1--alienware-rtx-4070-procedimiento-vigente)
y el [informe de auditoría](S2-M1-REPORT.md). Las secciones anteriores a ese
procedimiento conservan la evidencia histórica de Sprint 1; sus rutas ASR y
versiones de hardware no describen la Alienware.

**Estado histórico Sprint 1: auditado en el entorno existente; instalación desde cero PENDIENTE.**
No ejecutar estos pasos encima del `.venv` que está prestando servicio. Ensayar en
otro directorio/PC y conservar el entorno anterior para rollback. No hay Docker.

## Entorno histórico Sprint 1 observado el 2026-10-17

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

## S2-M1 — Alienware RTX 4070: procedimiento vigente

Auditoría del 2026-10-20, checkout `C:\live-captions`, rama
`sprint2/m1-rtx4070`, baseline `64f8221` / `v0.1.0-rc1` conservado.
La instalación ya existente funciona; no se reinstaló ni se reinició durante
la auditoría. Un ensayo independiente desde cero y el rendimiento sostenido
continúan pendientes. No ejecutar instalación, arranque duplicado ni rollback
encima de una sesión LIVE.

### Dos entornos y versiones verificadas

| Componente | Entorno / versión observada |
|---|---|
| Aplicación | `.venv`, CPython 3.12.10 x64 |
| Dependencias de aplicación | Los 21 pins de `requirements-release.lock` coinciden; `pip check` PASS |
| HTTP / WebSocket | FastAPI 0.141.1, Uvicorn 0.53.0, websockets 17.1 |
| ASR | `.venv-wlk`, CPython 3.12.10; `pip check` PASS |
| Motor ASR | WhisperLiveKit 0.2.26, faster-whisper 1.2.1, CTranslate2 4.8.2 |
| Torch | 2.14.0+cu126; TorchAudio 2.11.0+cu126; build CUDA de Torch 12.6 |
| Node / npm instalados | `C:\Program Files\nodejs\node.exe` v24.20.0; `npm.cmd` 11.19.0 |
| GPU / sistema | RTX 4070 Laptop, 8188 MiB; driver 596.08; Windows 11 Pro 10.0.26300 x64 |

El PATH del proceso de auditoría selecciona Node v24.19.0 del runtime de Codex
y no encuentra `npm`. Para repetir las suites con el Node instalado, usar la
ruta absoluta anterior. No actualizar paquetes para resolver esta diferencia.
El inventario `benchmarks/m8_environment.json` es histórico de Sprint 1.

En una futura copia independiente, crear `.venv` y `.venv-wlk` con Python
3.12.10; instalar los pins de aplicación solo en `.venv`. El inventario ASR
anterior identifica lo instalado, pero no fija todas sus dependencias, wheels,
índices ni cachés. No constituye un lock ASR portable ni una instalación limpia
ya demostrada. Preparar `small` y sus recursos antes del ensayo; no descargar
modelos ni resolver versiones automáticamente durante una operación.

`.env` y `.venv/` están en `.gitignore`. En esta copia `.venv-wlk/` está
excluido por `.git/info/exclude`, regla local que **no viaja al clonar**.
Antes de crear ese entorno en otra copia, excluirlo también en su configuración
local o incorporar una regla versionada con autorización. Verificar con
`git check-ignore -v .env .venv .venv-wlk` y no añadir entornos ni secretos a Git.
Esta auditoría no modifica reglas Git ni credenciales.

### DLL CUDA y arranque con PATH limitado al proceso

En la primera inferencia se reportó:
`RuntimeError: Library cublas64_12.dll is not found or cannot be loaded`.
Las DLL están en `.venv-wlk\Lib\site-packages\torch\lib`; se verificó la
presencia de `cublas64_12.dll`, `cublasLt64_12.dll`, `cudart64_12.dll` y
`cusparse64_12.dll`. La solución histórica fue anteponer esa carpeta al PATH
de la terminal WLK. No copiar DLL a Windows ni cambiar el PATH global.

Con sesión detenida y puerto 8000 libre, abrir una terminal PowerShell dedicada:

```powershell
Set-Location C:\live-captions
& {
    $torchLib = Join-Path $PWD '.venv-wlk\Lib\site-packages\torch\lib'
    $wlkExe = Join-Path $PWD '.venv-wlk\Scripts\wlk.exe'
    if (!(Test-Path -LiteralPath (Join-Path $torchLib 'cublas64_12.dll'))) {
        throw 'Falta cublas64_12.dll en el entorno ASR; revisar instalación.'
    }
    if (!(Test-Path -LiteralPath $wlkExe)) { throw 'Falta wlk.exe en .venv-wlk.' }
    $previousPath = $env:PATH
    try {
        $env:PATH = "$torchLib;$previousPath"
        & $wlkExe serve --backend faster-whisper --model small --lan es --pcm-input --host localhost --port 8000
        if ($LASTEXITCODE -ne 0) { throw "WLK terminó con código $LASTEXITCODE" }
    }
    finally { $env:PATH = $previousPath }
}
```

Es un bloque de arranque mínimo documentado, sin archivo de infraestructura nuevo.
Solo altera el entorno del proceso PowerShell y sus hijos mientras corre WLK;
`finally` restaura el PATH al retornar. Los entornos virtuales y otros procesos
existentes no se modifican. Usar una terminal dedicada, sin lanzar otros programas
desde ella mientras corre WLK. No necesita activar ningún venv.
El parser instalado acepta `--backend faster-whisper`, `--model small`, `--lan es`,
`--pcm-input`, `--host localhost` y `--port 8000`; `serve` se enruta al servidor.
La política predeterminada sigue siendo `simulstreaming`. No añadir opciones de
traducción WLK ni cambiar modelo/política.

En otra terminal dedicada, con 8010 libre:

```powershell
Set-Location C:\live-captions
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

No usar múltiples workers, `0.0.0.0`, reglas de firewall ni servicios nuevos.
El bloque se verificó por sintaxis, parámetros y alcance del entorno; no se
ejecutó un segundo servidor. La inferencia `small` GPU sin excepciones y el
arranque WLK son evidencia previa del usuario; esta auditoría revalidó detección
CUDA (Torch y CTranslate2: una GPU) y readiness del servicio existente.
CUDA 13.2 en `nvidia-smi` es la compatibilidad anunciada por el driver; no es
la versión de build de Torch ni demuestra un CUDA Toolkit instalado.

### Configuración y comprobación sin consumo DeepL

El código lee `TRANSLATION_ENABLED=1`, `TRANSLATION_PROVIDER=deepl`,
`TRANSLATION_SOURCE_LANGUAGE=es`, `TRANSLATION_TARGET_LANGUAGE=en`.
La clave se configura localmente como `DEEPL_API_KEY`; existe el alias heredado
`DEEPL_AUTH_KEY`, con precedencia de la primera. Las variables de terminal
prevalecen sobre `.env`. No imprimir claves ni copiar contenido de `.runtime`.
No se leyó ni modificó `.env` durante esta auditoría.

Consultas de lectura sobre los servicios ya existentes:

```powershell
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8000/v1/models
Invoke-RestMethod http://127.0.0.1:8010/health
Get-NetTCPConnection -State Listen -LocalPort 8000,8010 |
    Select-Object LocalAddress,LocalPort
```

Resultados actuales: WLK `status=ok`, `backend=faster-whisper`, `ready=true`;
modelo `faster-whisper/small`; FastAPI `status=ok`, `language=es`,
`wlk_check=on_session_connect`. Listeners WLK `127.0.0.1`/`::1`:8000 y
FastAPI `127.0.0.1`:8010. Estos GET no envían audio ni llaman a DeepL.
Health de FastAPI no demuestra conectividad DeepL ni una nueva inferencia.

### Operator, OBS y cierre

Abrir `http://localhost:8010/operator` y usar el mismo origen durante la sesión.
El usuario confirmó CAPTURE/Blue Yeti, reconocimiento español, normalización,
traducción real y visualización inglesa en Operator/OBS en la Alienware.
La auditoría no abrió micrófono, no pulsó START/STOP/CLEAR ni alteró OBS.

En un ensayo autorizado, Browser Source apunta a
`http://localhost:8010/overlay`, 1920×1080, transparente, posición 0/0 y sin crop.
Desactivar apagado al ocultar y refresco al activar escena para conservar continuidad.
La región por defecto Y=930, alto 150, fuente 48 e interlineado 1.2 permite
**dos líneas efectivas**, aunque se soliciten tres. Ver [OBS_OVERLAY.md](OBS_OVERLAY.md)
para composición, geometría y legibilidad. No usar `/overlay/preview` como fuente
operativa; la salida en proyector físico y el ensayo prolongado siguen pendientes.

STOP completo requiere flush/drain y ninguna traducción fallida; después cerrar
CAPTURE y terminar manualmente los servidores. Un outcome `incomplete` exige
revisar fallos aunque workers/cola estén a cero. No reiniciar servicios durante LIVE.
El [informe S2-M1](S2-M1-REPORT.md) explica el soak con fallos inyectados y las
reservas de precisión médica. Esta migración no acredita uso en el congreso.

## MVP bidireccional — arranque posterior a S2-M1

No reiniciar LIVE. Esperar STOP, cierre completo de CAPTURE y liberación de la
sesión. En sesiones de la nueva implementación, si terminó incompleta, revisar
diagnósticos y reconocer la pérdida con **Reconocer cierre incompleto** desde el
Operator propietario; esto no recupera traducciones fallidas. Cerrar los servicios
manualmente solo durante esa ventana.
La implementación no los reinicia ni aplica cambios al proceso que ya está activo.

Mantener las mismas versiones y los mismos entornos. En la terminal WLK dedicada:

```powershell
Set-Location C:\live-captions
$previousPath = $env:PATH
try {
    $torchLib = Join-Path $PWD '.venv-wlk\Lib\site-packages\torch\lib'
    if (!(Test-Path -LiteralPath (Join-Path $torchLib 'cublas64_12.dll'))) {
        throw 'Falta la DLL CUDA del entorno ASR.'
    }
    $env:PATH = "$torchLib;$previousPath"
    .\.venv-wlk\Scripts\python.exe -m app.asr.wlk_server --backend faster-whisper --model small --lan en --pcm-input --host localhost --port 8000
    if ($LASTEXITCODE -ne 0) { throw "WLK terminó con código $LASTEXITCODE" }
}
finally { $env:PATH = $previousPath }
```

`app.asr.wlk_server` adapta **solo el arranque de WLK 0.2.26**. Conserva una
instancia, Faster-Whisper `small`, CUDA y SimulStreaming. Crea una copia ligera
de la configuración de idioma por conexión; comparte pesos/encoders y no edita
el paquete instalado. `--lan en` establece el idioma de construcción del motor;
el idioma efectivo de cada conexión es el `language=en|es` explícito de TRAD.
Otros idiomas, autodetección o parámetros duplicados se rechazan. No añadir `serve`
al comando Python: este módulo llama directamente al servidor.

Arrancar FastAPI como antes, con `.venv`, un worker y `127.0.0.1:8010`.
Esperar `/health` y `/v1/models` como en M1. La confirmación de idioma ocurre en
el handshake de cada sesión, no en health. Un WLK arrancado con el ejecutable
estándar será rechazado por una sesión bidireccional antes de enviar PCM.

En Operator elegir **English → Español** (predeterminado) o **Español → English**
antes de START. La dirección queda fija en la sesión, incluso al recargar la
consola. Cambiarla exige cierre completo; ninguna modificación de `.env` es
necesaria. Inglés usa normalización identidad y muestra esa limitación.
OBS mantiene `http://localhost:8010/overlay` y recibe solo el destino de esa sesión.

Antes de usarlo con público, ejecutar el [ensayo real de ambas direcciones y el
rollback](BIDIRECTIONAL_MVP_REPORT.md#validación-física-posterior-no-ejecutada).
Las pruebas automatizadas no certifican calidad médica ni la inferencia física EN.

## Lanzador unificado del MVP

El arranque diario actual está en [LAUNCHER_MVP.txt](LAUNCHER_MVP.txt).
Desde `C:\live-captions`: `.\Start-TRAD.ps1`. Para comprobar servidores, glosario
y overlay sin captura ni traducción: `.\Start-TRAD.ps1 -Action Test`.
La publicación mantiene Operator en loopback y permite cualquier visor que alcance
la IP local, con perfil Public o Private. La IP receptora es opcional; el lanzador
abre solo TCP 3000 para el overlay y no cambia el perfil de Windows.
La interfaz aparece como `Microphone (USB AUDIO DEVICE)` en el selector de entrada.
