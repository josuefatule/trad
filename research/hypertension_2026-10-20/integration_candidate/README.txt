PAQUETE DEPURADO DE INVESTIGACIÓN — 657 CONCEPTOS EN↔ES
Versión: 1.0.0-research. No integrado en TRAD.

ALCANCE
Se consolida la investigación ya realizada, sin nuevas búsquedas ni cambios
en sus evidencias. Este paquete no constituye un glosario operacional aprobado.
Ninguna forma está aprobada para sustitución automática. No se importaron las
políticas exact/fuzzy del original ni el candidato histórico de 640 entradas.
Los JSON derivados usan entradas y decisiones de investigación; deliberadamente
no incluyen la lista raíz "terms" que exige el cargador actual de TRAD.

QUÉ LEER
1. validation.json: comprobaciones estructurales y preservación de archivos.
2. concepts.json: 657 identificadores y pares canónicos idénticos al registro
   bilingüe; evidencia, contexto, restricciones y metadatos depurados de siglas.
3. form_decisions.json: 567 formas únicas, que cubren 900 ocurrencias originales;
   historial anterior y decisión efectiva tras revisar las 124 formas posteriores.
4. normalization_en.json y normalization_es.json: vistas por idioma para diseñar
   una evaluación posterior. "review_alternative_ids" permite consultar variantes
   dentro del concepto; NO significa alias estricto ni permiso de reemplazo.
   Las siglas, unidades, flexiones, equivalencias contextuales, exclusiones y
   formas sin evidencia aceptada permanecen fuera de esa selección. Las colisiones
   detectadas también se retienen fuera de ella, sin resolver por orden de archivo.
5. translation_en_es.json: 657 pares para evaluación contextual. No es un mapa
   global de reemplazo, ni un archivo de carga del proveedor. Su inversión para
   ES→EN tampoco está aprobada. Se conservan los métodos y limitaciones del cotejo.
6. restrictions.json y collisions.json: distinciones clínicas, identidad de guías
   y estudios, evidencia definitoria, homónimos y solapamientos con los glosarios
   existentes. Un solapamiento puede pertenecer al mismo concepto; no se cuenta
   como error. Un destino existente no reconciliado tampoco prueba una colisión
   semántica: se registra y no se decide por precedencia.
7. changes_applied.json: ajustes aplicados SOLO a las copias derivadas, incluidas
   6 expansiones propuestas y 22 correcciones de otros significados. Las propuestas
   gramaticales de expansión siguen siendo condicionales; no autorizan expansión.
8. sources.json y provenance.json: catálogo S/AS/SF, entradas, huellas y precedencia.
   Las rutas de caché y los enlaces a archivos de evidencia se resuelven desde
   la carpeta de investigación padre. Los números de bloque no son páginas PDF.
9. protected_files.json y manifest.json: huellas previas de archivos protegidos
   y huellas del paquete nuevo. El manifiesto no se incluye a sí mismo.

DECISIONES DE DEPURACIÓN
Se preservan las 11 exclusiones estrictas anteriores y se retira además la forma
ambigua "hipertensión farmacológica". Las otras 12 de las 13 formas sin atestación
aceptada permanecen retenidas por evidencia. Ninguno de esos casos elimina el
concepto canónico correspondiente. Los 106 hallazgos literales aceptados conservan
las restricciones de la auditoría previa. "Prueba de captopril" exige finalidad
diagnóstica y protocolo; una guía identificada solo por año y sociedades necesita
el tema. PAD, ECA y MRA no se expanden sin una definición local explícita.
Las etiquetas canónicas genéricas de referencias se conservan por trazabilidad,
con restricción de contexto, sin inventarles una identidad más específica.
La identificación de un concepto existente mediante una variante revisada solo
sirve para esta comparación de investigación; no aprueba sinonimia estricta.
Los otros destinos antiguos sin correspondencia explícita quedan identificados
como pendientes de reconciliación para una eventual integración, sin eliminar
conceptos ni asumir equivalencia a partir de sus alias o palabras parecidas.

REPRODUCCIÓN Y LÍMITES
build_package.py escribe exclusivamente aquí y rechaza entradas que difieran de
las huellas protegidas. Reproduce datos a partir de la evidencia local existente.
test_package.py comprueba el paquete y casos negativos de precedencia/colisiones.
Las comprobaciones ejecutadas son de preparación de datos. No se ejecutó el
normalizador de TRAD, no se evaluaron audios, no se llamó al traductor y no se
certificó seguridad clínica. La normalización de tokens se utiliza únicamente
para detectar posibles colisiones; no altera grafías, valores, unidades ni textos.
La ausencia de una atestación aceptada no prueba que una expresión nunca se use.

ARCHIVOS CONSERVADOS
El original medical_base_en.json, los demás glosarios, el candidato histórico,
los registros de investigación, sus evidencias, manifiesto y ZIP previos conservan
sus bytes según validation.json. Solo se escribieron archivos en esta carpeta.
La comparación con la instantánea amplia detectó cambios concurrentes bajo
trad_lab/m5c2r/, fuera del límite de escritura del constructor. Se registran
los archivos y huellas observados, sin atribuir autoría ni revertirlos. Por eso no se
afirma que todos los archivos del proyecto sean idénticos a la instantánea.
No se modificó configuración ni se conectó este paquete con ninguna parte de TRAD.
Este trabajo completa únicamente la preparación del paquete de investigación.
