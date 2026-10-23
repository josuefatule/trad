# TRAD — MVP bidireccional de congreso, EN → ES prioritario

Fecha: 2026-10-20 (America/La_Paz). Rama `sprint2/m1-rtx4070`.
Baseline conservado: `64f82214b33fad4ee68295df1367249caeae3187`, tag `v0.1.0-rc1`.

## Dictamen y estado operativo

**GO CON RESERVAS para ensayo físico supervisado de la funcionalidad.**
La implementación y los contratos automatizados permiten EN → ES y ES → EN,
con dirección fija por sesión. **No se declara lista para el congreso**: falta
comprobar voz inglesa, inferencia GPU real con el nuevo aislamiento, DeepL real,
OBS y revisión de significado médico en ambas direcciones.

El código nuevo está en disco, **no activado en los servicios existentes**.
No se reiniciaron FastAPI/WLK ni se abrió micrófono real. Los listeners observados
siguen siendo WLK PID 27132 en 127.0.0.1/::1:8000 y FastAPI PID 27708 en
127.0.0.1:8010. La activación manual requiere una ventana con sesión detenida.

## Auditoría inicial y arquitectura

Antes de editar: HEAD, `main` y el RC resuelven a `64f8221`; rama esperada,
remoto `https://github.com/josuefatule/trad.git`. Existían únicamente el cambio
M1 en `INSTALL_WINDOWS.md`, `S2-M1-REPORT.md` sin seguimiento y los tres JSON
S2-M1 sin seguimiento. Se conservaron. No se inspeccionó el contenido de `.env`
ni se imprimieron o modificaron credenciales; `.env` permanece intacto. Las
pruebas importan la carga habitual de configuración con traducción real deshabilitada.

Se revisaron el informe M1, los documentos de arquitectura/operación y las
fuentes de sesiones, normalización, traducción, UI y overlay. El flujo real es:

```text
Operator → CAPTURE independiente → /ws/session autenticado
 → configuración de sesión → /asr?mode=full&language=en|es
 → TranscriptState → SegmentManager A → normalizador por idioma
 → TranslationEngine secuencial → DeepL source/target explícitos
 → Operator + CaptionHub → overlay OBS de solo lectura
```

El baseline fijaba `CAPTIONS_LANGUAGE` y los idiomas de traducción al cargar
el proceso; el proxy ya sustituía `language` y eliminaba `target_language` de
la URL WLK. Los glosarios de TerminologyNormalizer son españoles. SegmentManager
opera sobre palabras, límites y puntuación; no se cambiaron sus reglas ni thresholds.

La autoridad existente usa origen loopback, nonce de control, un propietario,
rotación de token/secret al recuperar Operator y una CAPTURE que sobrevive a su
recarga. Se conservan estos controles y el protocolo de capacidades explícitas.

## Limitación WLK demostrada y solución mínima

