# Baseline de latencia v0.1.0-rc1

Estado: **VALIDADO AUTOMÁTICAMENTE** en replay y Chrome aislado; voz física→proyector y duración real **PENDIENTES**. No se modificó la configuración A.

## Fuentes y relojes

Replay generado: `2026-10-17T12:05:51.542208+00:00`. E2E generado: `2026-10-17T12:12:13.523506+00:00`.

Fixture: `benchmarks\medical_full_receive.json.gz`, SHA-256 `6e4850702c084614cf62ad72a824d7f51384b16ea4c3416fadc7c764749d55b7`. 888 mensajes originales, 58.300 s, voz histórica del 2026-09-29, sesión `8ac73eec87da`. El fixture reducido de 61 eventos es la misma grabación, no otra muestra.

`benchmarks/m8_replay_results.json` conserva por segmento los tiempos de primera aparición confirmada/READY en segundos virtuales desde el primer mensaje WLK, y límites de audio de líneas fuente. Esos límites pueden solaparse: no son tiempos de palabras. La primera hipótesis parcial y el inicio físico de captura/habla son desconocidos. WLK con faster-whisper/small/es/pcm-input no entregó buffer parcial útil en esa grabación.

En el replay, normalizer.processing_ms usa perf_counter real y se reporta por separado. No se suma al reloj virtual ni a tiempos DeepL históricos. E2E, replay e historia son ejecuciones distintas.

E2E: sesión `0205397c0d27`, 17 publicaciones. Chrome real + CAPTURE/worklet PCM sintético + FastAPI real + WLK simulado que reproduce los mensajes con su timing original + normalizador real + provider de prueba (espera solicitada 20 ms) + Hub real + overlay real. El provider produce etiquetas de validación, no traducciones médicas.

`benchmarks/m8_e2e_results.json` correlaciona session_id/segment_id/sequence/generación, asr_first_seen_mono (= primera aparición CONFIRMED del contenido), ready_mono, normalized_completed_mono, queued_mono, translation_started_mono, translation_completed_mono y published_mono_ms del mismo proceso. También conserva browser_received_ms/browser_rendered_ms, observer_id y estimación calibrada con incertidumbre del protocolo de cuatro timestamps WS. No se restan relojes de procesos diferentes sin calibración. Timestamps invertidos causan fallo en el validador, en vez de producir ceros artificiales.

Doble requestAnimationFrame estima una oportunidad de paint del navegador; no mide OBS, encoder ni luz del proyector. Resolución monotónica Windows y RTT limitan la precisión: 0 ms significa no resuelto, no procesamiento instantáneo. Las restauraciones no cuentan como captions nuevos.

## Ejecución integrada M8 (ms, misma sesión)

| Etapa | n | Mediana | p90 | p95 | Máximo |
|---|---:|---:|---:|---:|---:|
| B. ASR confirmado→READY | 17 | 3750.000 | 5531.000 | 5531.000 | 5531.000 |
| C. READY→fin normalización | 17 | 31.000 | 62.000 | 63.000 | 63.000 |
| D. Fin normalización→fin provider SINTÉTICO | 17 | 16.000 | 32.000 | 32.000 | 32.000 |
| Cola traducción | 17 | 0.000 | 0.000 | 15.000 | 15.000 |
| Solo provider SINTÉTICO | 17 | 16.000 | 16.000 | 32.000 | 32.000 |
| Fin traducción→Hub | 17 | 0.000 | 0.000 | 0.000 | 0.000 |
| E. Fin traducción→paint ESTIMADO | 17 | 9.300 | 15.900 | 15.900 | 15.900 |
| ASR confirmado→Hub | 17 | 3781.000 | 5563.000 | 5593.000 | 5593.000 |

A. Captura/voz→ASR: **no medido**. DeepL real en esta ejecución: **no medido**, cero solicitudes. Nada de esta tabla representa latencia de una conferencia física.

Cola máxima observada: **1**; depth al publicar: máximo 0. Muestras paint ausentes: 0/17. Incertidumbre de entrega WS (ms): mediana 15.975, máximo 16.225. Tasa: 17.454 READY/min sobre 58.438 s desde origen del manager hasta última publicación, incluido STOP.

