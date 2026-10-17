# Material de segmentación

## M5.2 — Benchmark A/B de latencia

Informe y decisión: [MILESTONE_5_2_REPORT.md](MILESTONE_5_2_REPORT.md).
Detalle de todos los READY y traducciones reales: [M5_2_RESULTS.md](M5_2_RESULTS.md).
`medical_full_receive.json.gz` conserva los 888 mensajes originales de la misma
sesión médica, incluidos repetidos, en gzip determinista. El fixture histórico
de 61 eventos permanece intacto. `medical_units.json` contiene anotaciones de
evaluación; el runtime no las carga.

```powershell
.\.venv\Scripts\python.exe -m benchmarks.segment_latency_ab --output logs/m52-replay.json
```

Replay sin API: A 17 READY, mediana 3.751 s/p95 5.539 s; B 22, 3.108/4.061 s;
C 17, 3.940/4.550 s. Las tres conservan RAW 81/81 y 0 late revisions en la
grabación real. B fragmenta más unidades y falla dos controles sintéticos de
revisión. **No se cambian los defaults**. DeepL es opt-in mediante `--deepl`, con
caché por texto/contexto/idiomas/endpoint; ver consumo y limitaciones en el informe.

## Fixture histórico y etapas anteriores

- `medical_reference.txt`: lectura de referencia suministrada por el usuario.
- `medical_small_observed.txt`: transcripción aproximada suministrada por el
  usuario, con sus errores conservados; no es el resultado esperado de un test ASR.
- `medical_real_snapshots.json`: 61 eventos de la sesión real `8ac73eec87da` del
  2026-09-29: los 60 snapshots con cambios en `lines` y `ready_to_stop`.
  Los payloads no se modificaron. `at` conserva el tiempo de recepción desde el
  primer mensaje de la sesión, que duró 58,3 s. Se omitieron snapshots idénticos
  en `lines`; el replay ejecuta los ticks intermedios para conservar el paso del tiempo.

```powershell
.\.venv\Scripts\python.exe replay_fixture.py benchmarks/medical_real_snapshots.json
```

No requiere micrófono, servidores ni GPU; termina sin esperar 58 segundos reales.
Lee las mismas variables `SEGMENT_*` y `NORMALIZER_*` que la app. Imprime PENDING,
READY, RAW, NORMALIZED, CORRECTION/SUGGESTION, LATE si hay revisiones tardías, los
resúmenes y un perfil del normalizador. `--perf-repeats 0` omite el perfil. Para
guardar UTF-8 en PowerShell:

```powershell
$env:PYTHONIOENCODING = "utf-8"
.\.venv\Scripts\python.exe replay_fixture.py benchmarks/medical_real_snapshots.json |
    Out-File -Encoding utf8 logs/replay-medical.txt
```

Formato para otra grabación: objeto con `events`, cada evento contiene `at`
(segundos de recepción, monotónicos) y `payload` (JSON WLK completo). Incluir el
`ready_to_stop` real al final para probar session_end. No convertir los timestamps
del audio en tiempos de recepción. Un fixture sin EOF no se finaliza artificialmente.

## Afinación del SegmentManager

Se compararon tres políticas sobre los mismos 61 eventos y el mismo reloj de recepción:

| Métrica | Original | Afinación anterior | `safe_cut` final |
| --- | ---: | ---: | ---: |
| READY | 25 | 10 | **16** |
| Palabras mín./mediana/media/máx. | 1 / 3 / 3,24 / 7 | 1 / 8 / 8,10 / 16 | **1 / 5,5 / 5,06 / 8** |
| Latencia mín./mediana/media/máx. | 2,069 / 2,877 / 3,007 / 3,947 s | 3,177 / 7,040 / 6,220 / 7,098 s | **2,728 / 3,826 / 4,100 / 5,598 s** |
| Cortes por edad dura | 21/25 (`max_age`) | 6/10 | **2/16 (12,5 %)** |
| Late revisions | 0 | 0 | **0** |
| Integridad | 81/81, PASS | 81/81, PASS | **81/81, PASS** |

