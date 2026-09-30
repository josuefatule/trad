# Validación Milestone 3.1

Sesión real investigada: `c73206fa7334`, iniciada el 2026-09-29 a las 19:43.
El proceso FastAPI seguía vivo desde las 18:22:59, antes de los commits del
SegmentManager final (19:12) y TerminologyNormalizer (19:33).

## Regresión de la ruta real

El log de la sesión contiene 40 eventos `segment_ready`, todos con la regla antigua
`max_age`, y **cero** eventos `segment normalized`. El normalizador actual ejecutado
directamente sobre el mismo span sí produce:

```text
systólica → sistólica
rule=exact_variant, confidence=1.0
```

La UI de Milestone 3 aceptaba mensajes sin `normalization` y copiaba `segment.text`
como fallback en NORMALIZED ES. Un servidor Python antiguo podía servir el JavaScript
nuevo desde disco, pero conservar el proxy viejo importado en memoria. Por eso el
panel parecía normalizado aunque solo mostraba RAW.

La corrección añade la capability `terminology_normalizer=1` al handshake. La UI la
exige antes de iniciar captura y también exige un resultado normalizado por cada READY.
Si falta, muestra un error explícito que pide reiniciar FastAPI; ya no presenta RAW
como si fuera NORMALIZED.

## Antes y después

RAW y NORMALIZED anterior eran idénticos por el fallback descrito. El RAW exacto se
conserva en `medical_m3_1_observed.txt`.

NORMALIZED nuevo sobre el texto completo observado:

```text
la hipertensión arterial es una condición cardiovascular caracterizada por una elevación persistente de la presión arterial sistólica y/o diastólica suficio patología involucra mecanismos complejos y incluyendo la activación de la del sistema renina-angiotensina-aldosterona el aumento de las resistencias vascular periférica y alteraciones en la función endotelial. En pacientes hipertensos la exposición prolongada a niveles elevados de presión puede producir hipertrofia ventricular izquierda remodelado vascular disfunción renal y un incremento significativo del riesgo de accidente cerebrovascular e infarto agudo de miocardio. La evaluación clínica debe considerar mediciones repetidas de presión arterial monitoreo ambulatorio de 24 horas, y factores de riesgo como obesidad, diabetes mellitos, dislipidemia y enfermedad renal crónica. El tratamiento puede incluir modificaciones del estilo de vida y medicamentos como inhibidores del enzima convertidora de angiotensina antagonistas de los receptores de angiotensina II, bloqueadores de los canales de calcio, y diuréticos diacídicos
```

Correcciones automáticas:

| Source | Replacement | Rule | Confidence |
| --- | --- | --- | ---: |
| `systólica` | `sistólica` | `exact_variant` | 1.000000 |
| `renina angiotensina al desterona` | `renina-angiotensina-aldosterona` | `glossary_fuzzy` | 0.975493 |
| `accidente cerebro vascular` | `accidente cerebrovascular` | `glossary_fuzzy` | 1.000000 |
| `angiotensina 2` | `angiotensina II` | `exact_alias` | 1.000000 |

Sugerencias no aplicadas:

| Source | Candidate | Confidence |
| --- | --- | ---: |
| `suficio patología` | `fisiopatología` | 0.922619 |
| `resistencias vascular periférica` | `resistencia vascular periférica` | 0.985230 |
| `diabetes mellitos` | `diabetes mellitus` | 0.945404 |
| `diuréticos diacídicos` | `diuréticos tiazídicos` | 0.912143 |

Evaluación aislada de los casos solicitados:

| Input | Resultado | Acción | Confidence |
| --- | --- | --- | ---: |
| `systólica` | `sistólica` | corrección exacta | 1.000000 |
| `suficio patología` | sin cambio; candidato `fisiopatología` | sugerencia | 0.922619 |
| `renina angiotensina al desterona` | `renina-angiotensina-aldosterona` | corrección fuzzy | 0.975493 |
| `resistencias vascular periférica` | sin cambio; candidato singular | sugerencia | 0.985230 |
| `cerebro vascular` | `cerebrovascular` | unión técnica fuzzy | 1.000000 |
| `diabetes mellitos` | sin cambio; candidato `diabetes mellitus` | sugerencia | 0.945404 |
| `enzima convertidora de angiotensina` | sin cambio; ya canónico | reconocido | — |
| `angiotensina 2` | `angiotensina II` | alias exacto | 1.000000 |
| `diuréticos diacídicos` | sin cambio; candidato `diuréticos tiazídicos` | sugerencia | 0.912143 |

`enzima convertidora de angiotensina` se reconoce como forma canónica y no necesita
cambio. El artículo anterior en `del enzima...` se conserva. También permanecen
intactos `y incluyendo` y `de la del sistema`: son problemas gramaticales del ASR,
fuera del alcance del normalizador terminológico.

Procesando los 40 límites READY que realmente produjo el servidor antiguo, se aplican
dos correcciones locales (`systólica`, `accidente cerebro vascular`) y se registran
sugerencias para los términos partidos. No se modifica ningún READY anterior. Los
resultados variarán con los límites del SegmentManager actual, pero RAW permanece igual.

## Algoritmo afinado

El fuzzy arbitrario de una palabra continúa deshabilitado. Una forma canónica técnica
de una palabra puede comparar contra un span ASR de dos tokens solamente cuando:

- la entrada del glosario habilita fuzzy;
- el canónico tiene al menos 10 caracteres;
- el span contiene al menos dos tokens;
- la similitud supera el umbral, o al compactar los tokens queda como máximo a una
  edición del canónico.

El caso estructural de una edición recibe como mínimo el umbral auto configurado.
Esto normaliza `al desterona → aldosterona`, `electro cardiograma →
electrocardiograma` y `micro albuminuria → microalbuminuria`. No activa correcciones
para `alta tensión`, `arteria renal`, `cardio grama`, `micro economía` ni la palabra
aislada `angiotensina`.

NORMALIZED también colapsa whitespace repetido, elimina whitespace antes de signos y
añade un espacio ausente después de `,;:!?` cuando sigue una letra. Cada operación se
registra como `deterministic_spacing`; RAW y sus offsets permanecen intactos. No se
añaden signos ni se reescribe gramática.

## Falsos positivos y límites

No se observaron reemplazos falsos en el texto completo ni en los 40 READY reales.
Las cuatro coincidencias inciertas permanecen como sugerencias. Los términos que
cruzan READY no se corrigen retroactivamente. En particular, con el corte real
`angiotensina al | desterona`, se emite la sugerencia `al desterona → aldosterona`
en el segmento actual; el texto anterior permanece publicado.

El replay de segmentación conserva 16 READY, integridad RAW 81/81 y cero late
revisions. Sobre 1.600 normalizaciones: mediana 25,867 ms, p95 53,079 ms y máximo
72,956 ms. La mediana representa aproximadamente 0,68 % de la latencia READY mediana.
La suite completa ejecuta 84 tests Python.
