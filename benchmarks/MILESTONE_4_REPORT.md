# Milestone 4 — Translation Engine

Replay ejecutado el 2026-09-30 sobre `medical_real_snapshots.json`, con el pipeline
de producción, `TRANSLATION_CONTEXT_SEGMENTS=2` y `MockTranslatorProvider`. El mock
es determinístico, devuelve solo el segmento actual y marca cada resultado como
`[MOCK EN]`; estas salidas no evalúan calidad lingüística.

```text
SUMMARY segments=16 late_revisions=0 integrity=PASS source_words=81 emitted_words=81
TRANSLATION_SUMMARY segments=16 successes=16 failures=0 retries=0 timeouts=0 max_queue_depth=16
TRANSLATION_LATENCY_MS median=0.000 p95=0.000 max=0.000
TRANSLATION_QUEUE_DELAY_MS median=230.812 p95=517.343
```

El replay procesa en CPU los 58,3 segundos del fixture sin esperarlos en tiempo real.
Por eso los 16 segmentos pueden entrar en la cola durante el análisis acelerado y el
`max_queue_depth=16`; esa profundidad y sus demoras no predicen una sesión en vivo.
La latencia cero redondeada es la del mock sin demora artificial. Las pruebas del
engine cubren por separado latencia controlada, cola acotada, timeout y retries.

`medical_reference_en.txt` contiene la referencia inglesa humana. El replay y los
providers no leen ese archivo; se reserva para evaluación posterior y ninguna prueba
exige igualdad literal.

No se encontraron variables de traducción, credenciales ni `.env` en el proyecto al
iniciar M4. La aplicación queda deshabilitada por defecto. Para una prueba real se
propone DeepL, cuyo endpoint admite el contexto como parámetro separado que no se
traduce. Se requieren `TRANSLATION_ENABLED=1`, `TRANSLATION_PROVIDER=deepl` y
`DEEPL_AUTH_KEY`; `DEEPL_API_URL` permite elegir el endpoint Free o Pro.

Los tiempos propagados permiten medir READY, normalización, queue delay y traducción.
Todavía no existe un único reloj absoluto que una captura de audio, primera aparición
ASR y respuesta del provider, de modo que M4 no publica una cifra exacta de speech
onset → English.
