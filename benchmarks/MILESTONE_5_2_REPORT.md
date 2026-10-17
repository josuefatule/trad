# M5.2 — SegmentManager Latency A/B Benchmark

Fecha: 2026-10-17. Resultado: **la espera dominante está en ASR first appearance → READY**.
No recomiendo activar B para traducción médica con esta evidencia. A permanece como
predeterminado. C es una opción para probar si se prioriza reducir las esperas más
largas, pero no mejora la latencia típica y tampoco resuelve los cortes médicos.

No se modificaron WhisperLiveKit, SegmentManager, TerminologyNormalizer, glosarios,
DeepLProvider, TranslationEngine, CaptionHub, OBS ni `.env`. Todo el experimento es offline.

## 1. Verificación con segmentos de sesiones reales

Se unieron `segment_ready`, `segment normalized` y `caption_latency` por sesión y
secuencia en los logs locales. Las dos últimas sesiones con datos completos son
`5033f1ad06d4` y `f35acbc2d027`, con 15 segmentos en total. No son fixtures de
snapshots disponibles para replay: solo sirven como evidencia de latencia por etapa.

Tiempos ASR/READY en segundos relativos al origen monotónico de **cada** sesión.
Las duraciones de etapa proceden del mismo reloj backend; no se restaron relojes
del navegador ni timestamps de audio WLK. `Normalizer processing` es `processing_ms`,
medido con el reloj de rendimiento del normalizador; no es su timestamp de finalización.

| Sesión : segmento | Primera aparición ASR s | READY s | ASR → READY ms | READY → normalized ms | Normalizer processing ms | Provider ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 5033f1ad06d4:1 | 7.422 | 10.891 | 3469 | 15 | 19.557 | 672 |
| 5033f1ad06d4:2 | 10.047 | 13.609 | 3562 | 78 | 82.830 | 563 |
| 5033f1ad06d4:3 | 13.281 | 18.781 | 5500 | 78 | 76.197 | 610 |
| 5033f1ad06d4:4 | 17.562 | 21.797 | 4235 | 94 | 97.107 | 656 |
| 5033f1ad06d4:5 | 21.562 | 27.141 | 5579 | 31 | 25.855 | 531 |
| f35acbc2d027:1 | 4.625 | 8.657 | 4032 | 15 | 18.431 | 610 |
| f35acbc2d027:2 | 8.329 | 11.891 | 3562 | 78 | 84.041 | 578 |
| f35acbc2d027:3 | 11.516 | 15.750 | 4234 | 47 | 48.972 | 563 |
| f35acbc2d027:4 | 14.907 | 18.235 | 3328 | 62 | 65.335 | 563 |
| f35acbc2d027:5 | 17.344 | 22.875 | 5531 | 32 | 30.209 | 531 |
| f35acbc2d027:6 | 18.000 | 23.532 | 5532 | 0 | 4.476 | 562 |
| f35acbc2d027:7 | 47.063 | 50.438 | 3375 | 47 | 53.052 | 641 |
| f35acbc2d027:8 | 49.688 | 53.016 | 3328 | 78 | 76.959 | 578 |
| f35acbc2d027:9 | 52.313 | 57.844 | 5531 | 31 | 37.763 | 579 |
| f35acbc2d027:10 | 54.422 | 59.954 | 5532 | 0 | 9.078 | 578 |

| Sesión | ASR → READY mediana / p95 ms | READY → normalized mediana / p95 ms | Provider mediana ms |
| --- | ---: | ---: | ---: |
| 5033f1ad06d4 | 4235 / 5579 | 78 / 94 | 610 |
| f35acbc2d027 | 4133 / 5532 | 39.5 / 78 | 578 |

La segmentación representa entre **97.71% y 100%** del intervalo ASR → normalized
por segmento (mediana de esa proporción: **98.90%**). La cola de traducción fue
0 ms en los 15 casos. Esto confirma la hipótesis antes de cambiar parámetros.
El reloj monotónico de este Windows tiene resolución aproximada de 15.625 ms:
0 ms no significa CPU instantánea. La latencia de voz física → ASR y la salida
física de OBS no se evalúan aquí.

## 2. Nombres y semántica reales

