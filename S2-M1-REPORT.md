# TRAD — Sprint 2 / M1: auditoría de migración RTX 4070

Fecha de auditoría: **2026-10-20**, zona de referencia America/La_Paz.
Repositorio: `C:\live-captions`; remoto configurado
`https://github.com/josuefatule/trad.git`.

## 1. Dictamen ejecutivo y alcance

**Recomendación formal: GO CON RESERVAS para el cierre técnico de S2-M1.**
La Alienware ejecuta la instalación migrada, los entornos coinciden con los pins
comprobables, CUDA reconoce la RTX 4070 y ambos servicios existentes responden
en loopback. El usuario confirmó previamente el recorrido físico Blue Yeti →
ASR español → normalización → DeepL → Operator/OBS. La documentación incorpora
el arranque con DLL locales, sin modificar globalmente Windows.

Este dictamen admite como evidencia funcional las confirmaciones previas del
usuario; no afirma que esta auditoría haya repetido esa sesión. La reproducibilidad
operativa del entorno existente está respaldada; una instalación ASR desde cero,
con wheels/cachés fijados, no ha sido demostrada independientemente. Si se exige
esa reinstalación como condición previa de M1, ese gate permanece **PENDIENTE**
y el cierre incondicional no procede.

**Aceptación del congreso: NO-GO con la evidencia disponible.** Los errores de
significado médico observados, la falta de ensayo real prolongado y la falta de
validación del proyector impiden declarar TRAD listo para ese uso. Esto no cambia
el objetivo limitado de M1: migración funcional, conservación del baseline,
procedimiento de operación y caracterización de riesgos.

Trabajo limitado a lectura/auditoría, comprobaciones acotadas y documentación.
Sin nueva funcionalidad, optimización, cambios de glosario, SegmentManager,
traducción, modelo, dependencias, credenciales ni sesiones. No se inició M2.
El cierre requiere aprobación expresa del usuario; este documento no la sustituye.

## 2. Fuentes y fuerza de la evidencia

| Clase | Fuentes | Límite |
|---|---|---|
| Comprobación nueva | Git, CIM, NVIDIA-SMI, metadata Python, ambos `pip check`, parser WLK, detección CUDA, GET health/modelos, listeners, 7 tests Python y 6 suites JS | Sin nueva inferencia, micrófono, DeepL ni OBS |
| Artefactos S2-M1 preexistentes | Tres JSON `benchmarks/s2_m1_*_results.json`, leídos y preservados | No son una nueva ejecución durante esta auditoría |
| Confirmación del usuario | 180 Python PASS/363.685 s, seis suites JS PASS, inferencia GPU, sesión física y tres marcas audiovisuales | No se aportó transcript íntegro de esa ejecución Python; no convertirlo en log inspeccionado |
| Historia Sprint 1 | Documentos v0.1, JSON `m8_*`, fixture ASR y `M5_2_RESULTS.json` | Hardware/ejecuciones distintos; conservar separados |

Documentación inspeccionada: `README.md`, `ARCHITECTURE.md`, `PLAN.md`,
`INSTALL_WINDOWS.md`, `RELIABILITY_RUNBOOK.md`, `VALIDATION_REPORT_V0_1.md`,
`LATENCY_BASELINE_V0_1.md`, `RELEASE_CHECKLIST_V0_1.md`,
`MANUAL_VALIDATION_V0_1.md`, `OBS_OVERLAY.md`, `requirements-release.lock`,
`benchmarks/m8_environment.json` y fuentes/pruebas citadas a continuación.
README/PLAN mantienen el estado histórico de Sprint 1, incluido «No iniciar
Sprint 2»; el encargo explícito actual autoriza exclusivamente S2-M1.
No se reescribieron casillas históricas como si fueran aceptación nueva.
El inventario M8 describe Windows build 26200 / GTX 1650 SUPER en la documentación,
no la Alienware. Los resultados S2 se recogen aquí y en la nueva sección de instalación.

## 3. Estado Git y conservación del baseline

Comprobaciones iniciales, antes de editar:

