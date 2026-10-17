# Aceptación física M8 — PENDIENTE

M7 fue validado con hardware/servicios reales según confirmación del usuario en el
brief M8. Esta hoja es una **nueva** validación v0.1, incluida una sesión de 60–90 min.
No se ejecuta de manera desatendida ni autoriza consumo de DeepL por sí sola.
Usar exclusivamente texto de ensayo no confidencial, sin datos de pacientes.

## Preparación y recorrido end-to-end

Registrar fecha, operador, commit/tag, equipo, driver, dispositivos, navegador,
versión OBS, pantallas, sample rate y configuración A. Mantener 0.8/1.0/7/13/21,
lookback 8, soft 3.3, hard 5.5, tick 0.1. No afinar durante la prueba.

1. Con sesión detenida, comprobar versiones/pins y arrancar WLK y FastAPI según
   [instalación](INSTALL_WINDOWS.md). Esperar readiness de WLK. Abrir Operator y
   OBS, recargar caché del Browser Source. `Configured` no equivale a DeepL verificado.
2. Permitir audio/popups, seleccionar Blue Yeti y START. Anotar session_id; comprobar
   CAPTURE, frames PCM, ASR CONFIRMED, READY, RAW, NORMALIZED y ENGLISH en ese orden.
   PARTIAL vacío es una limitación documentada de la configuración WLK actual.
3. Leer `benchmarks/medical_reference.txt` y luego material independiente. Incluir
   negaciones, lateralidad, fármacos, 5 mg, 3,5 mmol/L, 120/80 mmHg y pausas largas.
   Comparar RAW→NORMALIZED→ENGLISH por ID; marcar omisión/adición/cambio de significado.
   No confundir preservación de palabras ASR con exactitud clínica del reconocimiento.
4. Confirmar inglés dentro de la franja, sin fondo negro, ni clipping. Pausa de 30 s:
   el texto sigue visible. Rolling mantiene orden y no crea espera visual.
5. CLEAR durante LIVE: desaparece el texto en todas las fuentes, se conservan los
   historiales y reaparece solo la siguiente traducción. Recargar Browser Source
   inmediatamente tras CLEAR: no debe resucitar el texto anterior.
6. Recargar solo Operator durante voz. Mismo session_id, una CAPTURE, sin huecos
   audibles ni doble traducción, STOP y CLEAR recuperados. Anotar incidentes.
7. Cerrar/reabrir o recargar Browser Source durante LIVE. Debe reconstruir la ventana
   vigente una vez, respetando CLEAR. No afirmar que reconectar el overlay reconecta WLK.
8. STOP, esperar flush/drain, último texto y outcome **complete**, cola/pending 0.
   Texto desaparece ocho segundos después de stopped. Cerrar CAPTURE después.
9. START nuevo: session_id nuevo, secuencia nueva, sin texto ni contexto anterior.
   Leer otra frase y STOP completo. Verificar limpieza de audio/workers/sockets.
10. Para terminar, Ctrl+C servidores. Probar reinicio y START nuevo en ensayo; no
    existe persistencia tras reinicio ni replay automático de traducciones.

## Duración real 60–90 minutos

El operador debe permanecer presente. Hacer un presupuesto de caracteres/cuota de
DeepL y autorizarlo antes de START. Anotar uso de cuenta antes/después; no hacer
health calls de traducción. No enviar automáticamente nuevos fixtures a DeepL.

Cada cinco minutos y antes/después de STOP completar:

| Minuto / session_id | READY / palabras | EN completadas / fallos / retries | Reconexiones WLK / overlay | Queue actual / máx | RAM por proceso / CPU | GPU / VRAM | Lag observado / incidente |
|---|---|---|---|---|---|---|---|
| 0 | | | | | | | |
| 5…60/90 | | | | | | | |
| STOP | | | | | | | |

Usar Task Manager/Performance Monitor para RSS, CPU y memoria de FastAPI, WLK,
Chrome y OBS por separado, sin confundir RSS con Python tracemalloc. Si está
disponible, `nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used --format=csv`
da una muestra GPU, no atribución perfecta por proceso. Registrar método e intervalo.

Counters/cola/outcome están en Reliability / recovery y Overlay diagnostics. Guardar
diagnósticos **antes del siguiente START**, que los reinicia. Journal 512 eventos/2 MB
y latencias 128 muestras son ventanas, no un archivo completo de conferencia.
No extrapolar p95 de una ventana a 90 min. Contar palabras por READY único, no por
snapshots acumulativos. Caracteres DeepL aproximados = suma de normalized_text de
solicitudes enviadas; informar retries/posible duplicación y contrastar con el uso
real de la cuenta. No confundir contexto o solo éxitos con el total facturable.

Para conservar muestras de duración sin modificar el servidor puede ejecutarse este
snippet en DevTools de **Operator**, antes de START. Solo lee el snapshot que la
consola ya obtiene; no hace requests ni guarda texto, credenciales, nonces o audio.
Descargar antes de recargar Operator; la recarga elimina este colector. Si se pausa,
se cierra o hay huecos, documentar muestras perdidas y no afirmar cobertura completa.
Conservar cada archivo con su intervalo y fusionar por session_id/sequence/observer_id.