| Concepto | Campo / variable de entorno | Semántica existente |
| --- | --- | --- |
| stability | `stabilization_seconds` / `SEGMENT_STABILIZATION_SECONDS` | Todo el prefijo candidato debe llevar ese tiempo sin cambios de caracteres; no exige que todo PENDING esté estable. |
| silence | `silence_seconds` / `SEGMENT_SILENCE_SECONDS` | Duración del silencio explícito `speaker=-2` o del hueco entre timestamps de líneas; no tiempo sin mensajes ni sin nuevas palabras. |
| minimum words | `minimum_words` / `SEGMENT_MINIMUM_WORDS` | Umbral de utilidad para silencio y whitespace blando; **no es un mínimo universal de READY**. Puntuación/coma/línea, edad dura y EOF pueden emitir menos. |
| target words | `target_words` / `SEGMENT_TARGET_WORDS` | Ancla de búsqueda hacia atrás y activación de corte natural; no espera obligatoria ni tamaño garantizado. |
| maximum words | `max_words` / `SEGMENT_MAX_WORDS` | Activa progreso por longitud, pudiendo emitir sin esperar estabilidad; el corte busca cerca del target, no necesariamente en la palabra máxima. |
| soft max age | `soft_max_age_seconds` / `SEGMENT_SOFT_MAX_AGE_SECONDS` | Edad desde el carácter retenido más antiguo. Si alcanza minimum, permite **whitespace estable**, además de límites naturales. No exige puntuación. |
| hard max age | `hard_max_age_seconds` / `SEGMENT_HARD_MAX_AGE_SECONDS` | Busca corte estable y, si no encuentra, vacía el texto disponible; puede publicar un token terminal aún susceptible de extensión ASR. |
| safe-cut lookback | `safe_cut_lookback_words` / `SEGMENT_SAFE_CUT_LOOKBACK_WORDS` | Se mantiene en 8. Prioriza puntuación, punto y coma, coma, línea y whitespace dentro de la ventana retrospectiva. |
| tick | `tick_seconds` / `SEGMENT_TICK_SECONDS` | Se mantiene en 0.1 s; explica el pequeño exceso sobre el ceiling configurado. También se evalúa al recibir cada snapshot. |

El orden efectivo es puntuación, silencio, target natural, máximo de palabras,
edad dura y edad blanda. La estabilidad se preservó íntegramente; no se cambió
la reconciliación, el manejo de caracteres abiertos ni la inmutabilidad de READY.

## 3. Dataset y método

- Principal: `medical_full_receive.json.gz`, **888 mensajes**, 58.300 s, 81 palabras.
  Recuperado del RAW original de `8ac73eec87da`, grabado el 2026-09-29. Contiene todos
  los mensajes después de `config`, incluidos snapshots repetidos y el `ready_to_stop`
  real. Los payloads originales y los offsets registrados en milisegundos no se alteraron.
  Gzip determinista, sin timestamp variable de compresión.
- SHA-256 del fixture comprimido:
  `6e4850702c084614cf62ad72a824d7f51384b16ea4c3416fadc7c764749d55b7`.
- Comparación histórica: `medical_real_snapshots.json`, 61 eventos de la **misma**
  grabación, sin snapshots idénticos en `lines`. Se conserva intacto. El test comprueba
  que cada uno de esos eventos/payloads/tiempos existe exactamente en el stream completo.
- Replay con el manager real y reloj virtual, respetando cada `at` y ejecutando ticks
  intermedios de 100 ms. No se aceleran los tiempos de decisión, aunque la ejecución
  tarda pocos segundos. No se usan timestamps de audio como tiempos de recepción.
- Los offsets RAW son timestamps de log de recepción, con precisión de milisegundos;
  no incluyen una reproducción del coste CPU, red ni scheduling del proceso original.
- p95: rango más cercano, elemento `ceil(0.95*n)` de los valores ordenados. No se
  interpolan percentiles. Con 17 segmentos, p95 coincide con el máximo; no es una
  estimación sólida de una población de sesiones.
- Latencia READY: primera aparición del contenido retenido más antiguo → emisión.
  No es edad de todas las palabras ni latencia física del habla. Se incluyen los EOF;
  el JSON también publica métricas excluyendo `session_end`.
