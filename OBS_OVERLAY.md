# Overlay inglés para OBS — M5.1

## Probar sin voz ni DeepL

Arrancar FastAPI y abrir http://localhost:8010/overlay/preview. Pulsar **Play demo**.
Debe verse DEMO en la parte superior, frases inglesas, Unicode y un texto largo
incorporado inmediatamente a las últimas líneas que caben en la región. Una pausa no borra el texto.
STOP demo limpia después de ocho segundos; Reset session limpia inmediatamente.
El demo no conecta WLK ni usa DeepL, incluso si .env contiene una clave válida.
El preview muestra todo el canvas 1920 × 1080 a escala: diapositiva clara arriba y
franja azul abajo. La franja y el borde discontinuo son ayudas exclusivas del preview;
el overlay público es transparente. El aviso de geometría indica las líneas solicitadas
y las que realmente caben sin reducir la fuente.

## OBS Studio

1. Arrancar WhisperLiveKit y FastAPI como indica README.md.
2. En OBS, en Sources/Fuentes pulsar + y crear **Browser / Navegador**.
3. Desactivar **Local file / Archivo local**.
4. URL: **http://localhost:8010/overlay**.
5. Width/Ancho **1920**, Height/Alto **1080** para composición Full HD.
6. Colocar esta fuente por encima de diapositivas/video en la lista de fuentes, con
   transformación sin recorte y posición (0, 0) sobre el canvas 1920 × 1080.
   Ajustar PowerPoint a Y=0–930 y la franja azul de OBS a Y=930–1080.
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
| CAPTION_MAX_LINES | 3 | 1–3 solicitadas; se limita a las que caben por altura |
| CAPTION_STOP_CLEAR_MS | 8000 | 0–120000 ms después de STOP |
| CAPTION_FONT_SIZE | 48 | 16–96 px |
| CAPTION_MAX_WIDTH | 1500 | 240–3840 px; limitado al ancho interior de la región |
| CAPTION_CANVAS_WIDTH | 1920 | 240–7680 px |
| CAPTION_CANVAS_HEIGHT | 1080 | 150–4320 px |
| CAPTION_REGION_X | 0 | Coordenada horizontal, 0–7680 px |
| CAPTION_REGION_Y | 930 | Coordenada vertical, 0–4320 px |
| CAPTION_REGION_WIDTH | 1920 | 80–7680 px; región completa dentro del canvas |
| CAPTION_REGION_HEIGHT | 150 | 40–4320 px; debe caber al menos una línea |
| CAPTION_PADDING_X | 32 | 8–200 px por lado; ancho interior mínimo 40 px |
| CAPTION_PADDING_Y | 8 | 8–200 px por lado; reserva espacio para sombra |
| CAPTION_LINE_HEIGHT | 1.2 | 1.1–1.6 veces el tamaño de fuente |
| CAPTION_POSITION | center | center, bottom, top; alineación **dentro** de la región |
| CAPTION_BOTTOM_OFFSET | 70 | Compatibilidad con URLs anteriores; no desplaza la nueva región |
| CAPTION_BACKGROUND_OPACITY | 0 | 0–1; 0 transparente, permite usar el azul de OBS |
| CAPTION_MIN_DISPLAY_MS | 1800 | Solo timed_queue; 300–10000 ms |
| CAPTION_MAX_DISPLAY_MS | 6500 | Solo timed_queue; 500–30000 ms; ≥ mínimo |
| CAPTION_READING_WPS | 3 | Solo timed_queue; 1–8 palabras/s |
| CAPTION_VISUAL_QUEUE_MAX | 64 | Solo timed_queue; 1–256 bloques |
| CAPTION_MAX_BACKLOG_MS | 20000 | Solo timed_queue; 1000–120000 ms |

Excepto visual_queue_max, se pueden sobrescribir por URL usando nombres en minúscula
sin CAPTION_, incluidos canvas_width, canvas_height, region_x, region_y, region_width,
region_height, padding_x, padding_y y line_height.
Todos se validan con los mismos rangos. Parámetros desconocidos o valores inválidos
producen 400 al cargar configuración y el overlay queda invisible; detalle en consola.

URL explícita para esta composición (también son los valores predeterminados):

http://localhost:8010/overlay?canvas_width=1920&canvas_height=1080&region_x=0&region_y=930&region_width=1920&region_height=150&position=center&background_opacity=0&mode=persistent_rolling&max_lines=3

Conservar fuente de **48 px** y line-height 1.2 implica 57.6 px por línea. Altura
interior: 150 − 2×8 = 134 px. Caben **dos líneas** (115.2 px), centradas entre
Y≈947.4 y Y≈1062.6; tres necesitarían 188.8 px incluyendo padding. No se reduce
la fuente automáticamente para conseguir tres líneas, ni se ocultan líneas con CSS.
Para pedir explícitamente dos, añadir `&max_lines=2`. Para elegir conscientemente
tres líneas en 150 px, una fuente de **36 px** cabe: 3×43.2 + 16 = 145.6 px;
añadir `&font_size=36&max_lines=3` y revisar legibilidad en el monitor de salida.
Otra opción es ampliar la franja y actualizar las diapositivas y la región juntas.

