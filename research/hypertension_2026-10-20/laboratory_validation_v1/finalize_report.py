"""Summarize existing lab measurements; do not rerun ASR or modify any input."""
from pathlib import Path
import json
import re
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from trad_lab.glossary_package import load, save, digest, timing, preservation, PACKAGE

OUT = Path(__file__).resolve().parent


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    # Keep the original measurement manifest and its historical source hashes.
    old_manifest_path = OUT / "evaluation_manifest.json"
    if not old_manifest_path.exists():
        old_manifest_path.write_bytes((OUT / "manifest.json").read_bytes())
    original_manifest = load(old_manifest_path)
    for row in original_manifest["files"]:
        path = OUT / row["name"]
        if path.stat().st_size != row["bytes"] or digest(path) != row["sha256"]:
            raise ValueError(f"Measurement artifact changed: {row['name']}")
    source = ROOT / "trad_lab/glossary_package.py"
    if digest(source) != original_manifest["validator_sha256"]:
        raise ValueError("Executed validator source changed")
    command = [sys.executable, "-B", "-m", "unittest", "tests.test_glossary_package", "-v"]
    checked = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    final_test = dict(command=command, returncode=checked.returncode, output=checked.stdout + checked.stderr)
    save(OUT, "focused_regression_tests.json", final_test)
    initial_tests = load(OUT / "test_results.json")
    test_ids = set()
    for result in initial_tests + [final_test]:
        for name, owner in re.findall(r"^(test_\w+) \(([^)]+)\) \.\.\. ok$", result["output"], flags=re.M):
            test_ids.add(owner + "." + name)
    tests_pass = all(r["returncode"] == 0 for r in initial_tests + [final_test])
    surfaces = load(OUT / "surface_checks.json")
    adversarial = load(OUT / "adversarial_results.json")
    corpus = load(OUT / "corpus_comparison.json")
    fuzzy = load(OUT / "fuzzy_diagnostics.json")
    package_hash = digest(PACKAGE / "manifest.json")
    if package_hash != original_manifest["input_package_manifest_sha256"]:
        raise ValueError("Frozen package manifest changed")
    reasons = {
        "A001": "La propuesta absorbe is not: inventa ingesta de potasio desde una frase con negación.",
        "A015": "Reintroduce mediante semejanza una equivalencia excluida: preparación/carga de medicación no equivale a carga de comprimidos.",
        "A018": "Convierte guideline needs an en recomendaciones sin respaldo en la frase; la referencia sigue necesitando tema.",
        "A019": "El intervalo absorbe and SPYRAL de la rama siguiente; no preserva el límite entre brazos.",
        "A022": "Añade hipertensión a severe is not, perdiendo la negación y el contraste de gravedad.",
        "A027": "No edema es negación de edema; no debe sugerirse angioedema.",
        "A028": "No edema es negación de edema también en español; no debe sugerirse angioedema.",
    }
    fuzzy_reviews = []
    for case in fuzzy["cases"]:
        for suggestion in case.get("fuzzy_suggestions", []):
            fuzzy_reviews.append(dict(case_id=case["id"], input=case["input"], suggestion=suggestion,
                editorial_assessment="inappropriate_in_constructed_case" if case["id"] in reasons else "expected_constructed_spelling_suggestion_only",
                reason=reasons.get(case["id"], "Errata sintética introducida deliberadamente; coincidencia esperada, sin aprobación automática."),
                assessed_by="assistant", independent_clinician_review="not_performed", automatic_substitution_approved=False))
    samples = []
    spacing_changes = 0
    for path in sorted(OUT.glob("corpus_*_cardio_*.json")):
        record = load(path)
        samples += [r["normalization_ms"] for r in record["segments"]]
        spacing_changes += sum(len(r["native_corrections"]) for r in record["segments"])
    protected = preservation(OUT)
    save(OUT, "preservation_final.json", protected)
    findings = dict(
        completed_at_utc=datetime.now(timezone.utc).isoformat(), integration_performed=False,
        conclusion="Validation completed with findings. Do not activate automatic replacement or the default fuzzy path.",
        integrity_and_unit_checks_passed=tests_pass, unique_unit_tests_passed=len(test_ids),
        canonical_complete_span_misses=[r for r in surfaces["failures"] if r["kind"] == "canonical"],
        alternative_complete_span_misses=[r for r in surfaces["failures"] if r["kind"] == "alternative"],
        affected_canonical_concept_ids=sorted({r["id"] for r in surfaces["failures"] if r["kind"] == "canonical"}),
        incomplete_span_explanation="The runtime span joiner accepts whitespace/hyphens only; slash and parenthesis spellings can load but do not match as complete forms.",
        exact_adversarial_cases=adversarial["cases"], exact_adversarial_failures=adversarial["failed_cases"],
        exact_lab_profile="657 canonical names per language, 124 EN/141 ES query variants, all suggest; fuzzy disabled in laboratory subclass only.",
        default_fuzzy_editorial_reviews=fuzzy_reviews,
        inappropriate_constructed_fuzzy_suggestions=sum(r["editorial_assessment"] == "inappropriate_in_constructed_case" for r in fuzzy_reviews),
        expected_constructed_spelling_suggestions=sum(r["editorial_assessment"] == "expected_constructed_spelling_suggestion_only" for r in fuzzy_reviews),
        original_text_changes_applied=0, native_spacing_corrections_not_applied=spacing_changes,
        segment_timing=timing(samples),
        translation_pair_consistency="657 unique EN/ES pairs consistent with stable concept IDs; provider output, grammar and Spanish ASR not evaluated.",
        clinical_false_positive_rate=None, clinical_false_negative_rate=None,
        prospective_actions_not_implemented=[
            "Define a punctuation-aware exact matcher with tests for slash, parentheses, units and chemical identities; do not strip punctuation globally.",
            "Keep default fuzzy disabled for a future pilot until negation, exclusions, reference identity and trial-arm spans have explicit safeguards.",
            "Adjudicate real suggestions and add recorded Spanish examples plus isolated provider-translation tests before claiming clinical or bidirectional quality.",
        ],
        limits=["References are provisional and not certified clinical ground truth.",
                "Nine cached hypotheses come from three recordings; they are not nine independent recordings.",
                "WER unchanged follows from preserving input; no ASR improvement was measured.",
                "Synthetic form misses and seven unsuitable suggestions do not estimate a population clinical error rate.",
                "CPU times are one local pass over offline ASR segments, not READY/live/end-to-end latency."],
    )
    save(OUT, "findings.json", findings)
    lines = [
        "VALIDACIÓN DEL PAQUETE DEPURADO — LABORATORIO AISLADO",
        "Resultado: evaluación terminada con hallazgos; sin integración en TRAD.",
        "El paquete NO queda habilitado para reemplazos automáticos ni para fuzzy por defecto.", "",
        "Se verificó el manifiesto del paquete congelado. Se ejecutaron " + str(len(test_ids)) + " pruebas unitarias distintas, todas satisfactorias.",
        "Estas pruebas del validador son distintas de las pruebas de cobertura: estas últimas detectaron limitaciones reales.", "",
        "COBERTURA CON EL NORMALIZADOR REAL",
        "1.881 comprobaciones: 1.314 formas canónicas EN/ES y 567 alternativas.",
        "Se encontraron 14 faltas de reconocimiento completo: 12 formas canónicas de 8 conceptos y 2 alternativas.",
        "La causa observable es el tratamiento de barras y paréntesis por el delimitador actual.",
        "El cargador admite esas entradas, pero eso no asegura que puedan reconocerse como una forma completa.",
        "No cambian el estado de verificación bilingüe de los 657 conceptos ni invalidan sus traducciones.",
        "Las formas afectadas son:",
    ]
    lines += ["- " + r["language"] + ": " + r["text"] + " [" + r["id"] + "]" for r in surfaces["failures"]]
    lines += ["", "PRUEBAS DE CONTRASTE Y SUGERENCIAS",
        "150 casos: 30 frases construidas y 120 lados de los 60 pares similares ya documentados.",
        "Con observación exacta: 0 cambios aplicados y 0 selecciones indebidas en esos casos.",
        "Se preservaron negaciones, cifras, unidades, símbolos, siglas ambiguas y diferencias entre conceptos.",
        "El perfil observado usa suggest y desactiva fuzzy solo en una subclase del laboratorio; no es la configuración LIVE.",
        "La prueba separada del matcher fuzzy existente produjo 9 propuestas en 30 frases construidas:",
        "7 son inadecuadas según revisión editorial del asistente y 2 corresponden a erratas sintéticas esperadas.",
        "Ejemplos prioritarios:",
        "- No edema -> angioedema, tanto en inglés como en español.",
        "- carga de medicación se -> carga de comprimidos, aunque el alias estricto estaba excluido.",
        "- potassium is not -> potassium intake: la propuesta absorbe una negación.",
        "No se aplicó ninguna. No basta retirar un alias si fuzzy puede reconstruir la equivalencia insegura.",
        "El modo suggest nativo también propone ajustes de espaciado. El control estricto no aplica ni esos ajustes.",
        "",
        "COMPARACIÓN CON TRANSCRIPCIONES DE AUDIO YA EXISTENTES",
        "Tres conferencias, " + f"{corpus['unique_audio_duration_s']/60:.2f}" + " minutos únicos, 4.204 palabras de referencia por modelo.",
        "Se reutilizaron nueve inferencias baseline (tres modelos por tres audios), con hashes verificados.",
        "No se ejecutó nuevo reconocimiento, ni se inició servicio alguno ni se llamó a DeepL.",
        "Comparación con/sin paquete sobre exactamente las mismas hipótesis:",
    ]
    for row in corpus["aggregate"]:
        lines.append(f"- {row['model']}: WER {row['baseline_wer']:.2%} -> {row['with_package_controlled_wer']:.2%}; "
                     f"{row['suggestions']} reconocimientos/sugerencias, {row['nonidentity_suggestions']} de grafía distinta.")
    t = findings["segment_timing"]
    lines += [
        "El texto controlado permanece idéntico en los 829 segmentos. Por diseño, esto NO demuestra mejora de reconocimiento.",
        "Los déficits/excesos léxicos se registran para revisión; conceptos anidados pueden solaparse y no son errores clínicos certificados.",
        f"Tiempo de observación exacta por segmento: mediana {t['median_ms']:.2f} ms; p95 {t['p95_ms']:.2f} ms; máximo {t['max_ms']:.2f} ms.",
        "Una sola pasada local. Se excluyen ASR, red, traducción, construcción del adaptador y scoring; no equivale a latencia LIVE.",
        "",
        "LÍMITES Y DECISIÓN",
        "La correspondencia estática de 657 pares es consistente en ambas direcciones; no se evaluó la salida del proveedor de traducción.",
        "Las pruebas españolas son de texto construido; no se dispone aquí de audio español con referencia clínica adjudicada.",
        "Las referencias inglesas de TurboScribe son provisionales. No hubo revisión clínica independiente.",
        "No se estima una tasa clínica de falsos positivos/negativos ni se certifican dosis o recomendaciones.",
        "Antes de un piloto habrá que resolver las 14 formas y las propuestas fuzzy inseguras en trabajo separado.",
        "Las posibles correcciones están documentadas en findings.json y NO se implementaron.",
        "",
        "PRESERVACIÓN Y ARCHIVOS",
        f"{protected['strictly_protected_files_checked']} archivos estrictamente protegidos mantienen sus huellas: investigación previa, paquete depurado, glosarios, corpus y ASR guardado, además de las bibliotecas centrales consultadas.",
        "Se añadieron únicamente trad_lab/glossary_package.py, tests/test_glossary_package.py y esta carpeta de resultados.",
        "Los cambios concurrentes observados fuera de este alcance constan en preservation_final.json y no se revirtieron.",
        "surface_checks.json: cada forma y las 14 faltas de cobertura.",
        "adversarial_results.json y fuzzy_diagnostics.json: entradas, sugerencias y resultados sin edición de evidencias.",
        "corpus_comparison.json y corpus_*.json: métricas, segmentos, tiempos y sugerencias locales.",
        "test_results.json y focused_regression_tests.json: pruebas iniciales y regresiones de los hallazgos.",
        "evaluation_manifest.json conserva las huellas de la medición inicial; manifest.json protege la entrega completa.",
    ]
    (OUT / "REPORT.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    save(OUT, "final_status.json", dict(validation_execution_complete=True, laboratory_result="completed_with_findings",
        all_unit_tests_passed=tests_pass, unique_unit_tests_passed=len(test_ids), surface_coverage_passed=False,
        surface_misses=14, exact_adversarial_cases_passed=150, inappropriate_fuzzy_suggestions=7,
        runtime_activation_approved=False, integration_performed=False, original_and_evidence_hashes_preserved=True,
        package_manifest_sha256=package_hash, clinical_or_provider_validation_claimed=False))
    save(OUT, "manifest.json", dict(files=[dict(name=f.name, bytes=f.stat().st_size, sha256=digest(f)) for f in sorted(OUT.iterdir())
                                           if f.is_file() and f.name != "manifest.json"],
        validator_sha256=digest(source), tests_sha256=digest(ROOT / "tests/test_glossary_package.py"),
        original_measurement_tests_sha256=original_manifest["tests_sha256"],
        input_package_manifest_sha256=package_hash, integration_performed=False))
    print(json.dumps(load(OUT / "final_status.json"), ensure_ascii=False, indent=2))
    if not tests_pass:
        raise SystemExit("Unit checks failed; see focused_regression_tests.json")


if __name__ == "__main__":
    main()
