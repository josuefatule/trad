# Overlay inglés para OBS — M5.1

## Probar sin voz ni DeepL

Arrancar FastAPI y abrir http://localhost:8010/overlay/preview. Pulsar **Play demo**.
Debe verse DEMO en la parte superior, frases inglesas, Unicode y un texto largo
incorporado inmediatamente a las últimas tres líneas. Una pausa no borra el texto.
STOP demo limpia después de ocho segundos; Reset session limpia inmediatamente.
El demo no conecta WLK ni usa DeepL, incluso si .env contiene una clave válida.
El fondo de preview es azul intencionadamente; el overlay público es transparente.

## OBS Studio

1. Arrancar WhisperLiveKit y FastAPI como indica README.md.
2. En OBS, en Sources/Fuentes pulsar + y crear **Browser / Navegador**.
3. Desactivar **Local file / Archivo local**.
4. URL: **http://localhost:8010/overlay**.
5. Width/Ancho **1920**, Height/Alto **1080** para composición Full HD.
6. Colocar esta fuente por encima de diapositivas/video en la lista de fuentes.
7. Mantener el CSS transparente predeterminado de OBS; la página también fija
   html/body transparentes y queda completamente invisible sin texto.
8. Para conservar la cola al cambiar de escena, dejar desactivados **Shutdown source
   when not visible** y **Refresh browser source when scene becomes active**.
9. Abrir /operator en Chrome/Edge, elegir Blue Yeti, START y hablar. El overlay
   muestra solo la traducción inglesa real. No pulsar START desde otra pestaña.
10. Verificar transparencia, orden y legibilidad sobre una diapositiva clara y otra
    oscura. STOP termina los resultados pendientes y limpia ocho segundos después.

