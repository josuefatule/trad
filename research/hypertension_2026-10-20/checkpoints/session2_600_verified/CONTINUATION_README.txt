Continuación de investigación EN↔ES de hipertensión, 20 de octubre de 2026

Resultado: 600 pares canónicos cotejados, 57 pendientes, 548 verificaciones nuevas.
El glosario original y el candidato operacional no se modificaron en esta continuación.
No hay integración, aprobación de sustituciones automáticas ni revisión clínica independiente.

Leer primero hypertension_research_report.md y hypertension_research_progress.json.
bilingual_verification.json conserva las dos atestaciones de cada par aceptado.
bilingual_decisions.json conserva las decisiones del asistente para los 657 registros.
source_access_index.json distingue acceso completo, extractos, metadatos y bloqueos.
Las copias locales de las publicaciones están en source_cache/ y se excluyen del ZIP.
El ZIP contiene los datos, metadatos de trazabilidad y herramientas de comprobación;
no es un paquete autónomo con los textos completos de las publicaciones.

Los bloques no PDF remiten al corpus de extracción local, numerados desde 1.
Los índices pdf_page remiten a páginas PDF, también desde 1, no a páginas impresas.
Las formas atestadas se distinguen de las formulaciones preferidas del inventario.

El estado anterior de 52 pares está conservado en checkpoints/session1_52_verified/.
build_research.py y finalize_research.py son históricos y tienen una protección
contra la pérdida de la verificación posterior. No usarlos para continuar.
report_template.md es también una plantilla histórica de ese primer lote.

finalize_continuation.py valida y empaqueta únicamente la investigación actual,
leyendo el corpus local y el registro editorial ya revisado. Nunca escribe el
glosario original ni el candidato. Reejecutarlo actualiza la fecha de cierre;
no debe usarse para simular tiempo de investigación.
verify_bilingual.py solo descubre coincidencias; no las aprueba.
record_bilingual_review.py materializa decisiones editoriales sobre una huella fija
de descubrimiento. Un corpus o inventario diferente exige una nueva revisión.

La verificación de fuentes no autoriza incorporar traducciones o alias en TRAD.
