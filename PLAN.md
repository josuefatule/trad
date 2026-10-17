# Milestones

## Milestone 1 — completado

- [x] Inspección de WLK 0.2.26 instalado, proxy PCM, operador, TranscriptState y tests.
- [x] Blue Yeti validado por el usuario con voz real.
- [x] PARTIAL investigado: buffer vacío por SimulStreaming con idioma fijo es.

## Milestone 2 — completado

- [x] Revisar arquitectura, investigación de partial, fixtures y RAW existente.
- [x] SegmentManager por línea/cursor, pending, READY incremental e inmutable.
- [x] Eventos para late revisions, retiming y desaparición de contenido publicado.
- [x] Puntuación, silencio ASR, longitud, edad, estabilidad y tick configurables.
- [x] STOP/ready_to_stop hace flush; START crea manager y paneles limpios.
- [x] UI ASR CONFIRMED / SEGMENT PENDING / TRANSLATION READY.
- [x] Benchmark médico, referencia sin corregir y replay temporizado de voz real.
- [x] Tests unitarios, integración de sesiones, lógica DOM y smoke con WLK real.
- [x] Documentar métricas, thresholds y limitaciones del primer algoritmo.
- [x] Afinación final por replay: 16 READY, mediana 3,83 s e integridad 81/81.

## Milestone 3 — implementación completada

- [x] `TerminologyNormalizer` independiente entre READY y la futura traducción.
- [x] `raw_text` inmutable y `normalized_text` separado con auditoría completa.
- [x] Glosario médico base y glosario de conferencia configurables.
- [x] Exactos seguros, fuzzy conservador de expresiones y sugerencias por umbral.
- [x] Resolución determinista de solapamientos, mayúsculas, acentos, guiones y signos.
- [x] Contexto reciente entre segmentos solo como `cross_segment_suggestion`.
- [x] UI RAW / NORMALIZED / CORRECTIONS-SUGGESTIONS.
- [x] Replay médico con salida comparada, términos conocidos y perfil de rendimiento.
- [x] Pruebas positivas, negativas, integración proxy y fixture real.
- [ ] Validación final con voz Blue Yeti del flujo NORMALIZED ES.

No avanzar todavía a traducción, LLM, OBS ni corrección retroactiva de READY.
El siguiente paso operativo es validar con voz real y revisar sugerencias antes de
ampliar el glosario de conferencia.

## Milestone 3.1 — validación y afinación completada

- [x] Explicar `systólica` sin corregir: proceso FastAPI antiguo y fallback RAW de UI.
- [x] Handshake de capability y error visible ante backend sin normalización.
- [x] Matching conservador de spans ASR partidos contra canónicos técnicos unidos.
- [x] Glosario médico ampliado con terminología general reutilizable.
- [x] Whitespace y spacing de puntuación determinísticos y auditables.
- [x] Replay del texto real, tests positivos/negativos y límites documentados.
- [ ] Repetir una sesión Blue Yeti después de reiniciar FastAPI.

## Milestone 4 — implementación estructural completada

- [x] `TranslationRequest`/`TranslationResult` inmutables y provider-agnostic.
- [x] `TranslatorProvider`, mock determinístico y adaptador DeepL configurable.
- [x] Contexto NORMALIZED de 0–2+ segmentos sin reemitirlo.
- [x] Cola secuencial acotada, orden estricto y métricas de depth/delay.
- [x] Timeouts, retries limitados y continuidad después de fallos.
- [x] Reset por sesión y descarte explícito de resultados stale.
- [x] Handshake `translation_engine=1`, estado y provider visibles.
- [x] Operator con RAW ES, NORMALIZED ES y ENGLISH simultáneos.
- [x] Replay con contexto, traducción y resumen de latencias.
- [x] Referencia inglesa humana separada y fuera del provider.
- [x] Tests unitarios y de integración sin red ni credenciales.
- [ ] Validación con voz real y un provider real configurado.

## Milestone 4.1 — completado

- [x] Carga automática de `.env`, valores entre comillas y alias `DEEPL_API_KEY`.
- [x] Clave excluida de Git y del repr de configuración.
- [x] DeepL probado con una traducción breve real.

## Milestone 5 — implementación completada

- [x] Hub de sesión con único publisher y múltiples observadores acotados.
- [x] Overlay transparente /overlay y WebSocket /ws/overlay de solo lectura.
- [x] Snapshot atómico vigente, orden, deduplicación y aislamiento de sesiones.
- [x] Cola visual independiente, paginación por tipografía y timers finitos.
- [x] Políticas de saturación y descartes explícitos con diagnósticos en Operator.
- [x] Demo aislada sin micrófono, WLK ni DeepL en /overlay/preview.
- [x] Bloqueo explícito de traducciones mock en producción.
- [x] Configuración y parámetros URL validados, documentación OBS.
- [x] Tests Python, DOM/tiempos JavaScript, integración simulada y replay.
- [ ] Inspección visual final en OBS y lectura real con audio + DeepL.

No avanzar a Milestone 6. No se instala ni controla OBS desde la aplicación.
