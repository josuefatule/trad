# M5-C1 — copia integral de preparación, exclusivamente laboratorio

No modifica `app/` LIVE. Clona el plan M5-B2 de SHA conocido, sin runtime, secretos
o `.env`; añade hooks solo a la copia. ASR, perfil, crédito, TranscriptState,
SegmentManager, CaptionHub y renderer son los evaluados. La única inserción en
CaptionHub es un hold explícito de publicación, preservando secuencias y journal.

La configuración fija EN→ES usa `m5c-simulation`, siempre visible como
`[SIMULACIÓN ES — NO CLÍNICA]`: es texto inglés marcado, no traducción médica.
Los filtros ordinarios de provider `mock` permanecen intactos. `provider_from_config`
rechaza claves y proveedor real en C1. No reutilizar esta revisión como DeepL real.

CAPTURE físico preparado usa deviceId exacto y verifica etiqueta Yeti, handshake
inglés/crédito, worklet mono con ocho lotes pendientes, FIR en Worker y cola PCM
512 KiB incluyendo el bloque en vuelo (máximo 64000 bytes). Callback de audio no
espera ni usa red. Un desbordamiento invalida y cierra; nunca descarta y continúa.
STOP drena worklet→worker→créditos→único EOF. El diagnóstico distingue accepted,
sent, acked, DSP input/output, terminal y cola EOF ASR. Micrófono permanece bloqueado
por `/m5c/capabilities` en C1, incluso si llega `capture_start` del propietario.

FIR experimental: 127 taps, Hann, cutoff 7200 Hz, fase racional 16 kHz, soporte
futuro 63 muestras; identidad a 16 kHz. EOF usa extensión cero del soporte del
filtro y exactamente ceil(N*16000/rate) muestras, sin añadir voz o votos ASR.
No es el candidato rectangular M4-B. No cambia recorder_worker histórico.
Su elección física requiere revisar señal y discrepancias ASR del prefijo; las
pruebas de duración/espectro no demuestran mejora médica.

Pruebas reproducibles sin TCP, desde el workspace:

```powershell
.\.venv-wlk\Scripts\python.exe -m trad_lab.m5c.prepare --out logs/trad_lab/NUEVA_COPIA
& 'C:\Program Files\nodejs\node.exe' trad_lab/m5c/test_physical.cjs
& 'C:\Program Files\nodejs\node.exe' trad_lab/m5c/test_capture.cjs
.\.venv-wlk\Scripts\python.exe -m unittest trad_lab.m5c.test_contract -v
```

Desde el directorio `copy` preparado, usando Python absoluto:

```powershell
C:\live-captions\.venv-wlk\Scripts\python.exe -m trad_lab.m5c.integration control --out C:\live-captions\logs\trad_lab\NUEVO_RESULTADO
```

`control` usa palabras previamente registradas, verificando ventanas/hash antes
de devolverlas. `gpu` ejecuta realmente el decoder cacheado y no utiliza referencia
como prompt; solo con los servicios cerrados. Ninguno inicia TCP. `prefix_asr`
compara DSP únicamente en el prefijo incompleto conservado, sin WER clínico.

No arrancar C1 por TCP ni habilitar micrófono, DeepL o OBS. M5-C2 requiere
autorización nueva y una política/plan explícitos en copia nueva: habilitar solo
esos recursos aprobados, inyectar la clave local sin imprimirla, seleccionar el
proveedor DeepL original y retirar exclusivamente el modo simulación. Volver a
verificar hashes, contratos y guardas antes del primer START. No cambiar modelo,
VAD, LA2, glosario, thresholds, renderer ni SegmentManager para habilitar recursos.

Controles: STOP cierra audio; CLEAR limpia la generación visual sin borrar ASR.
OCULTAR mantiene ASR, traducciones y journal, pero no publica nuevos captions.
REANUDAR muestra solo resultados nuevos; no repite los ocultos. Ante error grave,
ocultar y pedir STOP. En caso de pérdida de conexión, ocultar también la fuente
OBS manualmente: el control de red no garantiza oscuridad instantánea del proyector.

Rollback: cerrar la revisión experimental después del drenaje, conservar logs y
usar explícitamente una revisión histórica con su cliente compatible. WLK
histórico es rollback técnico; no es respaldo clínicamente validado. LIVE no se
restaura porque no se modifica. No hay cambio automático de backend.
