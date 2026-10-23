# TRAD-LAB (S2-M3)

Laboratorio local y aislado para reconocimiento médico inglés. No modifica
`app/`, glosarios operativos, `.env`, servicios, dependencias ni referencias Git.
No usa DeepL ni publica corpus. Los resultados privados se guardan bajo `logs/`.

## Entorno y protección

Ejecutar desde `C:\live-captions` con `.venv-wlk\Scripts\python.exe` (Python
3.12.10, Faster-Whisper 1.2.1, CTranslate2 4.8.2, PyAV 19.0.1 observados).
La aplicación conserva su propio `.venv`. No ejecutar pip ni actualizar paquetes.
El worker antepone torch/lib solo en su entorno de proceso para resolver CUDA.

Antes de inferencia, TRAD en 8010 debe estar completamente detenido. El padre
consulta el estado autorizado por loopback y cancela **solo su worker** si aparece
STARTING/LIVE/STOPPING o un estado no verificable. No envía STOP a producción.
No guardar tokens ni secretos; el guard conserva su token solo en memoria.
Un watchdog limita cada worker (incluida descarga) a 1800 s por defecto.

## Benchmark reproducible

```powershell
Set-Location C:\live-captions
$env:PYTHONIOENCODING='utf-8'
$env:HF_HUB_DISABLE_TELEMETRY='1'
$env:HF_HUB_DISABLE_XET='1'
.\.venv-wlk\Scripts\python.exe -m trad_lab evaluate --corpus C:\TRAD-LAB\corpus --out logs\trad_lab\nueva-evaluacion --glossary C:\Users\JF\Downloads\medical_base_en_tolerancias_v2.json --models small medium large-v3-turbo --allow-download --with-context
```

`--allow-download` autoriza únicamente pesos públicos faltantes en la caché HF,
no instalación de paquetes. Omitirlo exige modelos ya disponibles. Se hace una
comprobación previa de soporte float16 CUDA y una reserva conservadora de VRAM
(small 1800, medium 4000, turbo 6000 MiB libres); son umbrales de planificación,
no cifras medidas de consumo. Un fallo se registra como bloqueo, sin cambiar
versiones, tipos de cómputo ni modelo operativo. Medium/turbo no se ejecutan hasta
completar small. Cada modelo se carga en un proceso separado y los tres corpus
se procesan secuencialmente, sin solapar inferencia de modelos.

Una ejecución debe usar un directorio nuevo. `--resume` verifica hashes de los
originales, perfil y glosario; reutiliza modelos completos y archiva intentos
fallidos/interrumpidos bajo `attempts/`. No sobrescribe inferencias completas.
Un checkpoint de código no incluye los entornos ni sustituye un lock de wheels.

Perfil común: CUDA float16, inglés explícito, transcribe, beam 5, best_of 5,
temperature 0, contexto de transcripción previo activado, sin VAD, word timestamps.
La carga y warmup (0.5 s de ceros) están separados del cronómetro ASR. Se consume
el generador completo. RTF = tiempo ASR / duración del audio. Una única pasada
no demuestra estabilidad térmica ni rendimiento de una conferencia LIVE.

Cada muestra/modelo conserva JSON, Markdown, hipótesis sin normalizar,
referencia original byte a byte, segmentos/palabras y tiempos. `environment.json`
registra versiones, parámetros y SHA-256 de los pesos; `gpu_samples.json` muestrea
VRAM total del dispositivo cada 2 s. Incluye Windows/otros procesos y puede perder
picos breves; no es memoria exacta del proceso CT2. `SUMMARY.md` y `summary.json`
agregan por denominador total, sin promediar WER de muestras de tamaño desigual.

## Normalización, riesgos y glosario

WER: Levenshtein exacto por palabras; CER: Levenshtein exacto sobre texto
normalizado, con espacios únicos incluidos. NFKC + casefold; apóstrofes curvos
unificados; puntuación e hífenes separan palabras; números mantienen decimal,
coma y barra internos. No se convierten números escritos a dígitos ni unidades,
no se eliminan palabras de la referencia y no se aplica glosario al texto de
referencia. Texto original y normalizado se conservan por separado. Referencia
vacía con hipótesis no vacía produce WER/CER indefinidos, no una precisión falsa.
La puntuación principal puede omitir signos clínicos como menos, desigualdades
o porcentaje. Un canal adicional de firmas numéricas del texto crudo registra
esas diferencias, aun con WER cero; son alertas de revisión, no validación de dosis.

Las referencias TurboScribe son provisionales y revisadas por el usuario; no
ground truth clínicamente certificado. Señales de negación, cifras, unidades,
medicamentos y polaridad se marcan sobre alineamientos S/D/I. Son candidatos a
revisión, con cobertura limitada y falsos positivos (por ejemplo, “second”).
Los contextos de dosis/medición se detectan por proximidad léxica de número/unidad.
El déficit de términos cuenta formas exactas canónico/alias/variante; puede
solapar conceptos y no constituye un conteo certificado de errores médicos.

`glossary_audit.json` prueba el loader real y busca colisiones exactas y pares
canónicos similares. Ese screening fuzzy no demuestra que el matcher runtime
admita una sustitución. Exactos/aliases se aplican con confidence 1 sin depender
de auto_threshold; la ruta de términos partidos puede elevar confidence hasta
el umbral. Un 0.99 no es una probabilidad calibrada ni garantía de seguridad.

