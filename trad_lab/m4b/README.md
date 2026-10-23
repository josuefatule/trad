# M4-B: diagnóstico físico aislado

Corrección CDP posterior al intento 01: `Page.enable` es obligatorio antes de
registrar scripts. En targets pausados se encolan instalación y resume antes de
esperar respuestas, evitando bloquear `window.open`. `guard.js` bloquea START y
el acceso al micrófono hasta verificar observadores/DOM y ACK real del writer.
Los popups con opener pueden ejecutar esos scripts en `about:blank` y reutilizar
el contexto. `ensure_document` instala entonces en el documento efectivo, con
inicialización DOM tardía e idempotente. El propietario retiene `capture_ready`
hasta la aprobación CDP de CAPTURE. Solo después de ambos ACK se reserva un claim
y se libera un MessageEvent nuevo con los mismos source/origin/data/ports al
manejador operativo, evitando reutilizar las marcas de propagación del evento
retenido. No se copian ni registran
sus credenciales. Ver secciones 14/15 del informe y las reservas de prueba física.

Validación real sin audio (servidor TRAD 18010, sin WLK ni modelos cargados):
`python -m trad_lab.m4b.validate_cdp --plan PLAN --out NUEVO_DIRECTORIO_PRIVADO`.
Este comando exige los cuatro puertos libres, inicia/cierra solo sus procesos,
mantiene START bloqueado aun después de validar y prohíbe micrófono/reproducción.
Comprueba Operator, popup con opener y vínculo de propietario reales, instalación
en el documento efectivo, retención de `capture_ready`, rechazo sin audio y
recarga. También prueba la liberación del evento: el `capture_start` normal es
interceptado por una guarda independiente antes del manejador de sesión del
hijo. No pulsa START ni abre micrófono, AudioContext, sesión o PCM. Los resultados
distinguen ese intercambio interceptado de una captura física. No consume claims.
Necesita autorización específica; no equivale a permiso para reanudar captura.

Revisión de esta corrección (conserva los claims 01/02 sin reiniciar presupuesto):
`C:/live-captions/logs/trad_lab/m4b_openerfix_20261020T161600Z/environment_opener_ready/plan.json`.
No reutilizar `environment_ready` para una futura captura: conserva la versión
anterior como evidencia. Queda un intento, pendiente de autorización supervisada
posterior a la entrega de la validación sin audio.

Primera entrega: herramientas preparadas; **no arrancar servicios ni captura sin
autorización específica M4-B**, hasta tres intentos, sin reutilizar M3/M4.
Informe principal: `C:/live-captions/S2-M4B-PHYSICAL-DIAGNOSTIC.md`.

No modifica `app/`. `prepare` congela copias de app/glosarios/laboratorio bajo
`logs/trad_lab`, excluido de Git. Cambia únicamente el worklet de esa copia para
añadir metadata. El worker baseline, protocolo y muestras permanecen originales.
`browser.js` se instala mediante CDP antes de scripts del Operator/CAPTURE
experimental. Chrome visible, micrófono real, START/STOP manuales.

## Preparación sin servicios

```powershell
Set-Location C:\live-captions
.\.venv-wlk\Scripts\python.exe -m trad_lab.m4b prepare --out logs\trad_lab\m4b_ejemplo\environment
& 'C:\Program Files\nodejs\node.exe' trad_lab/m4b/test_signal.cjs
& 'C:\Program Files\nodejs\node.exe' trad_lab/m4b/test_browser.cjs
.\.venv-wlk\Scripts\python.exe -m unittest tests.test_trad_lab_m4b -v
```

Usar directorios nuevos. No reconstruir encima de evidencia ni extraer ZIP sobre
LIVE. El socketpair interno de asyncio puede necesitar permiso del sandbox de
Windows para los tests; no representa un servicio experimental arrancado.

## Después de autorización expresa

El informe fija el plan congelado de esta entrega. El texto del argumento es una
interlock deliberada de CLI, **no sustituye** autorización humana. Comprobar
8000/8010/18000/18010 y procesos GPU. El usuario cierra LIVE tras STOP completo.
No ejecutar benchmarks mientras WLK está cargado.

Terminal 1, .venv-wlk: `python -m trad_lab.m4b serve wlk --plan PLAN --authorization "M4-B aprobado hasta 3 sesiones"`.
Terminal 2, .venv: igual con `serve trad`. El launcher impide usar puertos LIVE,
limpia credenciales heredadas, fija DeepL OFF y verifica la copia por hashes.
Mantener ambas terminales para cerrar exclusivamente sus procesos con Ctrl+C.

Terminal 3, .venv-wlk:
`python -m trad_lab.m4b capture --plan PLAN --out NUEVO_DIRECTORIO_PRIVADO --authorization "M4-B aprobado hasta 3 sesiones"`.
Consume un intento mediante claim exclusivo después de preparar ambos documentos;
un popup fallido antes de ese punto no consume el intento. Máximo tres por plan,
conservando siempre los claims históricos al derivar una revisión. Cada colector
admite una sola sesión. Dos repeticiones físicas; tercero solo contingencia.