La [API upstream](https://github.com/QuentinFuxa/WhisperLiveKit/blob/main/docs/API.md)
documenta `language` por conexión. Esa documentación es de main y **no sustituye**
la inspección del 0.2.26 instalado.

La sonda `tests/probe_wlk_language.py` utiliza el factory y el procesador realmente
instalados, sustituyendo únicamente el decoder pesado por un doble que permite
observar su configuración. Resultado original: solicitud `language=en`, pero
decoder `cfg.language=es`. Es una prueba del contrato de configuración, sin audio.
El proxy genérico modifica `original_language` durante `transcribe()`, mientras
SimulStreaming construye AlignAtt con `asr.cfg.language` y no usa ese camino.

`app/asr/wlk_server.py` adapta el punto de entrada, sin editar site-packages:

- Restringido a WLK 0.2.26, Faster-Whisper y política SimulStreaming.
- Copia ligera del objeto backend y de su `cfg` por conexión; idioma `en` o `es`.
- Pesos y encoders compartidos; decoder/configuración separados por sesión.
- No muta el idioma global, no instala modelos y no crea un segundo servidor.
- Rechaza autodetección, idiomas no admitidos y parámetros duplicados.
- Anota el handshake con `session_language_isolation=1` y el idioma efectivo
  entregado al factory adaptado. Es una confirmación de configuración, no exactitud ASR.

La misma sonda verifica EN/ES/EN aislados, pesos compartidos y el cableado real
de ambos factories importados (`core` y `audio_processor`) y del middleware.
También ejecuta la inicialización real de opciones/tokenizer con un modelo
estructural mínimo: confirma idiomas y tokens EN/ES/EN distintos, sin pesos ni inferencia.
Uvicorn está simulado en esta sonda: su banner no indica un servidor arrancado.
No se actualizó WLK/Faster-Whisper ni se ejecutó inferencia real nueva.

## Dirección, cierre seguro y compatibilidad

`app/session_direction.py` define solo `en-es` y `es-en`. Operator anuncia y exige
la capacidad `session_direction=1` para usar el selector. El valor inicial es
EN → ES; no se modificaron variables históricas de `.env`.

La dirección se transmite al abrir el WebSocket autenticado de CAPTURE, antes
del envío PCM. FastAPI valida el par, copia Settings/TranslationConfig para esa
sesión y conserva ASR/source/target/modo de normalización como metadatos.
No existe API para mutarlos durante la sesión. Un segundo START se rechaza de
forma atómica; una pestaña rival no modifica la sesión del propietario.
Los clientes históricos que omiten dirección conservan la configuración previa
del servidor, con metadatos cuando corresponde a uno de los dos pares admitidos.

El nuevo cliente no usa una selección bidireccional si el backend no anuncia
esa capacidad: mantiene el modo histórico y el selector bloqueado. Una sesión
con dirección explícita exige además el handshake de aislamiento WLK correcto;
si falta o confirma otro idioma, se cierra antes de enviar PCM. Así, el arranque
estándar de WLK no produce una selección engañosa en la nueva funcionalidad.

El selector queda bloqueado durante STARTING/LIVE/STOPPING, incluyendo la espera
del popup antes de que exista socket y el intervalo entre stopped y cierre del
transporte. Refresh recupera la dirección autoritativa, sin abrir otro micrófono.
La selección viaja al popup por postMessage del mismo origen y ventana esperada.

Tras outcome `incomplete`, START y cambio de dirección permanecen bloqueados
hasta cierre completo y **Reconocer cierre incompleto**, con autorización del
propietario y session_id vigente. Ese reconocimiento **no cambia el outcome ni
reintenta contenido perdido**. La recuperación administrativa existente permite
resolver propietario ausente; no se añadieron mecanismos de acceso paralelo.
La liberación del gate de transporte está protegida también ante cancelación
del cierre, evitando un bloqueo permanente del flag de sesión.

## Normalización, traducción y salida

Inglés usa `IdentityNormalizer`: preserva exactamente raw_text, sin glosarios,
correcciones, sugerencias ni cambios de espacios. Se anuncia `normalization_mode=identity`.
Español conserva TerminologyNormalizer y los glosarios existentes, sin alterarlos.

TranslationEngine recibe source/target por sesión y DeepL los envía explícitos
como EN/ES o ES/EN; el contexto sigue separado del texto traducido. Se mantienen
cola, secuencias, límites, reintentos y aislamiento. Los resultados exitosos y
fallidos incluyen los dos idiomas.

Operator mantiene la traducción predominante, con etiquetas RAW/NORMALIZED y
destino dinámicas; muestra identidad inglesa y conserva diagnósticos. Los IDs
DOM históricos `english` se conservan por compatibilidad interna, sin fijar el
idioma mostrado. El overlay recibe metadatos y actualiza su atributo lang.

CaptionHub solo añade dirección/metadatos y rechaza captions cuyo par no coincida
con la sesión. Conserva protocolo v3, session_id, secuencias, CLEAR/watermarks,
persistent rolling, snapshots, reconexiones y limpieza al iniciar otra sesión.
No se traduce simultáneamente hacia dos destinos.

## Archivos de implementación

| Área | Archivos |
|---|---|
| Nuevos contratos y adaptación | `app/session_direction.py`, `app/asr/wlk_server.py`, `app/captions/identity_normalizer.py` |
| Sesiones y configuración | `app/main.py`, `app/operator_control.py`, `app/asr/whisperlivekit_client.py` |
| Metadatos de traducción/OBS | `app/translation/models.py`, `app/translation/engine.py`, `app/overlay/hub.py`, `app/static/overlay.js`, `app/templates/overlay.html` |
| Operator | `app/static/operator.js`, `app/static/operator_console.js`, `app/static/operator.css`, `app/templates/operator.html` |
| Pruebas | `tests/test_session_direction.py`, `tests/probe_wlk_language.py`, `tests/test_operator_console.cjs`, `tests/test_reliability.cjs`, `tests/test_reliability_browser.py`, `tests/test_release_e2e_browser.py` |
| Documentación | Este informe, `README.md` y adiciones a `INSTALL_WINDOWS.md` preservando M1 |

## Pruebas y resultados

| Comprobación | Resultado | Alcance |
|---|---|---|
| Dirigidas Python | **59 PASS**, 10.560 s | 7 nuevas + 52 existentes: direcciones, permisos/resume, cierre/ACK, transporte, normalización, DeepL falso, CLEAR/overlay |
| Chrome focalizado final | **2 PASS**, 10.404 s | Layout 1366×768 y 1920×1080; CAPTURE real con medio sintético, EN/ES, refresh y STOP |
| JavaScript | **6 suites PASS** | Estado UI, dirección, bloqueo antes/durante sesión, popup/recovery, CLEAR, EOF, overlay/geometría y aislamiento |
| WLK instalado | **PASS** | Factory original/adaptado, opciones/tokenizer reales, cableado de launcher con Uvicorn simulado |
| Regresión completa final | **187 PASS**, 381.475 s, OK, sin skips | Todos los tests Python disponibles, Chrome E2E y soak incluidos |
| Soak final | **Escenario esperado PASS**, 3603.304 s virtuales / 290.873 s reales | 600 READY, 5400/5400 palabras; 591 éxitos y 9 fallos inyectados; outcome `incomplete`; workers/cola/suscriptores finales 0 |

Las siete pruebas nuevas incluyen rechazo de dirección inválida/duplicada,
rechazo de handshake WLK ausente o incorrecto **sin enviar PCM**, configuración
inmutable con resume y pestaña competidora, reconocimiento de cierre incompleto
solo por propietario, EN identidad/ES glosario y EN/ES/EN con contexto aislado.
El adaptador DeepL real construye el body, pero un opener falso devuelve respuestas;
se verifican EN→ES/ES→EN explícitos y ausencia de contexto previo en cada START.

Problemas encontrados y corregidos: idioma SimulStreaming ignorado por el proxy
genérico; etiquetas fijas; normalización española aplicada sin distinguir idioma;
posible desbloqueo del selector durante el arranque del popup; gate de transporte
que debía liberarse aun si se cancela close. La primera regresión completa ejecutó
187 tests en 398.669 s y falló en **un gate de layout a 1366×768**. Se añadió una
fila compacta de dirección y se reservó su altura para mantener lectura/controles
dentro del viewport. La repetición Chrome focalizada pasó en ambos tamaños y
la segunda regresión completa pasó con 187/187. Su log es
`logs/bidirectional-final-regression.log`.
También se corrigió una espera del harness Chrome para pulsar START solo cuando
está habilitado, sin relajar las aserciones de sesión/idioma.

Los logs y JSON nuevos se guardan en `logs/bidirectional-*`; no sustituyen los
benchmarks S2-M1 ni los históricos M8. Todas las traducciones de pruebas usan
providers simulados o un opener HTTP falso del adaptador DeepL; cero llamadas
DeepL reales. Los navegadores utilizan perfiles temporales y micrófono sintético.
El E2E final conserva 888 eventos y primera sesión `complete` en
`logs/bidirectional-final-e2e.json`. El soak está en
`logs/bidirectional-final-soak.json`: sus nueve pérdidas simuladas explican
`incomplete`, como en M1; limpieza de recursos no equivale a entrega completa.
No se presenta esa simulación como una sesión física satisfactoria.

Comandos de reproducción, desde el repositorio y en una terminal de pruebas:

```powershell
$env:TRANSLATION_ENABLED='0'
$env:M8_E2E_OUTPUT='logs/bidirectional-retest-e2e.json'
$env:M7_SOAK_OUTPUT='logs/bidirectional-retest-soak.json'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv-wlk\Scripts\python.exe -m tests.probe_wlk_language
```

Las seis suites `.cjs` se ejecutaron con
`C:\Program Files\nodejs\node.exe` v24.20.0. Cerrar la terminal de pruebas antes
de arrancar la operación real: `TRANSLATION_ENABLED=0` prevalece sobre `.env`.

## Validación física posterior (no ejecutada)

1. Esperar cierre real de la sesión anterior. Registrar dirección, commit/diff,
   equipo, driver, navegador y versión OBS. La revisión no autoriza producción.
2. En ventana de mantenimiento, arrancar WLK con el nuevo procedimiento de
   [INSTALL_WINDOWS.md](INSTALL_WINDOWS.md#mvp-bidireccional--arranque-posterior-a-s2-m1)
   y FastAPI con `.venv`, un worker, loopback 8010. No cambiar dependencias,
   glosarios, modelo ni credenciales. No ejecutar dos WLK en el puerto 8000.
3. Cargar Operator actualizado y refrescar caché del Browser Source OBS con la
   sesión detenida. URL overlay habitual, 1920×1080; conservar geometría M1.
4. Elegir **English → Español**, Blue Yeti y START. Confirmar RAW EN, NORMALIZED EN
   identidad y ESPAÑOL predominante. Verificar que no aparecen captions de la
   sesión anterior y que el selector permanece bloqueado.
5. Leer en inglés, con pausas naturales, este texto público de ensayo:

   > This lecture reviews hypertension and cardiovascular prevention. We will
   > discuss blood pressure, left ventricular function, ejection fraction, and
   > pulmonary congestion. The example patient has no chest pain and no pulmonary
   > edema. The slide shows a blood pressure of 120 over 80 millimeters of mercury.
   > The number five milligrams is included only to test transcription of units.

6. Tras ver español en OBS, pulsar CLEAR. Continuar: “The next slide discusses
   angiotensin converting enzyme inhibitors and mineralocorticoid receptor
   antagonists.” Comprobar que reaparece solo contenido posterior a CLEAR.
7. Recargar solo Operator: misma sesión/dirección y una sola CAPTURE; continuar
   hablando y comprobar OBS. No cerrar CAPTURE durante LIVE.
8. STOP, esperar flush/drain, outcome y cierre completo. No tratar `incomplete`
   como éxito. Registrar errores y reconocer la pérdida si corresponde; esto no
   recupera palabras. Cerrar la CAPTURE terminada antes de un nuevo START.
9. Elegir **Español → English**, START y leer: “Esta conferencia revisa la
   hipertensión y la prevención cardiovascular. No hay dolor torácico ni edema
   pulmonar. Revisaremos la fracción de eyección y las presiones de llenado.”
   Repetir CLEAR → continuación → STOP. Verificar glosario español y salida inglesa,
   secuencias nuevas y ausencia de texto/contexto de la sesión anterior.
10. Guardar observaciones RAW/NORMALIZED/destino por session_id/segment_id:
    negaciones, lateralidad, números/unidades, omisiones y duplicaciones. Revisar
    significado médico con persona competente. El ensayo corto no sustituye
    estabilidad prolongada ni validación de proyector físico.

Las llamadas reales de ese ensayo deben ser supervisadas y autorizadas por el
usuario antes de START. No fueron realizadas por esta implementación.

## Rollback controlado

No ejecutar rollback en LIVE. Conservar primero el diff y los archivos nuevos de
esta entrega en una copia local; no incluir `.env`, `.runtime` ni secretos.
Si existen cambios posteriores de otra persona en los mismos archivos, detener
la restauración y conciliarlos antes de sobrescribirlos.

Para recuperar el código original, restaurar **solo los archivos versionados
de implementación de app/tests enumerados arriba** desde `64f8221`, revisando
el diff antes y después. Por ejemplo, `git restore --source=64f8221 -- app tests`
es válido únicamente si no hay otros cambios en esos directorios. Los tres
módulos nuevos pueden conservarse inactivos: el código baseline no los importa.
Antes de ejecutar discovery del baseline, mover `tests/test_session_direction.py`
y `tests/probe_wlk_language.py` a la copia de respaldo, pues prueban contratos
de esta entrega que no existen en el baseline. No hace falta borrarlos.

**No restaurar ni eliminar** `INSTALL_WINDOWS.md`, `S2-M1-REPORT.md`,
`benchmarks/s2_m1_*`, `.env` ni los entornos virtuales. Mantener también este
informe y los logs para trazabilidad; README puede conservar la nota de entrega
aclarando que se hizo rollback. No usar reset hard, git clean ni alterar main/tag.

Reiniciar manualmente el WLK estándar con `small --lan es --pcm-input` y PATH
CUDA temporal como en M1. Arrancar el FastAPI baseline en otra terminal; si se
necesita forzar el par histórico sin editar `.env`, establecer solo en esa
terminal `CAPTIONS_LANGUAGE=es`, `TRANSLATION_SOURCE_LANGUAGE=es` y
`TRANSLATION_TARGET_LANGUAGE=en`. Recargar Operator/Browser Source con sesión
detenida y validar ES → EN. No cambiar credenciales ni instalar paquetes.

## Reservas y detención

- El nuevo aislamiento se probó contra el código WLK instalado con decoder doble;
  falta inferencia física inglesa y alternancia real en GPU. No se certifica ASR.
- Sin glosario inglés clínicamente validado; identidad es deliberada. Los riesgos
  médicos documentados en M1 siguen abiertos.
- No hay nueva medición física de latencia, validación térmica ni ensayo de
  60–90 minutos/proyector. El soak es virtual.
- La adaptación depende del contrato interno de WLK 0.2.26 y está restringida a
  esa versión/política. Una actualización futura requiere reauditarla.
- Los clientes históricos sin dirección conservan la configuración del proceso;
  usar Operator actualizado para seleccionar explícitamente el par.
- El entorno ASR continúa sin lock portable completo y su exclusión Git es local,
  como se documentó en M1.

No hubo commits, tags, push, despliegues ni modificación de main/RC. Se entrega
para revisión y ensayo supervisado; detener aquí. No iniciar optimización médica,
semantic early commit ni otros milestones sin revisión del usuario.

## Estado final de Git

HEAD, main y el commit del RC siguen en `64f8221`; solo existe el tag
`v0.1.0-rc1`. Sin staging, commits, tags nuevos ni push. Los tres SHA-256 de
S2-M1 coinciden con el informe original. No hay diferencias en benchmarks
históricos, glosarios, SegmentManager ni archivos de dependencias.

```text
## sprint2/m1-rtx4070
 M INSTALL_WINDOWS.md
 M README.md
 M app/asr/whisperlivekit_client.py
 M app/main.py
 M app/operator_control.py
 M app/overlay/hub.py
 M app/static/operator.css
 M app/static/operator.js
 M app/static/operator_console.js
 M app/static/overlay.js
 M app/templates/operator.html
 M app/templates/overlay.html
 M app/translation/engine.py
 M app/translation/models.py
 M tests/test_operator_console.cjs
 M tests/test_release_e2e_browser.py
 M tests/test_reliability.cjs
 M tests/test_reliability_browser.py
?? BIDIRECTIONAL_MVP_REPORT.md
?? S2-M1-REPORT.md
?? app/asr/wlk_server.py
?? app/captions/identity_normalizer.py
?? app/session_direction.py
?? benchmarks/s2_m1_e2e_results.json
?? benchmarks/s2_m1_replay_results.json
?? benchmarks/s2_m1_soak_results.json
?? tests/probe_wlk_language.py
?? tests/test_session_direction.py
```