Referencia de propiedades: [OBS Browser Source](https://obsproject.com/kb/browser-source).
No se requiere OBS SDK ni plugin adicional. No se instala ni configura OBS automáticamente.

## Configuración

Variables opcionales en .env, leídas al arrancar FastAPI:

| Variable | Inicial | Rango / significado |
| --- | ---: | --- |
| CAPTION_MODE | persistent_rolling | persistent_rolling o timed_queue |
| CAPTION_MAX_LINES | 3 | 1–3 líneas; usar 2 si se prefiere |
| CAPTION_STOP_CLEAR_MS | 8000 | 0–120000 ms después de STOP |
| CAPTION_FONT_SIZE | 48 | 16–96 px |
| CAPTION_MAX_WIDTH | 1500 | 240–3840 px; se limita al viewport |
| CAPTION_POSITION | bottom | bottom, center, top |
| CAPTION_BOTTOM_OFFSET | 70 | 0–1000 px; también margen superior en top |
| CAPTION_BACKGROUND_OPACITY | 0.72 | 0–1; 0 elimina fondo |
| CAPTION_MIN_DISPLAY_MS | 1800 | Solo timed_queue; 300–10000 ms |
| CAPTION_MAX_DISPLAY_MS | 6500 | Solo timed_queue; 500–30000 ms; ≥ mínimo |
| CAPTION_READING_WPS | 3 | Solo timed_queue; 1–8 palabras/s |
| CAPTION_VISUAL_QUEUE_MAX | 64 | Solo timed_queue; 1–256 bloques |
| CAPTION_MAX_BACKLOG_MS | 20000 | Solo timed_queue; 1000–120000 ms |

Excepto visual_queue_max, se pueden sobrescribir por URL usando nombres en minúscula
sin CAPTION_: mode, max_lines, stop_clear_ms, font_size, max_width, position, bottom_offset,
background_opacity, min_display_ms, max_display_ms, reading_wps, max_backlog_ms.
Todos se validan con los mismos rangos. Parámetros desconocidos o valores inválidos
producen 400 al cargar configuración y el overlay queda invisible; detalle en consola.

Ejemplo sin fondo y fuente de 54 px:

http://localhost:8010/overlay?font_size=54&background_opacity=0&bottom_offset=90

El texto blanco con sombra es fijo. No se permite CSS/código arbitrario ni secretos
en URL. Los límites de lectura son experimentales, no una afinación definitiva.

## Qué sucede con el texto

En persistent_rolling cada traducción se añade en orden al texto visible, con wrapping
medido por palabras. No se inserta un salto por segmento READY. Las líneas antiguas
salen conforme se llena el espacio. No hay cola visual ni timers de lectura durante
LIVE: retener texto no retrasa el siguiente caption. Se preserva puntuación y se usa
textContent. Una pausa prolongada conserva el texto; STOP inicia el timer de limpieza.
START, desconexión o error fatal limpian inmediatamente; el estado queda en Operator.

Un caption largo puede superar él solo la ventana visible: se conserva su cola y se
registra rolling_overflow por las palabras nuevas que salieron antes de mostrarse.
El desplazamiento normal de líneas ya visibles se cuenta aparte como rolled-out lines.
Captions >20.000 caracteres o tokens que exijan fuente <8 px se rechazan explícitamente.
Resize vuelve a medir las palabras retenidas sin vaciar la ventana. Llegadas en el
mismo frame pueden compartir un solo pintado: coalesced DOM updates indica ese caso;
no garantiza que cada actualización DOM aparezca individualmente en el vídeo de OBS.

Reconectar reconstruye la ventana desde un historial acotado a 128 captions y
20.000 caracteres de la sesión vigente. No caduca por una pausa LIVE. Después de
STOP el snapshot deja de ofrecer texto al terminar CAPTION_STOP_CLEAR_MS del backend.
La restauración reemplaza la ventana, sin duplicar texto; no se mide como entrega
de un caption nuevo. Si se sobrescribe stop_clear_ms por URL, el período de snapshot
al reconectar sigue limitado por la configuración del backend.

El modo anterior sigue disponible con CAPTION_MODE=timed_queue o ?mode=timed_queue.
Conserva la paginación/cola de lectura y sus límites: puede añadir espera o descartar
bloques ante saturación. No es el modo predeterminado de M5.1.

## Latencias: qué significa cada cifra

Operator muestra ASR first appearance → READY, READY → normalización, READY → inicio
traducción, demora/depth de TranslationQueue, duración del provider y publicación Hub.
Son duraciones monotónicas del mismo proceso. La duración del provider incluye el
adaptador/thread/red, no un cronómetro independiente de paquetes HTTP de DeepL.

Browser Source mide recepción → DOM y recepción → doble requestAnimationFrame.
El segundo es una estimación de oportunidad de pintado, no una observación de la
composición/encoder/salida física de OBS. Una sincronización WebSocket periódica
permite estimar Hub → recepción y READY → visible con incertidumbre derivada del RTT
y de la resolución del reloj backend (15,625 ms en este Windows);
sin sincronización reciente se muestra not measured. La asimetría de red, deriva de
reloj y buffering de OBS siguen siendo limitaciones. No se restan relojes sin anclarlos.

No se mide todavía voz física/captura → primera aparición ASR. El diagnóstico
ASR first appearance → visible comienza al recibir el contenido, no al pronunciarlo.
Ver [MILESTONE_5_1_REPORT.md](benchmarks/MILESTONE_5_1_REPORT.md).

## Diagnóstico y primera lectura real

- Reiniciar FastAPI después de actualizar Python/configuración, con el micrófono detenido.
- Recargar /operator con Ctrl+F5 y comprobar Translator: Ready (deepl).
- En OBS, Refresh cache of current page para cargar protocolo overlay v2 y M5.1.
- Abrir /overlay antes de START. En Operator → Overlay / OBS diagnostics debe
  aumentar overlay connections. Cada overlay adicional comparte la misma traducción.
- Leer 20–30 segundos, hacer una pausa de 10 segundos y comprobar que el texto permanece.
- Leer varias frases seguidas; verificar renderer delay cercano a cero y visual queue 0.
- STOP: el último texto debe permanecer ocho segundos después del drain y desaparecer.
- Comprobar RAW/NORMALIZED/ENGLISH en Operator y el mismo inglés en OBS.
- Verificar que START nuevo no conserve texto anterior y que cerrar el Operator
  durante captura deje el overlay vacío.
- Si no se ve texto, revisar translator state, last caption, broadcast errors,
  display drops y filtered mock. Un mock se filtra en el overlay público.

Pruebas sin credenciales: `python -m unittest discover -s tests -v` con
TRANSLATION_ENABLED=0; `node tests/test_overlay_renderer.cjs` y
`node tests/test_operator_partial.cjs` para DOM y reloj simulado.
Persistencia/reconexión/reloj: `node tests/test_persistent_captions.cjs`.

No usar varios workers Uvicorn. El historial acotado solo existe en memoria del proceso.
Mantener FastAPI escuchando en 127.0.0.1; el producto no añade autenticación remota.