| Elemento | Resultado |
|---|---|
| Rama | `sprint2/m1-rtx4070` |
| HEAD | `64f82214b33fad4ee68295df1367249caeae3187` |
| `main`, `origin/main` local y `origin/HEAD` | `main` y referencia remota local en `64f8221`; `origin/HEAD -> origin/main` |
| Tag anotado RC | objeto `87a25e093c673d9594407188efa00854826eccb6`; commit resuelto `64f82214b33fad4ee68295df1367249caeae3187` |
| Tags locales | Solo `v0.1.0-rc1`; sin `v0.1.0` |
| Remoto | `origin` fetch/push con URL esperada |
| Archivos versionados | Sin cambios staged ni unstaged; diff con RC vacío |
| No versionados previos | Solo los tres JSON S2-M1 indicados |

No se hizo fetch ni consulta al estado vivo de GitHub: `origin/main` es una
referencia local. La integridad verificada es la del checkout y sus referencias
locales. No se crearon commits, tags, ramas, push ni despliegues.

SHA-256 de los archivos preservados, cotejados antes y después:

| Archivo en `benchmarks/` | SHA-256 |
|---|---|
| `s2_m1_e2e_results.json` | `593cdf7dd3eb2ff98164ae630c167d91b0d4ae32bd47f3b020c778685edc0ff4` |
| `s2_m1_replay_results.json` | `6442885c7566af9cc0488598eacef3a4671f8946b1b5b9e2419fb994a940b395` |
| `s2_m1_soak_results.json` | `1cf480f2e5ad9a9280b6342bb18a8387191598e3e90c8e7888519b67bdd8fc20` |

El fixture `medical_full_receive.json.gz` conserva el hash
`6e4850702c084614cf62ad72a824d7f51384b16ea4c3416fadc7c764749d55b7`,
coincidente con las referencias de replay y E2E.

## 4. Hardware real e inventario de software

| Componente | Declarado / previo | Observado en esta auditoría |
|---|---|---|
| Equipo | Alienware m16 R1 | CIM: Alienware / Alienware m16 R1 |
| Sistema | Windows 11 Pro x64, 10.0.26300 | CIM confirma edición, versión, build 26300 y 64-bit |
| CPU | i7-13700HX | CIM: 13th Gen Intel Core i7-13700HX |
| RAM | Aproximadamente 16 GB | CIM: 16,853,450,752 bytes, aproximadamente 15.70 GiB |
| GPU | RTX 4070 Laptop, aproximadamente 8 GB | NVIDIA-SMI y Torch: RTX 4070 Laptop GPU; 8188 MiB |
| Driver / CUDA anunciada | 596.08 / 13.2 | NVIDIA-SMI confirma ambos |
| Potencia | Lectura previa de cap 122 W | Tabla NVIDIA-SMI mostró 7 W / 115 W; consulta power.limit N/A, default 90 W y max 140 W |

Los valores de potencia corresponden a consultas distintas y pueden depender
del estado/perfil del equipo. No se cambiaron límites ni se estableció su causa.
Una muestra de 57 °C y 1676 MiB ocupados no caracteriza temperatura o VRAM máximas.
No se ejecutó inferencia sostenida ni ensayo térmico prolongado.

| Entorno | Resultado verificado sin modificar dependencias |
|---|---|
| `.venv` | CPython 3.12.10; los 21 paquetes fijados en `requirements-release.lock` coinciden por metadata; `pip check` PASS |
| HTTP aplicación | FastAPI 0.141.1, Uvicorn 0.53.0, websockets 17.1 |
| `.venv-wlk` | CPython 3.12.10; `pip check` PASS |
| ASR | WhisperLiveKit 0.2.26; faster-whisper 1.2.1; CTranslate2 4.8.2 |
| Torch / audio | 2.14.0+cu126 / 2.11.0+cu126; Torch informa build CUDA 12.6 |
| Node instalado | `C:\Program Files\nodejs\node.exe`: v24.20.0; `npm.cmd`: 11.19.0 |
| Node resuelto por esta herramienta | v24.19.0 desde `C:\Users\JF\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe`; npm ausente del PATH de la herramienta |

Las suites nuevas usaron explícitamente Node instalado v24.20.0. La diferencia
del PATH no demuestra que la instalación Node del usuario sea incorrecta.
`pip check` acredita consistencia declarativa de dependencias, no compatibilidad
binaria exhaustiva ni calidad del reconocimiento.