`post_glossary.json` contiene una salida candidata **no aprobada**, su efecto en
WER/CER y todas las correcciones/sugerencias. La salida controlada admite solo
spacing, dejando todo reemplazo terminológico pendiente de revisión humana.
El glosario no se activa en LIVE. El experimento `small-context` usa únicamente
`initial_prompt`, soportado por el Faster-Whisper instalado: los primeros 30
canónicos, máximo 160 tokens, iguales para todas las muestras, sin seleccionarlos
por la referencia. Se reporta separado y no se mezcla con el ranking baseline.
No se asume soporte de contexto en el WLK instalado.

## Comparación streaming: requiere autorización antes de iniciar servicios

El colector no inicia servidores. Antes de lanzar los dos comandos siguientes
obtener autorización explícita y comprobar que producción esté detenida.
No usar 8000/8010 ni modificar `.env`. Usar el clip derivado registrado en
`streaming_plan/plan.json`, o preparar otro WAV mono s16 16 kHz sin tocar MP3.

Terminal WLK dedicada (PATH CUDA temporal, restaurado al salir):

```powershell
$previousPath=$env:PATH
try {
  $env:PATH="C:\live-captions\.venv-wlk\Lib\site-packages\torch\lib;$previousPath"
  .\.venv-wlk\Scripts\python.exe -m trad_lab.wlk_probe_server --backend faster-whisper --model small --lan en --pcm-input --host 127.0.0.1 --port 18000 --warmup-file RUTA_AL_CLIP.wav
} finally { $env:PATH=$previousPath }
```

Otra terminal dedicada, sin credenciales ni traducción real:

```powershell
$env:TRANSLATION_ENABLED='0'
$env:WLK_WS_URL='ws://127.0.0.1:18000/asr'
$env:CAPTIONS_LOG_RAW='0'
$env:CAPTIONS_LOG_DIR='logs/trad_lab/servidor-aislado'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 18010
```

No fijar un contexto terminológico WLK no validado. El probe server comparte
modelo/configuración de arranque del MVP y añade evidencia **del decoder ya
construido**: idioma cfg/tokenizer/decode_options, modelo, dtype/dispositivo,
beam y encoder. No edita el paquete ni archivos operativos y se restringe a 18000.

Con esos servicios autorizados, ejecutar el colector:

```powershell
.\.venv-wlk\Scripts\python.exe -m trad_lab stream-capture --audio RUTA_AL_CLIP.wav --out logs/trad_lab/nueva-captura
```

Abre Chrome/Edge headless con archivo de audio sintético y usa el Operator y
CAPTURE **sin modificar**, con localhost/origen/nonce/propietario/capacidades.
START, CLEAR y STOP pasan por los controles normales; el capturador CDP solo
observa frames, omite headers de autorización y conserva PCM efectivamente
enviado, RAW WLK y READY. Exige configuración inglesa/PCM/full y EOF. No usa una
conexión WLK directa que eluda el contrato de la aplicación.

El clip de 60 s **no se puntúa contra la referencia de toda la conferencia**.
Omitir `--reference` significa comparar hipótesis, sin WER de exactitud clínica.
Una referencia nueva del fragmento debe revisarse antes de evaluar su precisión.
Al terminar, cerrar únicamente estos procesos del laboratorio, después de STOP.

Después, con WLK/TRAD de laboratorio cerrados y producción inactiva:

```powershell
.\.venv-wlk\Scripts\python.exe -m trad_lab same-pcm --capture logs/trad_lab/nueva-captura --source RUTA_AL_CLIP.wav --glossary C:\Users\JF\Downloads\medical_base_en_tolerancias_v2.json --out logs/trad_lab/nuevo-diferencial
```

El mismo perfil offline small procesa tanto el clip fuente como el **PCM exacto
enviado por CAPTURE**. `differential.json` compara: offline original → offline
capturado (frente de audio); offline capturado → WLK RAW (camino ASR/streaming);
WLK RAW → READY (segmentación/ensamblaje). Ratios de discrepancia entre hipótesis
no son WER clínico. La ubicación de una diferencia no acredita su causa raíz.

Si no se autoriza iniciar servicios, entregar el plan y marcar ese gate pendiente;
no atribuir por descarte el fallo LIVE a small, WLK, idioma ni audio.

## Pruebas y checkpoint

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_trad_lab -v
```

Las pruebas no necesitan GPU/red. Comprueban distancia exacta contra DP
independiente, vacíos, cifras/negaciones/dosis, colisiones/glosario, preservación
de entradas, bloqueo LIVE y contrato RAW/READY/handshake de capturas sintéticas.
La captura real autorizada del 20 de octubre terminó con STOP/EOF completo,
sin DeepL, y comparación sobre el PCM enviado. Ver `TRAD_LAB_REPORT.md` y los
artefactos allí enlazados. Los tests sintéticos no sustituyen esa evidencia.

El checkpoint inicial está en la ruta registrada en `logs/trad_lab/LATEST_RUN.txt`:
`checkpoint.zip` + `checkpoint.json` con SHA-256, manifiesto de 129 archivos,
HEAD, estado Git y diff. No contiene `.env`, `.runtime`, venvs, caches ni secretos.
Para recuperar, extraer primero en un directorio vacío, verificar manifiesto y
restaurar solo archivos elegidos tras revisar cambios posteriores. No resetear
Git ni extraer directamente sobre trabajo nuevo. No se crearon commits/tags.
