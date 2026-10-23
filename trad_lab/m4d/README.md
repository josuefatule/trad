# M4-D — Evaluación focalizada de ASR médico

Solo archivos existentes; no abre servicios, micrófono, DeepL u OBS. Reutiliza
sin modificar el motor incremental M4-C, con un modelo GPU por proceso, inglés,
CUDA float16, beam 5, temperatura 0, sin prompts/hotwords ni corrección posterior.
Los tres snapshots deben existir completos en caché y coincidir con los hashes
M3. `vocabulary.txt` y `vocabulary.json` son formatos cacheados distintos; Turbo
incluye además su `preprocessor_config.json`. No se instala ni descarga nada.

Desde `C:/live-captions`, con los cuatro puertos cerrados:

```powershell
.\.venv-wlk\Scripts\python.exe -m trad_lab.m4d.evaluate prepare --out logs/trad_lab/NUEVO_RUN/evaluation
.\.venv-wlk\Scripts\python.exe -m trad_lab.m4d.evaluate cache --out logs/trad_lab/NUEVO_RUN/evaluation
.\.venv-wlk\Scripts\python.exe -m trad_lab.m4d.analysis prepare logs/trad_lab/NUEVO_RUN/evaluation
.\.venv-wlk\Scripts\python.exe -m trad_lab.m4d.evaluate offline --model medium --out logs/trad_lab/NUEVO_RUN/evaluation
.\.venv-wlk\Scripts\python.exe -m trad_lab.m4d.evaluate incremental --model medium --group full --out logs/trad_lab/NUEVO_RUN/evaluation
.\.venv-wlk\Scripts\python.exe -m trad_lab.m4d.analysis analyze logs/trad_lab/NUEVO_RUN/evaluation
.\.venv-wlk\Scripts\python.exe -m unittest trad_lab.m4d.test_evaluation -v
```

Cada salida de inferencia exige directorio nuevo. Ejecutar modelos de forma
secuencial. Se mantienen los errores y se aborta ante fallos inesperados/GPU,
sin fallback ni reintentos automáticos. Las fuentes se congelan por ejecución.

`adjudication.json` fija **antes de inferir** las cuatro expresiones comunicadas
por el usuario como escuchadas. Comprueba identidad PCM de los recortes M4-C,
SHA e intervalos de contenedor, no adjudica toda la frase ni fronteras exactas
por palabra. El sistema no dispone de una nueva escucha independiente. Las
hipótesis nunca cambian esas referencias. Los demás recortes quedan sin adjudicar.

Se añade la misma cantidad de contexto a los cuatro casos: hasta 10 s antes y
10 s después, limitado por el archivo fuente. Ese audio posterior se usa solo
para diagnóstico offline. El incremental recibe exclusivamente audio disponible.
Las verificaciones independientes M4-C comprueban muestras, hashes y EOF.

La matriz clínica usa coincidencias explícitas de expresión. `stage two/2` y
`four to six/4 to 6` pueden coincidir en ese canal; `46` nunca equivale al rango,
ni `19` a `90`, ni `treated` a `untreated`. No cambia el WER/CER léxico primario.
Los conflictos y coincidencias mixtas quedan visibles. No hay WER clínico.

Se reutiliza el baseline small/LA2/age1/VAD de M4-C sin nuevas inferencias small
completas. Se comparan como máximo dos alternativas, cambiando inicialmente solo
el modelo. Las alertas sensibles se calculan después sobre las trazas; no alteran
confirmaciones ni son un detector clínico validado.

El corpus ya se exploró en M3/M4-C. Las regiones de comprobación excluyen 60
tokens de referencia a cada lado de los cuatro casos de selección, y cardio_02
se conserva completo. Esta partición no produce un test independiente. La
proyección fuera de esos cuatro casos también contiene recortes diagnósticos
adicionales ya vistos; no se presenta como holdout intacto. Cardio_02 es el único
archivo que no entra en la fase focal M4-D, con exposición previa M3/M4-C.
La continuidad textual entre cardio_02 y cardio_03 sugiere un mismo webinar;
se agrupan conservadoramente y no se cuentan tres discursos independientes.

Consultar el informe M4-D antes de proponer una integración. El código operativo
y el intento físico 04 quedan fuera de este paquete.