El wrapping se mide por palabras en coordenadas del canvas; CSS conserva exactamente
esos saltos, sin un segundo wrapping del navegador. La capacidad vertical se calcula
antes de renderizar, igual en OBS y preview. Si no cabe una sola línea o la región
sale del canvas, se rechaza la configuración con 400. Al cambiar el viewport se
escala el canvas completo proporcionalmente (con márgenes transparentes si cambia
su relación de aspecto); no se altera la fuente lógica ni el orden del texto.
Para OBS usar 1920 × 1080, evitando escalado accidental de la fuente Browser.

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
Resize conserva la ventana en el canvas lógico, escalando toda la composición. Llegadas en el
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
- En OBS, Refresh cache of current page para cargar protocolo overlay v3 y CLEAR de M6.
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
Geometría/capacidad/wrapping: `node tests/test_overlay_geometry.cjs`.
`tests/test_overlay_browser.py` prueba el DOM real y Canvas en Chromium/Chrome/Edge
headless con un perfil temporal: límites X/Y, centrado, padding, altura de líneas,
transparencia, fuente intacta, deduplicación y preview completo visible. Se omite si no existe ese navegador.
No conecta el micrófono ni usa DeepL; tampoco sustituye la comprobación visual en OBS.

No usar varios workers Uvicorn. El historial acotado solo existe en memoria del proceso.
Mantener FastAPI escuchando en 127.0.0.1; M6 autoriza mutaciones mediante nonce y
propietario local, sin autenticación remota ni cuentas.

## M6: limpieza manual desde Operator

START/STOP/CLEAR y diagnósticos están en `/operator`; ver [OPERATOR_CONSOLE.md](OPERATOR_CONSOLE.md).
CLEAR CAPTIONS vacía todos los overlays conectados y evita restaurar texto anterior
al reconectar. La siguiente publicación inglesa aparece normalmente. El historial
del Operator, el micrófono y DeepL siguen funcionando. El overlay es observador y
no puede emitir ese control. Se conserva persistent_rolling y la región Y=930–1080.
La consola muestra **Overlay clients: N**, no una afirmación de conexión OBS.

## Candidato v0.1: composición de conferencia y aceptación

No se modificó la escena OBS. En Settings → Video usar Base y Output 1920×1080.
En la escena, de abajo hacia arriba: fondo, captura PowerPoint, franja azul inferior
y Browser Source transparente. Reservar Y=930–1080 (150 px) o Y=900–1080 (180 px)
para captions; ajustar la presentación a la región superior **conservando aspecto**.
Una diapositiva 16:9 ajustada a altura 930 ocupa aproximadamente 1653×930, centrada;
el espacio lateral es preferible a deformar o tapar contenido.

Browser Source: URL `http://localhost:8010/overlay`, Width 1920, Height 1080.
Transform → Reset Transform y posición X=0/Y=0, sin crop ni escalado doble; bloquear
la fuente después de verificarla. No usar `/overlay/preview` para producción.
Conservar la fuente cargada entre cambios de escena: desactivar "Shutdown source
when not visible" y, si se busca continuidad, "Refresh browser when scene becomes active".
Tras actualizar el candidato, con sesión detenida, usar **Refresh cache of current page**.
No pegar CSS que añada fondo opaco o cambie geometría/fuente fuera de parámetros.

La URL sin parámetros utiliza la configuración backend auditada:
1920×1080, región 0/930/1920/150, padding 32/8, fuente 48, line-height 1.2,
max_width 1500, background_opacity=0 y persistent_rolling. Capacidad efectiva:
`floor((region_height - 2*padding_y)/(font_size*line_height))`, limitada a max_lines.
Con 150 px caben **dos** líneas de 48 px, aunque max_lines=3. A 180 px todavía
caben dos con esa fuente/interlineado. Para tres líneas a la altura original se
puede elegir explícitamente `?font_size=36` y verificar legibilidad; no se reduce
automáticamente la fuente para forzar tres. Alternativamente diseñar otra altura
que permita tres al tamaño deseado y reubicar la diapositiva. El preview completo
avisa de capacidad insuficiente y permite ensayar sin API/micrófono.

Para una franja de 180 px, usar de forma coherente región Y=900/height=180 en el
backend y en OBS, o URL `http://localhost:8010/overlay?region_y=900&region_height=180`.
Los parámetros no llevan secretos. Verificar región, wrapping, centrado y cola 0
con el guion médico. Abrir el proyector fullscreen de OBS en la segunda pantalla;
confirmar resolución, escala y que el escritorio del operador no esté proyectado.

CLEAR durante LIVE limpia sin detener audio; siguiente inglés reaparece. STOP
espera flush/drain y conserva la última ventana ocho segundos desde stopped.
Reconectar/recargar reconstruye solo la ventana vigente respetando CLEAR; si se
agotan los ocho intentos, recargar la fuente. Reiniciar backend pierde esa ventana.
No cerrar CAPTURE durante LIVE. El renderer puede coalescer cambios en un frame;
solo la prueba visual física acredita lo que realmente llegó al proyector.

M7 fue validado por el usuario con OBS real. La nueva aceptación del RC, incluido
ensayo de 60–90 min, queda **PENDIENTE** siguiendo
[MANUAL_VALIDATION_V0_1.md](MANUAL_VALIDATION_V0_1.md). Las pruebas Chrome validan
geometría y transporte, no el compositor de OBS ni la salida física.