- Calidad: 12 unidades anotadas manualmente en `medical_units.json`, sobre RAW literal
  con errores ASR conservados. Se cuentan unidades atravesadas por un límite de READY
  y número de límites internos. Esto es una auditoría lingüística concreta, **no una
  puntuación clínica, WER ni una regla nueva del pipeline**.

No hay otro fixture independiente de voz con snapshots y tiempos completos.
`medical_small_observed.txt` y `medical_m3_1_observed.txt` son textos sin timing;
el fixture real de partial es un extracto de esta misma sesión. Los logs recientes
de insuficiencia cardíaca no guardan sus payloads RAW. No se inventaron snapshots
ni tiempos para poder presentarlos como otro replay real.

## 4. Configuraciones

| Parámetro real | A actual | B experimental | C intermedia |
| --- | ---: | ---: | ---: |
| stabilization_seconds | 0.8 | 0.6 | 0.8 |
| silence_seconds | 1.0 | 0.8 | 1.0 |
| minimum_words | 7 | 5 | 7 |
| target_words | 13 | 10 | 13 |
| max_words | 21 | 18 | 21 |
| soft_max_age_seconds | 3.3 | 2.2 | 2.5 |
| hard_max_age_seconds | 5.5 | 4.0 | 4.5 |
| safe_cut_lookback_words | 8 | 8 | 8 |
| tick_seconds | 0.1 | 0.1 | 0.1 |

C conserva A y cambia solo las edades. La exploración declarada de 30 combinaciones
está completa en el JSON: estabilidad 0.6/0.8, minimum 5/6/7, target 12, máximo 20,
silencio 0.8 y parejas soft/hard 2.2/4.0, 2.5/4.5, 2.6/4.8, 2.8/4.8 y 3.0/5.0.
Se prefirió mantener mínimo 7 para no aumentar las unidades médicas fragmentadas y
estabilidad 0.8 por el control de revisión. Bajar target/máximo o silencio no aporta
un motivo de flush en esta grabación; C conserva sus valores actuales.

## 5. Resultados principales: todos los mensajes originales

| Métrica | A | B | C |
| --- | ---: | ---: | ---: |
| READY | 17 | 22 | 17 |
| Palabras mín. / mediana / media / máx. | 1 / 5 / 4.76 / 8 | 1 / 4.5 / 3.68 / 6 | 1 / 5 / 4.76 / 7 |
| READY latencia mín. s | 2.539 | 1.779 | 2.530 |
| READY latencia mediana s | 3.751 | 3.108 | 3.940 |
| READY latencia media s | 4.004 | 3.098 | 3.736 |
| READY latencia p95 s | 5.539 | 4.061 | 4.550 |
| READY latencia máxima s | 5.539 | 4.072 | 4.550 |
| Mediana excluyendo EOF s | 3.846 | 3.038 | 3.985 |
| soft_max_age | 10 | 13 | 8 |
| hard_max_age | 3 | 5 | 5 |
| punctuation | 3 | 3 | 3 |
| session_end | 1 | 1 | 1 |
| silence / target_words / max_words | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| Porcentaje hard age | 17.65% | 22.73% | 29.41% |
| forced_whitespace_cut_count | 9 | 14 | 9 |
| Unidades médicas fragmentadas / 12 | 5 | 9 | 5 |
| Límites dentro de unidades | 5 | 11 | 5 |
| Integridad RAW ordenada | 81/81 | 81/81 | 81/81 |
| Palabras perdidas / excedentes | 0 / 0 | 0 / 0 | 0 / 0 |
| Late revisions | 0 | 0 | 0 |

En los tres casos, IDs únicos, PENDING vacío al EOF y coincidencia palabra por
palabra con el último snapshot. No se deduplican palabras legítimamente repetidas:
se comparan la secuencia completa y los contadores de palabras.

B gana **643.5 ms de mediana (17.16%)** y **1478 ms de p95 (26.68%)**, pero produce
29.41% más segmentos y 55.56% más cortes forzados por whitespace. El mínimo 5 no
garantiza segmentos de cinco palabras: cola de puntuación y edad dura generan
fragmentos pequeños. La media de 3.68 palabras es insuficiente para dar por
validado un flujo médico contextual.

