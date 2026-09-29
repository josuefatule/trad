# Milestones

## Milestone 1 — completado

- [x] Inspección de WLK 0.2.26 instalado, proxy PCM, operador, TranscriptState y tests.
- [x] Blue Yeti validado por el usuario con voz real.
- [x] PARTIAL investigado: buffer vacío por SimulStreaming con idioma fijo es.

## Milestone 2 — implementación completada

- [x] Revisar arquitectura, investigación de partial, fixtures y RAW existente.
- [x] SegmentManager por línea/cursor, pending, READY incremental e inmutable.
- [x] Eventos para late revisions, retiming y desaparición de contenido publicado.
- [x] Puntuación, silencio ASR, longitud, edad, estabilidad y tick configurables.
- [x] STOP/ready_to_stop hace flush; START crea manager y paneles limpios.
- [x] UI ASR CONFIRMED / SEGMENT PENDING / TRANSLATION READY.
- [x] Benchmark médico, referencia sin corregir y replay temporizado de voz real.
- [x] Tests unitarios, integración de sesiones, lógica DOM y smoke con WLK real.
- [x] Documentar métricas, thresholds y limitaciones del primer algoritmo.
- [ ] Validación final de voz del usuario para evaluar la calidad de los cortes.

No continuar a normalización, traducción, OBS ni otro milestone.
Próximas decisiones: ajustar edad/longitud, política de late revisions y precisión
temporal. El replay demuestra conservación del texto, no calidad lingüística final.