```javascript
globalThis.m8Samples = {backend: new Map(), observers: new Map(), ready:new Map(),
  normalized:new Map(), translations:new Map(), runs: []};
globalThis.m8Timer = setInterval(() => {
  const s = globalThis.OperatorUI?.snapshot;
  if (!s?.session_id) return;
  const d = s.latency_diagnostics || {}, id = s.session_id;
  for (const x of d.backend_samples || [])
    m8Samples.backend.set(`${id}:${x.sequence}`, {session_id:id,...x});
  for (const x of d.observer_samples || [])
    m8Samples.observers.set(`${id}:${x.observer_id}:${x.visual_generation}:${x.sequence}:${x.render_measurement}`,
      {session_id:id,...x});
  for (const entry of s.operator_history?.events || []) {
    const m=entry.message;
    for (const x of m.segmentation?.ready_segments || [])
      m8Samples.ready.set(x.id,{session_id:id,id:x.id,word_count:x.word_count,
        first_seen_at:x.first_seen_at,emitted_at:x.emitted_at,latency_ms:x.latency_ms,
        start_time:x.start_time,end_time:x.end_time,reason:x.reason,boundary_kind:x.boundary_kind});
    for (const x of m.normalization?.segments || [])
      m8Samples.normalized.set(x.segment_id,{session_id:id,id:x.segment_id,
        processing_ms:x.processing_ms,characters:x.normalized_text.length,
        corrections:x.corrections.length,suggestions:x.suggestions.length});
    const t=m.translation;
    if(t) m8Samples.translations.set(`${id}:${t.sequence}`,{session_id:id,
      segment_id:t.segment_id,sequence:t.sequence,success:t.success,attempt_count:t.attempt_count,
      normalized_characters:t.normalized_text.length,timing:t.timing,queue_delay_ms:t.queue_delay_ms});
  }
  const r = s.reliability || {};
  if (m8Samples.runs.length < 7200) m8Samples.runs.push({session_id:id,
    observed_wall_ms:Date.now(), duration_seconds:r.duration_seconds, outcome:r.outcome,
    counters:r.counters, queue_depth:d.translation_queue_depth, queue_max:d.translation_queue_max,
    history_gap:s.operator_history?.history_gap, journal_truncated:r.journal_truncated});
  if (m8Samples.ready.size > 10000 || m8Samples.translations.size > 10000 ||
      m8Samples.backend.size > 10000 || m8Samples.observers.size > 30000) clearInterval(m8Timer);
}, 1000);
// Al terminar este intervalo, descargar metadatos locales:
// clearInterval(m8Timer);
// const data=Object.fromEntries(Object.entries(m8Samples).map(([k,v])=>[k,v instanceof Map?[...v.values()]:v]));
// const blob = new Blob([JSON.stringify(data,null,2)],{type:'application/json'});
// const a=document.createElement('a'); a.href=URL.createObjectURL(blob);
// a.download='m8-manual-diagnostics.json'; a.click(); URL.revokeObjectURL(a.href);
```

Los backend_samples contienen duraciones correlacionadas por secuencia; los eventos
de traducción añaden timestamps completos del backend y READY aporta límites de
líneas de audio. Sumar word_count de READY únicos y normalized_characters de
traducciones únicas; registrar aparte intentos y posibles duplicaciones, no asumir
que cada intento llegó a facturarse. Comparar IDs/secuencias con contadores finales
y declarar huecos: el polling puede perder eventos si la pestaña se suspende o se
recarga. Este snippet es auxiliar y no promete cobertura completa de cada evento.
No activar RAW por defecto ni guardar la respuesta de bootstrap/sessionStorage.

Al cerrar: duración real, totales, muestras faltantes, memoria inicial/final/pico,
CPU/GPU, colas, fallos y recuperación, consumo, lag del primer/último bloque,
outcome STOP y audio liberado. Cada fallo inesperado necesita reproducción antes
de aprobar. Un WLK perdido durante LIVE exige sesión nueva y resultado incompleto.

## Voz física → proyección: un reloj audiovisual

Con autorización, grabar en una sola toma de cámara la boca/sonido del orador y
la pantalla física proyectada. Usar guion público de ensayo y al menos 20 frases
identificables distribuidas al inicio, medio y final. Anotar FPS real y eventuales
frames perdidos. No subir la grabación automáticamente.

Para cada frase anotar frame/tiempo del inicio y final audible de la unidad elegida
y el primer frame donde esa unidad traducida resulta visible. Medir tanto
inicio→visible como final→visible, indicando criterio; no sumar relojes de PC y cámara.
Incertidumbre mínima por cuantización de dos frames, más alineación de audio/vídeo;
documentar esa incertidumbre. No usar el botón START como instante de habla ni
doble-rAF como instante del proyector. Informar n/mediana/p90/p95/máximo y comparar
primer/último tercio. Sin grabación/medición efectiva marcar **PENDIENTE**.

## Acta de aceptación

- Fecha / operador / commit / equipo / duración: **PENDIENTE**.
- Recorrido 1–19, CLEAR/recovery/STOP/nuevo START: **PENDIENTE M8**.
- Hora real, métricas y uso DeepL: **PENDIENTE**.
- Revisión de inglés médico por persona competente: **PENDIENTE**.
- Instalación limpia y OBS/proyector: **PENDIENTE**.
- Autorización explícita para `v0.1.0`: **PENDIENTE**.

Si una condición impide probarlo, registrar **BLOQUEADO**, causa y siguiente acción.
No marcar todo aprobado por el resultado de las simulaciones ni por aceptación M7.
