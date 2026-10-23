# M5-A — adaptador Turbo experimental

Solo laboratorio y archivos. No registra un backend en `app/`, no abre sockets,
micrófono o traductor. Selección explícita `turbo-experimental`; no lee `.env`.
El perfil ASR y el motor M4-C/M4-D permanecen congelados.

`adapter.py`: una instancia por sesión, PCM bytes mono s16le 16000 Hz, secuencia
contigua desde cero, frames pares de hasta 64000 bytes. Acumula frames hasta
exactamente 2 s para que el tamaño de mensaje no cambie ventanas/confirmaciones.
No remuestrea. START entrega config full/en con aislamiento; STOP admite el flush
pendiente; el único frame vacío es EOF. Un objeto cerrado no se reutiliza.
Errores de PCM/secuencia/decoder cierran como fallo, sin fallback ni terminal PASS.

Cada actualización entrega un snapshot completo: `lines` contiene únicamente
lotes de palabras confirmadas inmutables, con texto/timestamps exactos y speaker
sin atribuir; `buffer_transcription` reemplaza el provisional. No hay texto en
`buffer_diarization` ni traducciones. `ready_to_stop.unconfirmed_eof_tail` conserva
la cola sin forzar otro voto. Un último bloque de audio genuinamente nuevo sí
puede producir una inferencia final. La cola no se introduce en lines ni READY.

`consumer.py` usa los TranscriptState/SegmentManager reales, con SegmentConfig
predeterminado explícito y reloj serial simulado. Comprueba conservación de texto
en cada transición y rechazo de revisiones confirmadas. CLEAR invoca el contrato
visual del CaptionHub y no reinicia el ASR. Esto no sustituye auth/owner HTTP.

`replay.py` ofrece control con palabras ya registradas por M4-D y cuatro replays
Turbo nuevos (Yeti recibido preservado y corpus completo). Nunca pasa referencias
al decoder. Los modelos son únicamente los cacheados y verificados; Silero ON,
inglés, LA2/1 s/avance 2 s, objetivo 15 s/máximo 30 s, resto igual a M4-D.

Desde `C:/live-captions`, usando directorios nuevos y servicios cerrados:

```powershell
.\.venv-wlk\Scripts\python.exe -m unittest trad_lab.m5a.test_adapter trad_lab.m5a.test_relay -v
.\.venv-wlk\Scripts\python.exe -m trad_lab.m5a.replay control --backend turbo-experimental --out logs/trad_lab/NUEVO/control_final
.\.venv-wlk\Scripts\python.exe -m trad_lab.m5a.replay gpu --backend turbo-experimental --out logs/trad_lab/NUEVO/gpu_r1
.\.venv-wlk\Scripts\python.exe -m trad_lab.m5a.analyze --root logs/trad_lab/NUEVO
```

El análisis usa por convención `control_final/` y `gpu_r1/`; para una entrega
reproducible, nombrar el directorio de control `control_final`. Nunca reutilizar
directorios de resultados. Los tests relay sustituyen solo el transporte por
colas en memoria: ejecutan el relay real con traducción deshabilitada, sin TCP.

Límites: snapshots completos crecen con la sesión (máx. 6000 lotes/300000
caracteres); no hay servicio concurrente ni cola de admisión en esta entrega.
El relay actual transmite la cola EOF como metadata, pero su `complete` significa
cierre operativo y no que toda la voz quedó confirmada. La UI operativa no se ha
adaptado ni validado para destacar esa cola. El perfil y latencias de laboratorio
no acreditan latencia visible, exactitud médica ni uso en el congreso.

Rollback: terminar el replay y no seleccionar el adaptador. No existe cambio
operativo que revertir; conservar las evidencias. Un E2E con TCP/micrófono requiere
autorización posterior, aislamiento y revisión de la cola EOF/recursos/control.
