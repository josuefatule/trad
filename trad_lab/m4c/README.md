# M4-C — ASR incremental aislado

Procesa únicamente archivos PCM existentes. No abre micrófonos, WebSockets,
servicios ni traducción; no importa `app/`. Utiliza los pesos small cacheados,
inglés explícito y Faster-Whisper/CTranslate2 CUDA float16. No hay AlignAtt.

El estado del reconocedor separa palabras provisionales y confirmaciones
inmutables. Dos o tres hipótesis causales deben coincidir en texto y posición
temporal. Las continuaciones sin espacio se agrupan sin cambiar sus bytes.
Signos numéricos, comparadores, porcentajes y barras de unidades participan
en la comparación; no se convierten cifras ni se corrige terminología.

`fixed` decodifica los últimos 5/10/15/30 s. `adaptive` mantiene el origen del
buffer entre actualizaciones y recorta en puntuación confirmada cuando puede
retener el contexto solicitado; a su límite de 30 s admite un límite de palabra
confirmada. En inicio/pausa sin ese límite puede recortar contexto anterior a la
primera palabra provisional, conservando 0,4 s de margen, o contexto sin hipótesis.
Esto no certifica silencio acústico ni excluye falsos negativos del VAD/ASR.
Cada recorte queda registrado. Si texto pendiente sale del horizonte,
el reconocedor falla en lugar de ocultar una omisión. El EOF conserva una cola
explícitamente **no confirmada**, sin añadir silencio futuro ni fabricar un voto.

El motor conserva como máximo 30 s de audio, 32 palabras confirmadas recientes,
128 puntos de recorte y dos hipótesis acotadas a 512 registros. Los logs y el
ensamblaje del informe viven fuera del estado del reconocedor. El evaluador de
archivos conserva trazas/texto completos para puntuar; no es una cola de servicio
validada para conferencias indefinidas.

Desde `C:/live-captions`, con 8000/8010/18000/18010 cerrados y sin otra inferencia:

```powershell
.\.venv-wlk\Scripts\python.exe -m trad_lab.m4c.replay --group yeti --windows 15 --update 2 --vad --out logs/trad_lab/NUEVO_RUN
.\.venv-wlk\Scripts\python.exe -m trad_lab.m4c.replay --group clips --windows 15 --update 2 --vad --out logs/trad_lab/OTRO_RUN
.\.venv-wlk\Scripts\python.exe -m trad_lab.m4c.replay --group full --windows 15 --update 2 --vad --out logs/trad_lab/OTRO_RUN_COMPLETO
```

`--mode adaptive`, `--minimum-age 4`, `--agreement 3`, `--update 1` y `--beam 1` son contrastes
independientes, no valores operativos recomendados. `--vad` usa exclusivamente
el ONNX Silero y sus defaults ya incluidos en la instalación; el perfil y hash
se guardan. Ningún TXT se entrega al modelo como prompt/contexto. Los directorios
de salida deben ser nuevos. Una excepción inesperada de decoder/integridad/GPU
aborta el lote y conserva el diagnóstico; no hay fallback ni reintento automático.

El replay lee bloques s16 de 1–2 s, los convierte a float32 sin ganancia y solo
entrega ventanas ya disponibles al decoder. Cada evento incluye límites absolutos,
hash del float32, palabras del decoder, hipótesis agrupada, provisional,
confirmación y tiempos de inferencia. `verify.py` contrasta esos hashes contra
el PCM original y comprueba orden/EOF/texto confirmado.

```powershell
.\.venv-wlk\Scripts\python.exe -m unittest trad_lab.m4c.test_incremental trad_lab.m4c.test_replay -v
.\.venv-wlk\Scripts\python.exe -m trad_lab.m4c.summarize logs/trad_lab/m4c_20261020T173100Z
```

`comparison.json` conserva resultados incompletos sin atribuirles un WER final.
La diferencia con WLK/offline es discrepancia **entre hipótesis**. Los recortes
M4 tienen aceptación temporal provisional y dispersión de límites conservada;
el TXT completo permite una comparación léxica exploratoria, no WER clínico.
La cola EOF se puntúa separada del texto estable.

La latencia se refiere a disponibilidad simulada menos fin de palabra estimado
por el candidato. La variante serial suma tiempos de inferencia medidos; excluye
transporte, UI, reloj acústico, traducción y escritura del log. RTF es trabajo
de inferencia/audio, no retraso visible. Muestreo GPU cada ~1 s no mide el pico
exacto del allocator. Consultar el informe M4-C antes de elegir otra prueba.