Defaults finales: `stability=0.8`, `silence=1.0`, `minimum=7`, `target=13`,
`maximum=21`, `safe_cut_lookback=8`, `soft_max_age=3.3` y `hard_max_age=5.5`.
Se probaron mínimos 6–9, targets 12–14, edades blandas 3,0–3,5, edades duras
5,0–5,5 y ventanas 6/8/10. Un mínimo de 8 reducía `forced_whitespace_cut_count`
solo de 8 a 7, elevaba la mediana a 4,55 s y volvía a separar `presión arterial`
de `systólica y/o diastólica`; se descartó.

Motivos finales: 10 `soft_max_age`, 3 `punctuation`, 2 `hard_max_age` y 1
`session_end`. Límites: 8 `whitespace`, 4 `comma`, 3 `strong_punctuation` y 1
`session_end`. Por tanto, `forced_whitespace_cut_count=8`. La latencia mide primera
aparición del contenido conservado → READY. El máximo de 5,598 s incluye el tick
de 100 ms sobre el ceiling configurado de 5,5 s.

READY finales, conservando literalmente los errores del ASR real:

1. `La hipertensión arterial es una condición cardiovascular`
2. `caracterizada por una elevación persistente de la presión`
3. `arterial systólica y/o diastólica.`
4. `Suficio patología involucra mecanismos complejos,`
5. `incluyendo la activación del sistema herenina angiotensina`
6. `al dosterona.`
7. `El aumento de la resistencia vascular periférica`
8. `y alteraciones en la función endotelial.`
9. `En pacientes y pertencios,`
10. `la exposición prolongada a niveles elevados de`
11. `presión puede producir hipertrofia ventricular`
12. `izquierda,`
13. `remodelado vascular,`
14. `disfunción renal y un incremento significativo del`
15. `riesgo de accidentes cerebrovascular e infarto agudo de`
16. `miocardio.`

El fixture mantiene una sola línea WLK creciente durante toda la lectura. Por eso no
ofrece límites internos de línea, y sus timestamps solo describen esa línea completa.
La política conserva `arterial systólica y/o diastólica` y `remodelado vascular`.
No puede preservar también toda la cadena `sistema herenina angiotensina al dosterona`
dentro de un ceiling de 5,5 s: la puntuación final aparece demasiado tarde y no hay
otra señal estructural antes. Añadir una regla léxica específica sería frágil, por lo
que se documenta el límite.

La concatenación por whitespace coincide palabra por palabra con el snapshot final;
no se perdió ni duplicó contenido. El test de regresión fija los 16 READY, motivos,
tipos de límite, IDs únicos, pending vacío y ausencia de late revisions.

Los tests comparan conservación respecto del último snapshot del fixture y las
invariantes del algoritmo, no contra la ortografía del texto médico de referencia.

## Normalización

El resultado histórico de Milestone 3.1 está en `NORMALIZER_REPORT.md`. Con la
configuración local actual el replay produce 3 correcciones, 1 sugerencia y RAW 81/81.
El normalizador no modifica los READY ni las métricas de segmentación anteriores.

La validación posterior con la sesión real `c73206fa7334`, la causa del backend
obsoleto y la comparación completa antes/después están en
`MILESTONE_3_1_REPORT.md`. El RAW suministrado se conserva en
`medical_m3_1_observed.txt`.

## Traducción Milestone 4

`medical_reference_en.txt` es una referencia humana separada para evaluación. Nunca
entra al provider, al contexto ni a la generación de resultados.

El replay usa `MockTranslatorProvider` por defecto y muestra explícitamente
`[MOCK EN]`. `--translation-provider configured` usa `TRANSLATION_*`; `disabled`
conserva el benchmark sin traducción. El resumen incluye éxitos/fallos, retries,
timeouts, latencia y demora de cola. Esta demora corresponde al replay acelerado,
no a los 58,3 segundos reales del fixture.
