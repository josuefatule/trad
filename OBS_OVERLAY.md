# Overlay inglés para OBS — M5

## Probar sin voz ni DeepL

Arrancar FastAPI y abrir http://localhost:8010/overlay/preview. Pulsar **Play demo**.
Debe verse DEMO en la parte superior, frases inglesas, Unicode y un texto largo
dividido en bloques sucesivos. Reset session limpia el caption inmediatamente.
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
    oscura. STOP termina los resultados pendientes; la última cola se lee y desaparece.

Referencia de propiedades: [OBS Browser Source](https://obsproject.com/kb/browser-source).
No se requiere OBS SDK ni plugin adicional. No se instala ni configura OBS automáticamente.

## Configuración

Variables opcionales en .env, leídas al arrancar FastAPI:

| Variable | Inicial | Rango / significado |
| --- | ---: | --- |
| CAPTION_MAX_LINES | 2 | 1–4 líneas por bloque visible |
| CAPTION_FONT_SIZE | 48 | 16–96 px |
| CAPTION_MAX_WIDTH | 1500 | 240–3840 px; se limita al viewport |
| CAPTION_POSITION | bottom | bottom, center, top |
| CAPTION_BOTTOM_OFFSET | 70 | 0–1000 px; también margen superior en top |
| CAPTION_BACKGROUND_OPACITY | 0.72 | 0–1; 0 elimina fondo |
| CAPTION_MIN_DISPLAY_MS | 1800 | 300–10000 ms |
| CAPTION_MAX_DISPLAY_MS | 6500 | 500–30000 ms; debe ser ≥ mínimo |
| CAPTION_READING_WPS | 3 | 1–8 palabras/s |
| CAPTION_VISUAL_QUEUE_MAX | 64 | 1–256 bloques pendientes |
| CAPTION_MAX_BACKLOG_MS | 20000 | 1000–120000 ms de atraso visual |

Excepto visual_queue_max, se pueden sobrescribir por URL usando nombres en minúscula
sin CAPTION_: max_lines, font_size, max_width, position, bottom_offset,
background_opacity, min_display_ms, max_display_ms, reading_wps, max_backlog_ms.
Todos se validan con los mismos rangos. Parámetros desconocidos o valores inválidos
producen 400 al cargar configuración y el overlay queda invisible; detalle en consola.

Ejemplo sin fondo y fuente de 54 px:

http://localhost:8010/overlay?font_size=54&background_opacity=0&bottom_offset=90

El texto blanco con sombra es fijo. No se permite CSS/código arbitrario ni secretos
en URL. Los límites de lectura son experimentales, no una afinación definitiva.

## Qué sucede con el texto

Un segmento traducido puede necesitar varios bloques de dos líneas; todos se
presentan en orden. No se inventa puntuación, no se insertan HTML y no se vuelve a
traducir. Se colapsa whitespace solo para presentación. La lectura dura palabras/3
segundos, acotada a 1,8–6,5 s por bloque. Una pausa termina por dejar la pantalla vacía.

Ante saturación se descartan primero bloques pendientes antiguos, nunca el que está
leyéndose. Los descartes se cuentan y registran. La cola admite 64 bloques y 20 s
de duración acumulada; un bloque esperando más de 20 s también vence. No es una
garantía de presentación íntegra bajo sobrecarga; sí evita ocultar overflow
silenciosamente. Captions >20.000 caracteres o tokens que exijan fuente <8 px se
rechazan con diagnóstico explícito. Cambiar el tamaño del viewport limpia la cola
medida previamente y registra el descarte.

Reconectar no recupera historial: solo el último caption vigente y el estado actual.
La caducidad del snapshot es max_display_ms desde su publicación. Una reconexión en
la misma página no repite secuencias aceptadas; actualizar la página puede recuperar
el caption todavía vigente. Tras desconexión/error fatal se limpia de inmediato.

## Diagnóstico y primera lectura real

- Reiniciar FastAPI después de actualizar Python/configuración, con el micrófono detenido.
- Recargar /operator con Ctrl+F5 y comprobar Translator: Ready (deepl).
- Abrir /overlay antes de START. En Operator → Overlay / OBS diagnostics debe
  aumentar overlay connections. Cada overlay adicional comparte la misma traducción.
- Leer varias frases, hacer una pausa, probar una frase larga y STOP.
- Comprobar RAW/NORMALIZED/ENGLISH en Operator y el mismo inglés en OBS.
- Verificar que START nuevo no conserve texto anterior y que cerrar el Operator
  durante captura deje el overlay vacío.
- Si no se ve texto, revisar translator state, last caption, broadcast errors,
  display drops y filtered mock. Un mock se filtra en el overlay público.

Pruebas sin credenciales: `python -m unittest discover -s tests -v` con
TRANSLATION_ENABLED=0; `node tests/test_overlay_renderer.cjs` y
`node tests/test_operator_partial.cjs` para DOM y reloj simulado.

No usar varios workers Uvicorn. El hub es local al proceso y no persiste historial.
Mantener FastAPI escuchando en 127.0.0.1; el producto no añade autenticación remota.
