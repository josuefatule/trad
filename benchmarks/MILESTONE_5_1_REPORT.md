# M5.1 — Persistent captions and latency diagnostics

Fecha: 2026-10-16. Baseline: 116 pruebas Python, overlay M5 validado en OBS por el
usuario. Este cambio no modifica WLK, thresholds/reconciliación del SegmentManager,
TerminologyNormalizer, glosarios ni DeepLProvider. SegmentManager solo expone el
origen monotónico para instrumentación; request/result añaden un timing frozen.

## Causas demostradas

- Desaparición: CaptionRenderer.advance programa 1800–6500 ms y, al vaciar la cola,
  llama hide. No era una pérdida de traducciones.
- Espera artificial: el caption nuevo se encola mientras otro tiene tiempo de
  lectura pendiente. Esa cola es independiente de TranslationQueue y puede añadir
  varios segundos incluso cuando DeepL ya respondió.
- Logs reales previos a M5.1 en proxy-startup.stderr.log:

| Sesión / muestras | ASR first appearance → READY, mediana / máx. | Provider, mediana / máx. | Normalización mediana |
| --- | ---: | ---: | ---: |
| c130fe169cae / 19 | 4406 / 5578 ms | 563 / 703 ms | 52,838 ms |
| 8dd0607988dd / 13 | 5531 / 5532 ms | 562 / 641 ms | 13,960 ms |

Son duraciones registradas por etapa. No se suman medianas como si fueran la
mediana end-to-end. Los logs M5 no contienen el tiempo en el renderer, por lo que no
permiten atribuir los ~10 s percibidos a una cifra exacta. Voz/captura → primera
aparición ASR y salida final de OBS siguen sin medirse.

## Política nueva

persistent_rolling es el predeterminado: tres líneas, configurable a dos. Cada
traducción nueva se incorpora en su callback, sin esperar timers previos. La cola
visual es cero. Se refluyen palabras sobre el contenido retenido y se desplazan
las líneas más antiguas; no se añaden saltos por READY ni puntuación. LIVE no tiene
timer de desaparición. STOP limpia tras 8000 ms; START/desconexión limpian enseguida.

El modo timed_queue anterior sigue disponible. El historial de reconexión se acota
a 128 captions / 20.000 caracteres. Normal rolling cuenta líneas retiradas; un
caption nuevo demasiado largo que desborda antes de presentarse registra
rolling_overflow por palabra. No se garantiza leer cada fragmento ante ráfagas más
rápidas que el pintado; coalesced DOM updates permite observar ese caso.

## Benchmark del renderer

Texto English sintético de siete palabras por caption, NO traducción generada ni
referencia médica; usa los 16 tiempos READY del fixture médico intacto. Reloj
virtual y modelo determinista de ancho de caracteres: compara scheduling, no tiempos
físicos de Canvas/OBS. Se vuelve a probar con llegadas cada 400 ms.

| Caso / política | Captions incorporados | Mediana / máx. espera renderer | Cola máx. | Bloques descartados |
| --- | ---: | ---: | ---: | ---: |
| Tiempos READY reales / timed_queue | 16/16 | 0 / 1271,33 ms | 1 | 0 |
| Tiempos READY reales / persistent_rolling | 16/16 | 0 / 0 ms | 0 | 0 |
| Cada 400 ms / timed_queue | 11/16 | 7666,67 / 17333,33 ms | 8 | 5 |
| Cada 400 ms / persistent_rolling | 16/16 | 0 / 0 ms | 0 | 0 |

"Incorporado" significa actualización del renderer/DOM ofrecida, no frame físico
confirmado en vídeo. 0 ms significa ninguna espera programada con este reloj, no
CPU/pintado de duración cero. Esto demuestra la eliminación de latencia de cola
visual; no demuestra todavía una reducción real del tiempo voz → OBS.

Reproducir desde la raíz:

```powershell
.\.venv\Scripts\python.exe -m benchmarks.renderer_arrivals | Out-File -Encoding utf8 logs/renderer-arrivals.json
node benchmarks/renderer_policy.cjs logs/renderer-arrivals.json
```

Replay M1–M4 sin cambios: 16 READY, 81/81 palabras, 0 late revisions y 16 éxitos mock.
El mock del replay sigue filtrado en el overlay público.

## Métricas disponibles y límites

Backend: first_seen/READY anclados al reloj monotónico del manager, normalización,
enqueue/start/end del provider y publicación Hub. Duraciones por intento distinguen
retries; el provider span incluye adaptador, thread y red, no HTTP wire-only.

En este Windows, el reloj backend GetTickCount64 tiene resolución de 15,625 ms:
0 ms en una etapa corta puede ser cuantización, no duración física cero.

Browser Source: performance.now para recepción→DOM y doble-rAF como estimación de
pintado. WebSocket clock_probe/clock_sync sincroniza offset, con incertidumbre
RTT/2 más resolución del reloj backend.
READY→visible estimado suma READY→Hub medido + entrega sincronizada estimada + rAF
local. Sin muestra de reloj reciente o en restauraciones se omite la estimación.
La incertidumbre publicada no captura toda asimetría, deriva o composición de OBS.

No se mide voz física → primer ASR, frame realmente emitido por OBS, buffering del
encoder ni pantalla física. Se necesita otra lectura instrumentada para reportar
end-to-end real. La telemetría se valida, limita y conserva 128 muestras; no contiene
texto/credenciales. Operator muestra colas, última muestra, observador, descartes,
captions/líneas visibles y alertas.

## Pruebas y archivos

121 tests Python PASS, DOM Operator/overlay y tests de persistencia/reloj PASS,
syntax JS PASS, compileall PASS y diff --check PASS. Se usó el runtime Node de Codex;
no se instalaron paquetes. Tests temporales usan reloj simulado, sin esperas largas.

Cambios: app/overlay/{config,hub}.py, app/translation/{models,engine,timing}.py,
app/asr/whisperlivekit_client.py, propiedad temporal de segment_manager.py,
app/main.py, caption_renderer.js, overlay.js, overlay_latency.js,
overlay_diagnostics.js, operator.js, overlay_preview.js y templates del overlay.
Tests: test_caption_latency.py, test_persistent_captions.cjs, caption_test_clock.cjs,
test_overlay.py, test_overlay_renderer.cjs. Benchmark: renderer_arrivals.py,
renderer_policy.cjs. README.md, OBS_OVERLAY.md, ARCHITECTURE.md y PLAN.md actualizados.

Prueba real pendiente: recargar cache de Browser Source y Operator; leer 20–30 s,
pausar 10 s, hablar varias frases seguidas, revisar tiempos y cola visual 0, STOP
y esperar 8 s. START nuevo debe limpiar de inmediato. No avanzar a M6.
