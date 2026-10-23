Ensayo exploratorio de 10 términos aleatorios: leer REPORT.txt y final_results.json.

Se conservaron intactos el original, el paquete depurado y la investigación previa.
Solo esta carpeta nueva contiene simulaciones, casos, métricas y audios derivados.
No se escribió ni activó ninguna configuración de TRAD.

selection.json y protocol.json fijan el sorteo y las reglas antes de evaluar ASR.
threshold_decisions.json registra todos los puntos probados y la elección usando
únicamente calibración construida, antes de comprobar las hipótesis reales.
real_speech_checking.json conserva candidatos simulados, cambios y comparación
contra las referencias provisionales sobre los mismos audios. No hubo nuevo ASR.
correction_review.json evalúa cada cambio por separado frente a esas referencias.
El WER global y el número de formas recuperadas no certifican equivalencia clínica.

Los rangos son puntos probados de un score heurístico, no probabilidades ni
garantías para los valores intermedios. Todos permanecen sin aprobación operacional.
El perfil estudió solo estos diez canónicos, sin añadir sus alias ni los otros 647
como reglas de corrección. Los otros conceptos se usaron como negativos cercanos.
Las interacciones al incorporar el inventario completo siguen sin estar evaluadas.

checking_overlap_audit.json declara y excluye del resumen los diez ejemplos de
palabras unidas repetidos entre calibración y checking. Los resultados iniciales
se mantienen, sin retocar los umbrales después de conocer el resultado real.
Incluso el checking construido sin duplicados comparte la receta de generación;
no sustituye a una prueba independiente con nuevos hablantes y entonaciones.

audio_examples.json y summary.json pertenecen a la primera pasada, que pudo
localizar un clip con correspondencia completa de timestamps de palabras.
audio_review_examples.json y final_results.json contienen la entrega posterior:
10 clips naturales, completados mediante contenedores de segmentos ASR cuando
no se pudo justificar un límite exacto por palabra. No se manipuló la prosodia.
Los clips contextuales pueden incluir otras frases. Sus muestras PCM coinciden
exactamente con los intervalos originales, según las pruebas.

Los archivos 02/03 podrían ser partes adyacentes de la misma charla: no se
presentan como tres discursos independientes, ni los tres modelos como tres voces.
La revisión del audio humano y de las referencias sigue siendo necesaria para
interpretar discrepancias clínicas y posibles erratas de transcripción.

manifest.json protege esta entrega; preservation_final.json comprueba las fuentes.