C reduce el p95/máximo **989 ms (17.86%)**, conserva el número de segmentos y los
cinco problemas lingüísticos de A, pero **empeora la mediana 189 ms (5.04%)**.
No hay paradoja: los límites cambian qué contenido/primera aparición pertenece
a cada segmento; la mediana no es monotónica al bajar una edad. Aumentar el
porcentaje hard age tampoco significa mayor latencia absoluta si baja el ceiling.

### Diferencia frente al fixture histórico

| Fixture de 61 eventos | A | B | C |
| --- | ---: | ---: | ---: |
| READY | 16 | 22 | 17 |
| Mediana s | 3.826 | 3.116 | 3.900 |
| p95 / máximo s | 5.598 / 5.598 | 4.068 / 4.070 | 4.560 / 4.560 |
| Whitespace forzado | 8 | 14 | 9 |
| Unidades fragmentadas | 5 | 9 | 5 |

Los mensajes repetidos originales evalúan el manager entre los ticks que quedaron
en el fixture reducido y reinician la espera de recepción del proxy. Una diferencia
de decenas de milisegundos cambia un corte elegible cerca de una revisión. Por eso
A pasa de 16 a 17 sin cambiar configuración ni algoritmo. No son dos muestras
independientes, y no se mezclaron sus métricas en la tabla principal.

## 6. Cortes médicos y traducciones DeepL reales

Todos los READY, tiempos, motivos, NORMALIZED y traducciones están en
[M5_2_RESULTS.md](M5_2_RESULTS.md); resultados y contextos exactos en
[M5_2_RESULTS.json](M5_2_RESULTS.json). No se usó la referencia inglesa para
generar traducciones ni se fabricaron resultados.

B añade fragmentaciones como:

- `condición | cardiovascular` y `elevación | persistente`;
- `presión arterial | systólica y/o | diastólica.`;
- `sistema | herenina angiotensina al | dosterona.`;
- `resistencia vascular | periférica` y `función | endotelial.`.

En A y C siguen separados `hipertrofia ventricular | izquierda,` e `infarto ... |
miocardio`; `remodelado vascular` y `disfunción renal` permanecen juntos en las tres.
Las cinco unidades partidas por A y C son las mismas, aunque no siempre en la
misma palabra. La anotación no captura por sí sola toda la diferencia de calidad.

La normalización se ejecutó con los glosarios reales, cuyo SHA-256 está en el JSON.
A y C conservan tres correcciones automáticas; B conserva dos: separar `al` de
`dosterona` impide corregir `al dosterona` a `aldosterona`. No se cambió el normalizador.

| Caso observado | NORMALIZED → DeepL | Implicación |
| --- | --- | --- |
| B, segmento 4 | `sistólica y/o` → `and/or` | El calificador sistólico desaparece en esa salida. |
| B, segmento 9 | `dosterona.` → `dosterone.` | La fragmentación impide la corrección disponible en A/C y el inglés no identifica aldosterona. |
| B, segmentos 10–12 | `resistencia vascular` → `vascular resistance`; `periférica ... función` → `and alterations in the function`; `endotelial.` → `endothelial function.` | Se pierde «periférica» en la concatenación de esas salidas observadas. |
| A/B/C, fragmento aislado | `izquierda,` → `,` | La lateralidad se pierde también con A y C; no hay una configuración ya validada clínicamente. |
| A, últimos dos | `... infarto agudo de` → `... acute myocardial infarction`; `miocardio.` → `myocardial infarction.` | Hay repetición semántica en inglés aunque RAW tenga integridad 81/81. |

Estas son observaciones de respuestas específicas, no garantías sobre todas las
respuestas futuras de DeepL. El contexto enviado fueron los dos segmentos
NORMALIZED previos, tal como está configurado el engine. No se añadió futuro ni
contexto externo. No basta con que el provider tenga contexto para asegurar que
traduzca correctamente un fragmento incompleto.