1. En Chrome visible, permitir micrófono/popups, actualizar dispositivos, elegir
   **Blue Yeti** y **English → Español**. Seleccionar el MP3 original cardio_01.
2. START normal. Mantener CAPTURE abierta. El indicador exige flujo PCM; esperar
   cinco segundos. El botón solo permite reproducir si el SHA del MP3 es correcto.
3. Reproducir desde el panel: 0–100 s. Mismo altavoz, salida de sistema, volumen,
   distancia, orientación, patrón y ajustes de Windows/Yeti. Anotar esos valores.
4. Esperar cinco segundos tras finalizar. Probar CLEAR en ese postroll si se desea;
   no cambia audio ni RAW. STOP normal del propietario y esperar cierre completo.
5. El colector exige propietario, sesión cerrada y drenaje del logger antes de
   cerrar su Chrome. Si falla, deja Chrome abierto para STOP normal y conserva
   evidencia parcial; **no volver a START** en ese navegador.
6. Repetir con otro colector/directorio y las mismas condiciones. Ante CUDA OOM,
   detener intento y guardar evidencia; no cambiar paquetes, modelo o precisión.

Ese procedimiento 0–100 s es el diseño inicial. La condición vigente solicitada
por el usuario es 0:10–2:00 (110 s), desde dispositivo externo/Bose, con cinco
segundos de preroll/postroll; el MP3 local solo verifica identidad y **no se
reproduce en paralelo desde el panel**. Mantener esa condición en una futura
sesión autorizada; no atribuirle timestamps de `playing` del navegador.

No minimizar las superficies al evaluar render. rAF es oportunidad de pintado,
no medida física de pantalla. El overlay M4-B muestra READY inglés en Operator;
no es el overlay traducido de OBS ni tiene sus contratos visuales. El overlay
operativo no recibe traducciones con DeepL OFF. Las regresiones cubren su contrato.

## Análisis posterior, sin servicios GPU concurrentes

Cada conexión genera `environment/trad_wire/wire_NN` y
`environment/wlk_wire/wire_NN`. Emparejar por orden/hashes y session_id, **no asumir
NN** si hubo rechazo o conexión fallida. Los writers deben haber cerrado.

```powershell
.\.venv-wlk\Scripts\python.exe -m trad_lab.m4b analyze --capture CAPTURA --trad WIRE_TRAD --wlk WIRE_WLK
.\.venv-wlk\Scripts\python.exe -m trad_lab.m4b align --capture CAPTURA
& 'C:\Program Files\nodejs\node.exe' trad_lab/m4b/replay.cjs CAPTURA/browser/pre.f32le CAPTURA/browser/events.jsonl COPIA/app/static/recorder_worker.js CAPTURA/replay
```

`analyze` comprueba orden, frames, EOF, SHA por bloque/total, PCM exacto en tres
puntos, continuidad worklet y STOP. Exporta `sent_pcm.wav` y un derivado de escucha
`pre_listening_s16.wav`; el f32 original sigue siendo autoritativo. `align` compara
anchors MP3/pre; correlación baja es inconclusa, no prueba de defecto acústico.
`replay` reproduce particiones exactas por el worker original y el candidato.

Con ambos servicios cerrados, `python -m trad_lab.m4b offline --capture CAPTURA
--out NUEVO_DIRECTORIO_PRIVADO` compara small float16/beam5 en los dos PCM con
perfil idéntico. Rechaza si el replay original difiere del enviado. No calcula
WER de exactitud: requiere validar referencia exacta, preroll/postroll y bordes.
Los ratios entre hipótesis se identifican como discrepancias, no verdad clínica.

## Límites y privacidad

Worklet: solo copia/metadata mediante MessagePort, sin I/O de disco. Cola navegador
8 MiB + paquete en vuelo <180 k caracteres; un paquete requiere ACK tras escritura.
Timeout ACK 5 s. Escritor: cola de 32 paquetes, máximo 256 KiB por paquete y
160 MiB de JSON por writer; fallo invalida captura, sin sustituir audio. Telemetría
GPU: máximo 600 filas. Sesión/colector: 240 s incluyendo preparación manual.

Taps ASGI conservan bytes tras aceptación, sin scope, headers, URL/query, cookies
ni subprotocolos. Se filtran claves sensibles del payload. No publicar logs,
audio, transcripciones, perfiles ni `.runtime` de la copia. El perfil Chrome
temporal contiene la autorización normal; se retira al terminar correctamente.
Si queda bloqueado/incompleto, cerrar normalmente antes de retirar solo ese perfil.

El remuestreador usa integración rectangular con fase racional entera: invariancia
de partición en 48/44.1/16 kHz. EOF emite una celda parcial normalizada, informa su
cobertura y prohíbe doble EOF. Duración cuantizada por exceso <1 muestra de 16 kHz.
No es un filtro de calidad auditiva demostrado ni un candidato aprobado para LIVE.
