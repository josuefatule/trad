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

Resultado con defaults iniciales: **25 segmentos, 0 late revisions**, todas las
palabras del snapshot final conservadas en orden, sin duplicarlas. La edad máxima
de 2,8 s produce muchos cortes de 1–7 palabras en esta lectura lenta; `target_words=18`
es un objetivo de corte por longitud, no una garantía de longitud mínima. Esto
evidencia el intercambio entre latencia y longitud lingüística. Probar otras edades
con `SEGMENT_MAX_PENDING_SECONDS` antes de escoger valores de producción.

Los tests comparan conservación respecto del último snapshot del fixture y las
invariantes del algoritmo, no contra la ortografía del texto médico de referencia.