Evolución por orden de publicación (tercios 1–6, 7–12, 13–17):

| ASR→READY por tercio | n | Mediana | p90 | p95 | Máximo |
|---|---:|---:|---:|---:|---:|
| Inicial | 6 | 3914.000 | 5500.000 | 5500.000 | 5500.000 |
| Medio | 6 | 3664.000 | 5531.000 | 5531.000 | 5531.000 |
| Final | 5 | 3594.000 | 5531.000 | 5531.000 | 5531.000 |

Una sesión de un minuto no demuestra ausencia de deriva durante 90 minutos.

## Replay determinista A (otra ejecución)

| Medida en ms | n | Mediana | p90 | p95 | Máximo |
|---|---:|---:|---:|---:|---:|
| ASR confirmado→READY virtual | 17 | 3751.000 | 5529.000 | 5539.000 | 5539.000 |
| CPU normalizador real, reloj independiente | 17 | 29.700 | 57.862 | 65.156 | 65.156 |

17 READY, palabras min/mediana/media/máx = 1/5/4.765/8; integridad RAW **81/81**, sin pérdida/duplicación/revisiones tardías; 9 cortes forzados whitespace, 5/12 unidades anotadas fragmentadas. Flush: soft_max_age 10, hard_max_age 3, punctuation 3, session_end 1. La variante reducida da 16 READY: no mezclar cadencias para comparar versiones.

## Evidencia histórica M5.2 (no reejecutada con DeepL)

Fuente inmutable: `benchmarks/M5_2_RESULTS.json`, hash en el JSON M8. Sesiones históricas separadas; no promediar medianas ni sumarlas para fabricar E2E.

| Sesión / etapa (ms) | n | Mediana | p90 | p95 | Máximo |
|---|---:|---:|---:|---:|---:|
| 5033f1ad06d4 / asr_to_ready_ms | 5 | 4235.000 | 5579.000 | 5579.000 | 5579.000 |
| 5033f1ad06d4 / ready_to_normalized_ms | 5 | 78.000 | 94.000 | 94.000 | 94.000 |
| 5033f1ad06d4 / provider_total_ms | 5 | 610.000 | 672.000 | 672.000 | 672.000 |
| 5033f1ad06d4 / asr_to_hub_ms | 5 | 4985.000 | 6188.000 | 6188.000 | 6188.000 |
| f35acbc2d027 / asr_to_ready_ms | 10 | 4133.000 | 5532.000 | 5532.000 | 5532.000 |
| f35acbc2d027 / ready_to_normalized_ms | 10 | 39.500 | 78.000 | 78.000 | 78.000 |
| f35acbc2d027 / provider_total_ms | 10 | 578.000 | 610.000 | 641.000 | 641.000 |
| f35acbc2d027 / asr_to_hub_ms | 10 | 4750.500 | 6110.000 | 6141.000 | 6141.000 |

La historia real y el replay atribuyen la mayor espera hasta NORMALIZED a ASR→READY. Operator M7 consulta cada 2 s y añade 0–2 s de espera visual a sus paneles; eso no es tiempo de normalizador ni afecta el WebSocket de OBS. Una observación visual de 6–7 s no es una medición física de extremo a extremo ni justifica modificar A en M8.

## Reproducir / completar

Ver comandos en [INSTALL_WINDOWS.md](INSTALL_WINDOWS.md). Regenerar esta tabla con `python -m benchmarks.release_report` después de guardar ambos JSON M8. p90/p95 = nearest rank ceil(p*n), mediana convencional; con n=17 p95=máximo. Los JSON contienen los registros por segmento y permiten recalcular las distribuciones.

La prueba física y los límites de los historiales acotados están en [MANUAL_VALIDATION_V0_1.md](MANUAL_VALIDATION_V0_1.md). La grabación audiovisual de un único reloj debe completar captura/ASR y voz→proyección con FPS/incertidumbre y tercios de sesión. Los resultados de DeepL del fixture son históricos y sirven para revisión lingüística, no para medir D en este E2E ni aprobar la salida clínica.
