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

No iniciar Milestone 4 ni traducción.