## 5. Instalación, seguridad y CUDA

El [procedimiento vigente](INSTALL_WINDOWS.md#s2-m1--alienware-rtx-4070-procedimiento-vigente)
separa los dos venv y contiene un bloque PowerShell con PATH temporal y restauración
en `finally`. Ejecuta exclusivamente `.venv-wlk\Scripts\wlk.exe`; FastAPI usa
`.venv\Scripts\python.exe` en otra terminal. No se añadió script ni infraestructura.
El bloque fue comprobado sin arrancar otro servicio; el arranque efectivo previo
es evidencia del usuario y la disponibilidad actual se verificó por GET.

Incidente CUDA previo: `RuntimeError: Library cublas64_12.dll is not found or
cannot be loaded`. Se verificó la presencia de las DLL en
`C:\live-captions\.venv-wlk\Lib\site-packages\torch\lib`. El usuario resolvió el
problema anteponiendo esa carpeta al PATH de su PowerShell y confirmó inferencia
`small` en GPU sin excepciones y arranque WLK. No se reprodujo deliberadamente el
fallo ni se volvió a cargar el modelo para inferencia durante la auditoría.

Nueva comprobación aislada, anteponiendo esa ruta solo al proceso Python:
`torch.cuda.is_available()=True`, `device_count()=1`, dispositivo RTX 4070 Laptop,
`ctranslate2.get_cuda_device_count()=1`. Esta detección no prueba por sí sola que
se haya ejecutado una nueva operación cuBLAS ni un benchmark GPU.
CUDA 13.2 anunciada por el driver y build Torch 12.6 son datos distintos;
no se infiere un Toolkit 13.2 instalado.

Configuración contrastada con `.env.example`, `app/environment.py`,
`app/main.py` y `app/translation/engine.py`: `TRANSLATION_ENABLED=1`, provider
`deepl`, origen `es`, destino `en`, credencial `DEEPL_API_KEY` y alias heredado
`DEEPL_AUTH_KEY`. El primero prevalece; la credencial se excluye del repr.
La carga de `.env` no sustituye variables ya presentes en la terminal.
No se leyó ni modificó `.env`, no se imprimieron secretos y no se hizo ninguna
nueva solicitud DeepL. Las pruebas usan credenciales ficticias y providers de prueba.

`git ls-files` no encontró `.env` ni archivos de los dos venv versionados.
`git check-ignore -v`: `.env` y `.venv/` por `.gitignore`; `.venv-wlk/` por
`.git/info/exclude:7`. **La exclusión ASR solo es local.** En un nuevo clon hay
que reproducirla antes de crear el entorno; se propone una regla versionada
`.venv-wlk/` en una modificación posterior autorizada. No se cambió Git ignore
porque el permiso actual de correcciones está limitado a documentación y arranque.

## 6. Arquitectura operativa y servicios existentes

Comando WLK contrastado con `cli.py` y el parser instalado:

```powershell
.\.venv-wlk\Scripts\wlk.exe serve --backend faster-whisper --model small --lan es --pcm-input --host localhost --port 8000
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

Son comandos de referencia para un futuro arranque con sesión detenida, no
comandos ejecutados para duplicar los servicios. `serve` se elimina antes de
delegar al servidor; `--lan`/`--language` son alias. El parser se ejecutó por
separado sin crear motor: `backend=faster-whisper`, `model_size=small`, `lan=es`,
`pcm_input=True`, `host=localhost`, `port=8000`, `backend_policy=simulstreaming`.

| Consulta nueva | Resultado |
|---|---|
| WLK `GET /health` | HTTP 200; `status=ok`, `backend=faster-whisper`, `ready=true` |
| WLK `GET /v1/models` | HTTP 200; `faster-whisper/small` |
| FastAPI `GET /health` | HTTP 200; `status=ok`, `language=es`, `wlk_check=on_session_connect` |
| Listeners | WLK PID 27132 en `127.0.0.1:8000` y `[::1]:8000`; FastAPI PID 27708 en `127.0.0.1:8010` |

PID y listeners son una fotografía puntual. Las consultas CIM/sockets inicialmente
no estaban disponibles dentro del sandbox; se repitieron con acceso de lectura
aprobado. No se modificaron procesos ni puertos.
Health no acredita una nueva transcripción ni disponibilidad de la cuenta DeepL.

Operator `http://localhost:8010/operator`; overlay `http://localhost:8010/overlay`.
CAPTURE/Blue Yeti, reconocimiento real, TerminologyNormalizer, DeepL, inglés en
Operator y Browser Source OBS son validación funcional previa confirmada por el
usuario. No hubo inspección visual nueva de OBS ni validación de proyector.
La geometría documentada 1920×1080, región Y=930/150 px, fuente 48 e interlineado
1.2 ofrece dos líneas efectivas; los tres solicitados se limitan por capacidad.

## 7. Pruebas automatizadas: nuevas frente a previas

Ejecución nueva y acotada, sin micrófono ni red de traducción:

```powershell
$env:TRANSLATION_ENABLED='0'
.\.venv\Scripts\python.exe -m unittest tests.test_environment tests.test_release_validation -v
```

**7 tests PASS, 0.455 s, OK**, sin skips: carga/configuración de entorno,
precedencia/alias, protección del repr, negaciones/números/unidades sintéticos,
replay real offline, invariantes de percentiles y correlación de relojes.
El test de replay recalculó en memoria la integridad del fixture y su p95;
no escribió ni regeneró los tres JSON preservados.

Se repitieron con `C:\Program Files\nodejs\node.exe` las seis suites siguientes;
todas reportaron **PASS**:

- `tests/test_operator_console.cjs`
- `tests/test_operator_partial.cjs`
- `tests/test_overlay_renderer.cjs`
- `tests/test_persistent_captions.cjs`
- `tests/test_overlay_geometry.cjs`
- `tests/test_reliability.cjs`

Estas suites comprueban lógica JS/DOM simulado y no equivalen a una nueva
ejecución Chrome E2E ni OBS. Los mensajes de reconexión y agotamiento del renderer
son escenarios de la suite, no incidentes nuevos del servicio activo.

Evidencia previa declarada: **180 pruebas Python, 180 PASS, 363.685 s, OK** y
las seis suites JS PASS. No se reejecutó el discovery completo, el E2E Chrome
temporizado ni el soak de aproximadamente 284 s. Se conservan como evidencia
previa; no se presenta la duración comunicada como medida nueva ni como transcript
íntegro disponible. No se solicitó una ejecución costosa innecesaria para editar docs.

## 8. Replay, E2E y soak preservados

### Replay A

`s2_m1_replay_results.json`, generado `2026-10-20T04:17:29.890473+00:00`:
888 eventos, 58.3 s de fixture, 17 READY, palabras 81/81 con igualdad ordenada,
IDs únicos, cero revisiones tardías y pending vacío al terminar.
ASR confirmado → READY: mediana **3751 ms**, p95 **5539 ms**.
Cinco de doce unidades médicas anotadas están fragmentadas; nueve cortes
whitespace forzados. El fixture reducido produce 16 segmentos y es la misma
grabación, no una muestra independiente.

Configuración A preservada: estabilidad 0.8 s, silencio 1.0 s, mínimo/objetivo/
máximo 7/13/21 palabras, lookback 8, edad soft 3.3 s, hard 5.5 s y tick 0.1 s.
La integridad 81/81 conserva el texto reconocido, incluidos sus errores;
no demuestra exactitud médica frente a lo pronunciado.

### E2E automatizado

`s2_m1_e2e_results.json`, generado `2026-10-20T04:08:03.058371+00:00`:
17 publicaciones; mediana ASR → READY **3750 ms**, p95 **5532 ms**;
READY → NORMALIZED mediana **16 ms**; ASR → CaptionHub mediana **3781 ms**.
Primera sesión `complete`; cero muestras paint ausentes, cola máxima 1.
Las filas permiten correlacionar sesión, segmento, secuencia y generación visual.

La prueba usa PCM sintético, ASR registrado con tiempos originales, normalizador
real, provider simulado y Chrome real. `tests/test_release_e2e_browser.py` crea
servidores aislados y no usa los puertos de producción. No mide Blue Yeti,
inferencia GPU actual, latencia DeepL, compositor OBS ni salida física.
Double-requestAnimationFrame es una estimación de pintado de navegador.

### Soak: interpretación obligatoria de `incomplete`

`s2_m1_soak_results.json`: **3603.304 s virtuales**, **284.127 s reales**;
600 READY, integridad **5400/5400** palabras; 591 traducciones simuladas exitosas,
9 fallidas, 16 retries, 608 llamadas simuladas; outcome **`incomplete`**.
Tras cierre: workers 0, cola 0, suscriptores 0; tareas 1→1, threads 2→2.
Journal máximo 512 eventos / 599185 bytes, 388 truncados; caption history máximo
128; un suscriptor lento desalojado. Son límites ejercitados deliberadamente.
`tracemalloc` no mide RSS completo, VRAM ni estabilidad térmica.

La inspección establece la siguiente cadena causal dentro de la simulación:

1. `benchmarks/reliability_soak.py` inyecta HTTP 403 para secuencia 100, pérdida de
   red en el primer intento de múltiplos de 37 y rearme cuando `ready_count>=110`.
2. `app/translation/engine.py` clasifica 403 como error permanente `provider_auth`;
   mientras el circuito está abierto genera resultados fallidos sin llamar al
   proveedor. `rearm()` permite futuras entradas, no reenvía las ya fallidas.
3. El callback retiene cada resultado en `OperationalRun`. En `app/reliability.py`,
   cualquier contador de traducciones fallidas hace que stopped sea `incomplete`,
   aunque luego el traductor vuelva a READY y el drain se vacíe.
4. `tests/test_reliability_soak.py` exige explícitamente
   `assertEqual(report["stop_outcome"], "incomplete")` por los fallos inyectados.

**Conclusión:** `incomplete` es el resultado esperado del escenario con pérdidas
inyectadas, coherente con código, test y artefacto. No hay evidencia aquí de un
defecto nuevo de limpieza STOP. Sí hubo nueve resultados sin traducción exitosa;
el outcome conserva esa pérdida. La limpieza es satisfactoria dentro del harness,
la entrega de la sesión es incompleta. El harness llama finish/wait_idle/close
directamente; no acredita toda la barrera EOF de un STOP físico con servicios reales.
No se cambió código ni se reinterpretó el resultado como `complete`.

## 9. Experimento físico exploratorio — Nivel A

Fuente: marcas de una grabación externa proporcionadas por el usuario, quien
confirmó que Audio indica **fin de pronunciación del bloque**. No se encontraron
videos `.mp4`, `.mov`, `.mkv`, `.avi` o `.webm` en el inventario del repositorio.
No se inspeccionaron videos originales; la auditoría recalcula las marcas dadas.

| Bloque | Fin audio (s) | RAW (s) | NORMALIZED (s) | ENGLISH (s) | Fin→RAW | Fin→NORMALIZED | Fin→ENGLISH |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | 17.40 | 18.50 | 20.81 | 20.82 | 1.10 s | 3.41 s | 3.42 s |
| 2 | 32.45 | 34.85 | 34.85 | 34.85 | 2.40 s | 2.40 s | 2.40 s |
| 3 | 44.50 | 46.94 | 46.95 | 48.95 | 2.44 s | 2.45 s | 4.45 s |
| Mediana exploratoria, n=3 | | | | | **2.40 s** | **2.45 s** | **3.42 s** |

Solo tres observaciones; sin p95 presentado como robusto. FPS, frame de aparición,
sincronización audiovisual e incertidumbre no están disponibles para verificación.
La coincidencia de paneles en 34.85 s no prueba que DeepL tardara cero ms.
Son observaciones visuales externas, sin correlación interna por segment_id;
no miden inicio de frase → salida, ni proyector físico. No comparar directamente
estas medianas con ASR → READY, que empieza en otra referencia temporal.
La medida es exploratoria y no certifica rendimiento.

## 10. Hallazgos de precisión médica

Problemas físicos **reportados por el usuario**, sin trazas correlacionadas
completas disponibles para establecer causas raíz:

| Hallazgo | Etapa que puede afirmarse / investigación pendiente |
|---|---|
| «Fracción de eyección» reconocida como «fracción de inyección» | Error de reconocimiento reportado; confirmar captura RAW y compararla con NORMALIZED por ID |
| «Presiones de llenado» convertida en expresiones incorrectas | Error observado; localizar primera divergencia en RAW/NORMALIZED/ENGLISH |
| «Enzima convertidora de angiotensina» mal reconocida | Reconocimiento reportado; comprobar supervivencia/cambio en normalización y traducción |
| Confusión con antagonistas de receptores de mineralocorticoides | Problema observado; atribución de etapa pendiente |
| Fragmentación de «inhibidores del cotransportador sodio-glucosa tipo 2» | Corte reportado; correlacionar límites ASR/READY antes de atribuirlo al manager |
| Traducción incorrecta de «congestión pulmonar» | Problema en salida inglesa reportado; validar la entrada NORMALIZED exacta enviada al provider |
| Duplicaciones y formulaciones extrañas en inglés | Problema observado tras traducción/visualización; separar respuesta provider de ensamblaje/renderer |
| Diferencias RAW/NORMALIZED/ENGLISH entre ejecuciones | Variabilidad reportada; ejecuciones distintas no permiten inferir qué componente introdujo cada cambio |

La revisión debe separar: **(1)** error ya presente en RAW, **(2)** cambio
introducido o error no corregido en NORMALIZED, **(3)** divergencia surgida en
respuesta traducida y **(4)** posible defecto de segmentación/ensamblaje.
La falta de corrección conservadora no equivale a haber introducido el error.
No se atribuyen automáticamente estos hallazgos a DeepL ni a SegmentManager.

Hay evidencia histórica adicional inspeccionable en
`benchmarks/M8_MEDICAL_SEGMENTS.md`, `M5_2_RESULTS.json` y el replay:
RAW `systólica`, `herenina` y `al dosterona`; tres correcciones de normalización
en el replay; unidades partidas y casos ingleses históricos de pérdida de
lateralidad/duplicación. Son ejemplos de aquel corpus, no trazas de las tres
observaciones físicas actuales. No se alteraron glosarios ni ASR.

## 11. Exploración limitada de inglés y dependencias de M5

La fuente de verdad aquí es **el paquete 0.2.26 instalado**, no una versión
actual de Internet. Parser: `parse_args.py:211` define `--lan`/`--language`,
destino `lan`. Se ejecutó el parser con `--lan en` y los demás flags del comando
operativo: **aceptado**, `model_size=small`, política `simulstreaming`.
Esto no es una prueba de voz inglesa.

`basic_server.py:104` recibe `?language=` por WebSocket y lo pasa a
`AudioProcessor`; `audio_processor.py:202` lo entrega a `online_factory`.
`core.py:422–432` aplica `SessionASRProxy`, cuyo `transcribe()` sustituye
temporalmente `original_language` bajo lock. Por tanto existe un mecanismo
de selección por conexión en el código WLK; no se puede concluir que todos
los backends lo apliquen correctamente.

**Reserva concreta de la política activa:** `simul_whisper/backend.py:369–373`
crea `AlignAttConfig(language=self.lan)` al construir el backend compartido;
`SimulStreamingOnlineProcessor._create_alignatt` usa `self.asr.cfg` y su
`SimulStreamingASR.transcribe` es un método vacío. No se encontró
`original_language` en esa implementación. Esto sugiere una incompatibilidad
entre el proxy genérico y el camino SimulStreaming: cambiar el query por sí
solo podría no cambiar el idioma efectivo. Es una **hipótesis de integración
pendiente**, no una demostración por audio. Para cambiar el idioma de arranque
mediante CLI se requiere reiniciar el proceso en una ventana con sesión detenida;
no se ensayó ese reinicio ni se ofrece como selector operativo.

TRAD ya fija `mode=full` y `language=settings.language` en
`app/asr/whisperlivekit_client.py:24`, elimina `target_language` del upstream,
y `Settings.language` proviene de `CAPTIONS_LANGUAGE` al cargar el proceso.
`TranslationConfig` carga source/target de entorno; no hay selección coordinada
por sesión en la aplicación actual. Cambiar solo el comando WLK no acredita
EN→ES ni una interfaz bidireccional.

M5 debe validar idioma ASR efectivo en esta política, aislar configuración/contexto
por sesión, coordinar idioma origen/destino del traductor, normalización por idioma,
etiquetas de UI/overlay, protocolo de sesión y pruebas de aislamiento/reinicio.
Debe decidir si el cambio requiere procesos separados, reinicio controlado u otra
integración validada. No se implementó selector, autodetección, traducción WLK
ni reconocimiento bilingüe.

## 12. Registro de incidencias, riesgos y transferencia

Solo M5 tiene asignación formal ES↔EN en el encargo; el repositorio no contiene
un roadmap detallado S2-M2–M4. Las asignaciones restantes son **propuestas de
destino**, sujetas a aprobar ese roadmap, y no autorización para ejecutarlas.

| ID | Clase | Hallazgo / impacto | Destino y acción posterior |
|---|---|---|---|
| R01 | Confirmado | DLL cuBLAS existentes requieren ruta de búsqueda en el arranque observado | M1 documentado; ensayo de reinstalación independiente antes de aceptación |
| R02 | Limitación conocida | ASR sin lock completo de wheels/cachés/índices; instalación limpia no repetida | Cierre de reproducibilidad M1 / gate de aceptación posterior: archivar artefactos y probar copia aislada |
| R03 | Confirmado | `.venv-wlk` excluido solo localmente; nuevo clon no hereda la regla | M1 seguimiento documental; proponer `.gitignore` versionado con permiso posterior |
| R04 | Confirmado | Soak entrega incompleta por fallos inyectados, con limpieza verificada | M1 aclarado; aceptación posterior debe observar STOP físico y ausencia de pérdidas no inyectadas |
| R05 | Limitación conocida | Sin benchmark GPU sostenido ni validación térmica prolongada; potencia puntual variable | Milestone de rendimiento/estabilidad a asignar; ensayo supervisado antes del congreso |
| R06 | Riesgo de aceptación | Errores médicos físicos y salida inglesa defectuosa reportados | Milestone de calidad a asignar; corpus independiente y revisión competente por etapa/ID |
| R07 | Confirmado | Replay fragmenta 5/12 unidades; latencia ASR→READY mediana ~3.75 s | Propuesta S2-M2 si cubre latencia/segmentación; investigar sin cambiar A en M1 |
| R08 | Hipótesis pendiente | Parte de duplicación/omisión podría depender de segmentación/contexto/ensamblaje | Milestone de calidad/segmentación a asignar; contrastar entradas y respuestas exactas, sin atribución automática |
| R09 | Limitación conocida | Nivel A n=3, sin video original/FPS ni referencia por segmento | Milestone de validación a asignar; protocolo audiovisual con incertidumbre y muestra mayor |
| R10 | Riesgo de aceptación | Sin 60–90 min reales ni proyector físico ni acta clínica nueva | Gate final previo al congreso; ejecutar protocolo manual con cuota autorizada |
| R11 | Hipótesis pendiente | Override de idioma por sesión puede no aplicarse a SimulStreaming | **S2-M5**: comprobar idioma efectivo con audio y estrategia de aislamiento |
| R12 | Confirmado | TRAD usa idioma/configuración de traductor de proceso, sin selector por sesión | **S2-M5**: diseño ES↔EN coordinado, sin implementación en M1 |
| R13 | Limitación conocida | 180 PASS/363.685 s provienen del brief; transcript íntegro no localizado | Cierre M1: conservar atribución; archivar log en futuro ensayo autorizado |
| R14 | Confirmado | PATH de herramienta resuelve Node distinto al instalado | M1 documentado y suites nuevas ejecutadas con ruta absoluta |
| R15 | Limitación conocida | Baseline RC y referencias comprobados localmente; GitHub vivo no consultado | M1: alcance local explícito; comparar remoto en revisión posterior si se requiere |
| R16 | Riesgo de aceptación | PARTIAL vacío en fixture, ventanas acotadas e incerteza de consumo por retries del baseline | Aceptación/operación posterior: preservar diagnósticos y controlar cuota; no prometer recuperación de audio |

## 13. Gates y criterios de cierre

| Gate | Evidencia | Resultado | Reserva | Acción siguiente |
|---|---|---|---|---|
| G1 Baseline y Git | HEAD/main/tag resuelto a `64f8221`, diff inicial vacío, hashes conservados | PASS local | No verificación remota viva | Revisar diff documental; conservar RC |
| G2 Entornos migrados | 2× Python 3.12.10, 21 pins iguales, 2× pip check PASS | PASS | ASR no es lock portable | Ensayar reinstalación independiente |
| G3 CUDA funcional | Una GPU en Torch/CT2; DLL presentes; inferencia GPU previa confirmada | PASS con evidencia previa | Sin inferencia nueva ni carga sostenida | Benchmark/ensayo térmico posterior autorizado |
| G4 Operación ES→EN | Health/modelos/listeners actuales + sesión Blue Yeti/DeepL/OBS confirmada | PASS funcional | No repetida durante auditoría; calidad insuficiente | Revisión médica y ensayo supervisado |
| G5 Arranque reproducible existente | Procedimiento de dos venv, PATH temporal, parser y sintaxis comprobados | PASS documental/operativo previo | No se arrancó copia nueva; exclusión ASR local | Revisar procedimiento; prueba limpia pendiente |
| G6 Regresión | 7 Python + 6 JS nuevos PASS; 180 Python previos declarados; JSON E2E/replay/soak | PASS acotado + evidencia previa | No nueva regresión completa ni Chrome E2E | Conservar artefactos y atribución |
| G7 Integridad y STOP simulado | 81/81 replay, 5400/5400 soak; 9 fallos inyectados; recursos 0 | PASS escenario esperado | `incomplete` es entrega incompleta; no STOP físico | Verificar STOP real en aceptación posterior |
| G8 Seguridad local | Ignorados verificados, convención de claves en código, listeners loopback | PASS copia actual | `.venv-wlk` no excluido de forma portable | Excluir antes de crear entorno en otra copia |
| G9 Medición Nivel A | Tres restas y medianas recalculadas | EXPLORATORIO | Sin video inspeccionado ni proyector | Ampliar muestra con protocolo audiovisual |
| G10 Inglés | Parser acepta en; ruta por sesión inspeccionada | PASS exploratorio | Idioma efectivo SimulStreaming no validado | S2-M5, sin cambios ahora |
| G11 Reinstalación desde cero | No ejecutada | PENDIENTE / no verificable en esta auditoría | Evidencia esencial si se exige reproducibilidad total | Ensayo aislado autorizado, sin tocar servicios |
| G12 Aceptación congreso | Errores médicos reportados; sin sesión prolongada/proyector | NO-GO | Riesgos de significado y estabilidad abiertos | Resolver/validar antes de uso y obtener aprobación |

M1 tiene respaldo para **GO CON RESERVAS**, condicionado a registrar y aceptar
explícitamente G11 pendiente y las demás limitaciones del alcance. No corresponde
GO sin reservas, versión estable ni autorización para iniciar el siguiente milestone.

## 14. Entrega, estado final y detención

Archivos de esta auditoría:

- **Creado:** `S2-M1-REPORT.md`, con dictamen, evidencias, riesgos y gates.
- **Modificado:** `INSTALL_WINDOWS.md`, nota de separación histórica y procedimiento S2-M1.
- **Preservados sin cambios:** los tres JSON S2-M1 y todos los benchmarks históricos,
  código, pruebas, glosarios, configuración, pins y referencias Git.

Estado final esperado y comprobado mediante `git status --short --branch`:

```text
## sprint2/m1-rtx4070
 M INSTALL_WINDOWS.md
?? S2-M1-REPORT.md
?? benchmarks/s2_m1_e2e_results.json
?? benchmarks/s2_m1_replay_results.json
?? benchmarks/s2_m1_soak_results.json
```

Sin staging, commits, tags, push, despliegues ni cambios en main. Se entrega la
recomendación al usuario para revisión y aprobación expresa. **Trabajo detenido
al terminar M1; no iniciar S2-M2 ni implementar ninguna transferencia.**
