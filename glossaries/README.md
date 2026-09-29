# Formato de glosarios

La aplicación carga primero `medical_base.json` y después `conference.json` al
abrir cada sesión. Ambos usan UTF-8 y este formato:

```json
{
  "name": "conference",
  "version": 1,
  "terms": [{
    "canonical": "ecocardiografía transtorácica",
    "variants": ["ecocardiografia transtoracica"],
    "aliases": ["eco transtorácico"],
    "auto_apply": "fuzzy",
    "auto_threshold": 0.97,
    "suggest_threshold": 0.88
  }]
}
```

- `canonical` es obligatorio.
- `variants` y `aliases` son listas opcionales de formas conocidas y exactas.
- `auto_apply` puede ser `exact`, `fuzzy` o `suggest`. `exact` nunca autoaplica
  similitud; `fuzzy` puede hacerlo sobre expresiones de varias palabras; `suggest`
  nunca modifica texto automáticamente.
- Los umbrales son opcionales por término. Deben cumplir
  `0 <= suggest_threshold < auto_threshold <= 1`.

El matching ignora mayúsculas y diacríticos para reconocer una forma, admite guion
o espacio entre palabras y conserva la puntuación exterior. Una forma exacta no
puede pertenecer a dos canónicos. Reiniciar FastAPI después de editar un glosario.

Mantener la base limitada a correcciones ampliamente seguras. Usar el glosario de
conferencia para nombres y vocabulario confirmado del evento. Antes de promover una
entrada fuzzy, probar ejemplos positivos y negativos; una sugerencia es preferible
cuando la ambigüedad sea material.
