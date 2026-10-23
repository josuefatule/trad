# TRAD-LAB / M4

Código adicional aislado. Los fuentes y resultados de M3 y todos los componentes
operativos permanecen intactos. Consultar `C:\live-captions\S2-M4-ASR-DIAGNOSTIC.md`
para resultados, bloqueos y límites. Ningún candidato está aprobado.

Se usan solo recursos ya instalados y pesos small en caché. No ejecutar pip,
descargar modelos, cambiar `.env` ni iniciar servicios desde estos comandos.
El monitor consulta producción y aborta ante sesión activa/estado desconocido o
menos de 768 MiB libres. Las consultas y NVIDIA-SMI añaden tiempo al intervalo
nominal de muestreo de 1 s: usar los timestamps reales del JSON, no asumir 1 Hz.

## Reproducción

Desde una terminal de laboratorio dedicada, con producción detenida:

```powershell
Set-Location C:\live-captions
$env:PYTHONIOENCODING='utf-8'
$env:HF_HUB_OFFLINE='1'
$previousPath=$env:PATH
try {
  $env:PATH="C:\live-captions\.venv-wlk\Lib\site-packages\torch\lib;$previousPath"
  .\.venv-wlk\Scripts\python.exe -m trad_lab.m4 offline --clips RUTA\references\clips.json --out RUTA_NUEVA\offline --glossary glossaries\medical_base_en.json --repeats 3
  .\.venv-wlk\Scripts\python.exe -m trad_lab.m4 resampler --clips RUTA\references\clips.json --out RUTA_NUEVA\resampler_pair --glossary glossaries\medical_base_en.json --repeats 2
  .\.venv-wlk\Scripts\python.exe -m trad_lab.m4 local-agreement --clips RUTA\references\clips.json --out RUTA_NUEVA\local_agreement --glossary glossaries\medical_base_en.json --repeats 2
} finally {$env:PATH=$previousPath}
```

Cada salida debe ser nueva. No se sobrescriben inferencias ni resultados M3.
Para reproducir sin tocar el run original, copiar `references/` completo,
verificar los WAV/TXT y conservar su validación por hash; ajustar las rutas solo
si los bytes no cambian. El glosario se utiliza únicamente como inventario léxico,
sin reemplazos ni activación fuzzy.

`prepare-references --m3 RUTA_M3 --out CARPETA_NUEVA` deriva tres WAV mono s16
de los originales ya decodificados en M3. Nunca convierte ni sobrescribe los MP3
originales. Los TXT candidatos son oraciones exactas de las referencias del
usuario. Las marcas ASR ayudan a recortar, pero no certifican fronteras.
`reference_validation.json` empieza vacío; solo registrar aceptación tras una
respuesta humana y conservar hashes/alcance de esa aceptación. Sin ella los
resultados no incluyen WER/CER de exactitud.

Diagnóstico de forma de onda sin GPU:

```powershell
.\.venv-wlk\Scripts\python.exe -m trad_lab.m4 audio-diagnostic --source WAV_FUENTE --captured WAV_PCM_ENVIADO --out CARPETA_NUEVA
.\.venv\Scripts\python.exe -m trad_lab.m4 report --root RUTA_RUN_M4
```

El diagnóstico compara ventanas de 5 s por correlación FFT normalizada con
factores temporales 1 y 129/128; no usa transcripciones para estimar la deriva.
El umbral 0.55 es una heurística de ingeniería. No es una confianza médica ni
un detector exhaustivo de duplicación.

## Experimentos bloqueados y latencia

`simul` y `pipeline` están implementados para investigar el código WLK instalado,
pero **los intentos M4 se bloquearon por VRAM**, incluso beam 1. Se conserva un
OOM con abort nativo y dos abortos por reserva. No repetir como ensayo de
aceptación ni actualizar dependencias para forzarlos. Primero aislar la causa
del consumo; las diferencias entre harness, audio limpio y servidor real aún no
se resolvieron. Ningún resultado truncado participa en la tabla de WER.

`simul` reproduce chunks fijos sin VAC/VAD, red o DOM. `pipeline` usa AudioProcessor
completo y envío PCM a tiempo real en el mismo proceso, sin abrir un puerto.
Ninguno acredita latencia visible. `local-agreement` es una arquitectura alternativa
instalada, con CT2 auto/int8_float16 y confirmación entre hipótesis; no es una
comparación de una sola variable frente a offline float16 o AlignAtt.

El lag de compromiso es disponibilidad de audio menos el fin estimado de token
ASR; no es tiempo hasta pintado. La cola/DOM/OBS y DeepL quedan fuera.

## Prototipo de captura

`continuous_box.cjs` conserva fase entre bloques solo en 48 kHz→16 kHz. Mantiene
el promedio de tres muestras y el cuantizador del worker real en la simulación;
no añade ganancia, filtro nuevo ni modelo. Hasta dos muestras de entrada pueden
quedar como grupo incompleto al EOF; se informa explícitamente.

`resampler_pair.cjs` ejecuta el worker operativo en dos VM aisladas y sustituye
únicamente `resample()` dentro de la VM candidata. No escribe el worker ni altera
CAPTURE. El A/B parte de la misma señal sintética a 48 kHz obtenida del WAV
aceptado; omite AGC, dispositivo y temporización del navegador.

La corrección de duración no basta para aprobar seguridad clínica. Se conservan
WER/CER primarios y una sensibilidad secundaria post hoc para `%`/`percent` y
`stage one/two`/`stage 1/2`; esta última no es un criterio de aceptación ni corrige
las referencias originales.

## Pruebas sin inferencia

```powershell
.\.venv-wlk\Scripts\python.exe -m unittest tests.test_trad_lab tests.test_trad_lab_m4 tests.test_terminology_normalizer tests.test_segment_manager tests.test_release_validation
& 'C:\Program Files\nodejs\node.exe' trad_lab\m4\test_continuous_box.cjs
```

Usar el venv ASR existente permite ejecutar el test FFT con NumPy/SciPy; el venv
de aplicación omite ese test si no dispone de esas bibliotecas. No instalarlas
para eliminar el skip. Los tests reales M4 se ejecutaron en el venv ASR sin skips.
