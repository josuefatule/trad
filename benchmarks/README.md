# Material de segmentación

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
Lee las mismas variables `SEGMENT_*` que la app. Imprime PENDING, READY con métricas,
LATE si hay revisiones tardías, y un resumen. Para guardar UTF-8 en PowerShell:

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

La configuración anterior (`stability=0.9`, `silence=1.1`, `target=18`, `max=25`,
`max_age=2.8`) generaba **25 READY**. El motivo dominante no era el objetivo de
palabras: 21 cortes eran `max_age`, 3 `punctuation` y 1 `session_end`. La edad única
actuaba sin longitud mínima y fragmentaba esta lectura lenta.

Con los defaults actuales (`stability=0.8`, `silence=1.0`, `minimum=6`, `target=16`,
`maximum=24`, `soft_max_age=4.5`, `hard_max_age=7.0`) el mismo fixture genera:

| Métrica | Antes | Ahora |
| --- | ---: | ---: |
| READY | 25 | 10 |
| Palabras mín./mediana/media/máx. | 1 / 3 / 3,24 / 7 | 1 / 8 / 8,10 / 16 |
| Latencia mín./mediana/media/máx. | 2,069 / 2,877 / 3,007 / 3,947 s | 3,177 / 7,040 / 6,220 / 7,098 s |
| Late revisions | 0 | 0 |
| Integridad | 81/81 palabras, PASS | 81/81 palabras, PASS |

Motivos nuevos: 6 `hard_max_age`, 3 `punctuation` y 1 `session_end`. En este fixture
no aparece un corte `soft_max_age`: a los 4,5 s no había un límite débil estable y
útil. Esperar hasta el límite duro fue precisamente lo que permitió agrupar más.
La latencia mide primera aparición del contenido conservado → READY usando el reloj
virtual de recepción. El máximo de 7,098 s incluye la granularidad del tick de 100 ms.

READY completos del replay nuevo, conservando literalmente los errores del ASR real:

1. `La hipertensión arterial es una condición cardiovascular caracterizada por una elevación persistente de la presión arterial`
2. `systólica y/o diastólica.`
3. `Suficio patología involucra mecanismos complejos, incluyendo la activación del sistema herenina`
4. `angiotensina al dosterona.`
5. `El aumento de la resistencia vascular periférica y alteraciones en la función endotelial.`
6. `En pacientes y pertencios, la exposición prolongada a niveles elevados de presión puede producir`
7. `hipertrofia ventricular izquierda, remodelado`
8. `vascular, disfunción renal y un incremento significativo del`
9. `riesgo de accidentes cerebrovascular e infarto agudo de`
10. `miocardio.`

La concatenación por whitespace coincide palabra por palabra con el snapshot final;
no se perdió ni duplicó contenido. El test de regresión usa este payload real y exige
también IDs únicos, pending vacío y ausencia de late revisions.

Los tests comparan conservación respecto del último snapshot del fixture y las
invariantes del algoritmo, no contra la ortografía del texto médico de referencia.
