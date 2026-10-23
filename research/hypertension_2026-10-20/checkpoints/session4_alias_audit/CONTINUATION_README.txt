AUDITORÍA POSTERIOR DE ALIAS COMPLETADA, SOLO INVESTIGACIÓN.
Leer primero alias_audit_report.md y alias_corrections_proposed.json.
657 conceptos / 900 ocurrencias / 567 formas únicas revisadas.
3 colisiones internas; 16 advertencias externas; 11 exclusiones estrictas;
47 condiciones; 6 expansiones; 22 metadatos; 60 pares similares separados.
124 formas sin coincidencia literal individual siguen explícitas.
Original, candidato, dataset canónico y registro bilingüe intactos.
No integración. Usar finalize_alias_audit.py para validar esta capa;
finalize_657.py se conserva como finalizador histórico protegido.
Los párrafos siguientes describen el cierre canónico anterior.

Inventario EN↔ES de hipertensión: 657 pares canónicos cotejados, 0 pendientes.
Última sesión: comenzó el 20 de octubre de 2026 y cerró el 21, hora de Bolivia.

Se añadieron 57 verificaciones conservando los 600 registros previos.
Dos preferencias españolas se ajustaron solo en el dataset de investigación:
arterial compliance -> compliancia arterial;
asymptomatic markedly elevated blood pressure -> presión arterial marcadamente elevada asintomática.
El historial está en session3_terminology_corrections.json.

El glosario original y el candidato operacional permanecen byte por byte intactos.
No se modificó producción, no se integró nada en TRAD y no hubo commits.
El cotejo por el asistente no constituye certificación clínica independiente,
aprobación de sustituciones automáticas ni verificación de dosis o indicaciones.

Leer hypertension_research_report.md y hypertension_research_progress.json.
bilingual_verification.json: 1.314 atestaciones de los 657 pares.
bilingual_decisions.json: decisiones acumuladas e historial de pendientes resueltos.
session3_verification.json y session3_review_decisions.json: los 57 de esta sesión.
source_access_index.json: disponibilidad, localizadores y huellas de fuentes.
DATASET_SCHEMA.md: alcance de campos y métodos.
manifest.json: tamaño y SHA-256 de los archivos del ZIP.

Los estados previos están en checkpoints/session1_52_verified/ y
checkpoints/session2_600_verified/. Las fuentes completas y el corpus local
source_cache/ se excluyen del ZIP; repetir la comprobación textual requiere
conservarlos o recuperar las fuentes públicas identificadas. Un extracto indexado
no demuestra lectura del artículo completo.

Los índices PDF cuentan páginas del archivo desde 1, no necesariamente las
impresas. Los índices no PDF remiten a bloques locales desde 1. Las listas de
palabras clave bilingües se distinguen del cuerpo del texto y pueden contener
atestaciones explícitas de ambos idiomas.

finalize_657.py validaba y empaquetaba el estado canónico anterior. Nunca escribe el glosario
original ni el candidato. Reejecutarlo actualiza el cierre de sesión: no usarlo
para simular tiempo de investigación. El registro suma intervalos de tres sesiones
y excluye ambas pausas; no mide horas efectivas de trabajo por separado.

Los constructores/finalizadores de 52 y 600 pares son históricos y tienen una
protección contra el retroceso de la verificación posterior. No usarlos para
continuar. discover_session3.py y verify_bilingual.py localizan coincidencias,
no las aprueban. record_session3_review.py representa decisiones explícitas sobre
una huella fija; un corpus o inventario distinto exige otra revisión.
No habilitar estos datos en TRAD sin una solicitud distinta.