Se evaluaron primero los 61 eventos y después el stream completo. Durante este
trabajo se realizaron **50 solicitudes únicas y exitosas**, con **1640 caracteres
de texto enviados** en total. Esto cuenta texto enviado, no una consulta de
facturación. La validación completa añadió solo 4 solicitudes/156 caracteres:
52 de sus 56 entradas reutilizaron caché. La ejecución final con C conservando
los otros parámetros de A reutilizó las 56 respuestas, con **0 llamadas nuevas**.
La caché incluye texto, contexto, idiomas y endpoint; textos iguales con contexto
distinto son entradas diferentes. No se cachean fallos ni se hacen retries aquí.
La API key permanece en `.env` y nunca se incluye en los artefactos.

No se comparan duraciones offline del provider como si fueran E2E del replay:
las llamadas se ejecutan después del replay, con su caché; no simulan cola de
traducción ni scheduling de OBS. La evidencia de latencia real del provider está
en la sección 1.

## 7. Controles independientes de revisión, sintéticos

No son grabaciones adicionales. Se usan como controles derivados de los casos
de revisión y extensión de token de los tests actuales:

| Control | A | B | C |
| --- | --- | --- | --- |
| `Tiene hipotensión.` a 0 s → `Tiene hipertensión.` a 0.7 s | Correcto, 0 late | Publica antes la forma anterior, 1 late | Correcto, 0 late |
| `cardio` a 0 s → `cardiovascular` a 4.2 s | Correcto, 0 late | Hard age publica `cardio`, 1 late | Correcto, 0 late |

B no coincide con el snapshot final en esos dos controles porque READY conserva
su texto publicado y la revisión posterior se registra sin reescribirlo, como
debe hacer el diseño actual. No es un fallo nuevo de reconciliación ni prueba
de pérdida en el benchmark real: es el riesgo explícito de adelantar la emisión.
No se aplicó una heurística para ocultar esos resultados.

## 8. Decisión y siguiente validación

**Conservar A.** El ahorro típico de B no justifica el deterioro observado para
traducción médica: más unidades partidas, pérdida de correcciones disponibles y
ejemplos reales de inglés incompleto, además del riesgo de revisión temprana.
A también tiene límites lingüísticos y no debe describirse como traducción médica
validada por conservar 81 palabras.

**Proponer C solo como experimento para limitar la cola de latencia**:
soft 2.5 s, hard 4.5 s, conservando el resto de A. Recorta el p95 cerca de un
segundo sin aumentar los cortes anotados en esta grabación, pero no acelera el
caption típico. No se activó en `.env` ni en defaults.

Hace falta otra grabación médica independiente con RAW/timing y revisión de
inglés, idealmente con ritmo y puntuación distintos. La sola línea WLK creciente
del fixture no aporta límites internos de línea y sus tiempos no son word-level.
Los umbrales no pueden garantizar unidades clínicas completas con un ceiling
corto cuando la continuación/puntuación aún no ha llegado. No se introdujeron
reglas médicas, nuevas reconciliaciones ni proveedores para compensarlo.

## 9. Reproducir y pruebas

Sin voz, GPU, servidores ni solicitudes API:

```powershell
.\.venv\Scripts\python.exe -m benchmarks.segment_latency_ab --output logs/m52-replay.json
```

Opcional, DeepL real usando caché local (puede consumir API si faltan entradas):

```powershell
.\.venv\Scripts\python.exe -m benchmarks.segment_latency_ab --deepl --output logs/m52-deepl.json --cache logs/m52-deepl-cache.json
```

Los resultados se escriben a JSON y al apéndice `.md` del mismo nombre. La
configuración del normalizador sigue siendo la local; comparar los hashes de
glosarios si se modifican. La parte de evidencia live requiere los logs locales
originales; sus muestras capturadas ya están incluidas en el resultado versionado.
El fixture completo es autocontenido y se descomprime con `load_fixture` del módulo.

Siete tests nuevos verifican ambos streams reales, métricas/p95, anotación de cortes,
integridad, riesgos de revisión, unión temporal por segmento y caché de traducción.
La prueba de la caché usa un doble local, nunca DeepL real. Se conservan los tests
anteriores. Resultado final: **132 tests Python y cuatro suites JavaScript PASS**.
No avance a M6.
