# Benchmark del Terminology Normalizer

Fixture: `medical_real_snapshots.json`, 61 eventos recibidos de voz real. El replay
produce los mismos 16 READY de Milestone 2 y conserva las 81 palabras RAW en orden,
sin pérdidas, duplicados ni late revisions.

## Resultado

| Métrica | Valor |
| --- | ---: |
| READY procesados | 16 |
| Correcciones aplicadas | 2 |
| Sugerencias | 2 |
| Segmentos sin modificación | 14 |
| Falsos positivos observados | 0 |
| Palabras RAW conservadas | 81/81 |

Corrección aplicada:

```text
RAW:        arterial systólica y/o diastólica.
NORMALIZED: arterial sistólica y/o diastólica.
RULE:       exact_variant (confidence=1.0)
```

Milestone 3.1 añade en el mismo replay:

```text
RAW:        al dosterona.
NORMALIZED: aldosterona.
RULE:       glossary_fuzzy (confidence=1.0)
```

La cadena reconocible quedó dividida por el SegmentManager:

```text
READY 5: incluyendo la activación del sistema herenina angiotensina
READY 6: al dosterona.
SUGGESTION: herenina angiotensina al dosterona
          → renina-angiotensina-aldosterona
confidence=0.939231, rule=cross_segment_glossary_fuzzy
```

La sugerencia no cambia ninguno de los dos READY. `Suficio patología` añade ahora
una sugerencia conservadora a `fisiopatología` con confianza 0.922619.
`pertenecios` permanece igual. En especial, no se infiere
`pertenecios → hipertensos`.

Términos conocidos encontrados: `aldosterona`, `cerebrovascular`, `hipertensión`,
`resistencia vascular periférica` y `sistólica`. Los términos correctos
se reconocen aunque no requieran una sustitución; solo las sustituciones aparecen
como correcciones.

## Rendimiento

Comando:

```powershell
$env:PYTHONIOENCODING = "utf-8"
.\.venv\Scripts\python.exe replay_fixture.py benchmarks/medical_real_snapshots.json
```

La ejecución predeterminada repite los 16 READY cien veces:

| Muestras | Mediana | p95 | Máximo |
| ---: | ---: | ---: | ---: |
| 1.600 | 25,867 ms | 53,079 ms | 72,956 ms |

La mediana equivale aproximadamente al 0,68 % de la latencia READY mediana del
mismo replay (3.826 ms). Es una medición local, no un límite contractual. El costo
crece con el número y longitud de términos del glosario.

## Casos adicionales

Las pruebas independientes cubren `fibrilación auricular`, `insuficiencia cardíaca`,
`antagonistas de los receptores de angiotensina II`, `ecocardiografía transtorácica` y
`hemoglobina glicosilada`. También fijan los negativos `renal`, `arterial`, `tensión`
y `receptor`, para evitar correcciones por semejanza débil o por una sola palabra.
