"""Render M8 evidence tables from saved JSON; no measurements or network calls.

python -m benchmarks.release_report
"""
import json
import hashlib

from benchmarks.release_validation import distribution
from benchmarks.segment_latency_ab import ROOT


def load(name):
    return json.loads((ROOT / "benchmarks" / name).read_text(encoding="utf-8"))


def metric_row(label, item):
    def number(value):
        return "no medido" if value is None else f"{value:.3f}"
    return "| " + " | ".join([label, str(item["n"])] +
        [number(item.get(key)) for key in ("median", "p90", "p95", "max")]) + " |"


def main():
    # Windows write_text uses CRLF by default. Keep measured JSON values intact,
    # but make their serialized checksum bytes reproducible across checkouts.
    for path in [*(ROOT / "benchmarks").glob("m8_*.json"), ROOT / "requirements-release.lock"]:
        path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n"))
    manifest_path = ROOT / "benchmarks/m8_validation_results.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["evidence_sha256"] = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                                       for name in manifest["evidence_sha256"]}
        manifest_path.write_bytes((json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    replay = load("m8_replay_results.json")
    e2e = load("m8_e2e_results.json")
    historical = load("M5_2_RESULTS.json")
    full = replay["full_receive_A"]
    rows = e2e["rows"]
    origin = rows[0]["timing"]["asr_first_seen_mono"] - e2e["requests"][0]["asr_first_seen_at"]
    end = rows[-1]["published_mono_ms"] / 1000 - origin
    text = ["# Baseline de latencia v0.1.0-rc1", "",
        "Estado: **VALIDADO AUTOMÁTICAMENTE** en replay y Chrome aislado; voz física→proyector "
        "y duración real **PENDIENTES**. No se modificó la configuración A.", "",
        "## Fuentes y relojes", "",
        f"Replay generado: `{replay['generated_utc']}`. E2E generado: `{e2e['generated_utc']}`.", "",
        f"Fixture: `{replay['fixture']}`, SHA-256 `{replay['fixture_sha256']}`. "
        "888 mensajes originales, 58.300 s, voz histórica del 2026-09-29, sesión "
        "`8ac73eec87da`. El fixture reducido de 61 eventos es la misma grabación, no otra muestra.", "",
        "`benchmarks/m8_replay_results.json` conserva por segmento los tiempos de primera "
        "aparición confirmada/READY en segundos virtuales desde el primer mensaje WLK, "
        "y límites de audio de líneas fuente. Esos límites pueden solaparse: no son tiempos de palabras. "
        "La primera hipótesis parcial y el inicio físico de captura/habla son desconocidos. "
        "WLK con faster-whisper/small/es/pcm-input no entregó buffer parcial útil en esa grabación.", "",
        "En el replay, normalizer.processing_ms usa perf_counter real y se reporta por separado. "
        "No se suma al reloj virtual ni a tiempos DeepL históricos. E2E, replay e historia son ejecuciones distintas.", "",
        f"E2E: sesión `{rows[0]['session_id']}`, {len(rows)} publicaciones. "
        "Chrome real + CAPTURE/worklet PCM sintético + FastAPI real + WLK simulado que reproduce "
        "los mensajes con su timing original + normalizador real + provider de prueba (espera solicitada 20 ms) "
        "+ Hub real + overlay real. El provider produce etiquetas de validación, no traducciones médicas.", "",
        "`benchmarks/m8_e2e_results.json` correlaciona session_id/segment_id/sequence/generación, "
        "asr_first_seen_mono (= primera aparición CONFIRMED del contenido), ready_mono, "
        "normalized_completed_mono, queued_mono, translation_started_mono, translation_completed_mono "
        "y published_mono_ms del mismo proceso. También conserva browser_received_ms/browser_rendered_ms, "
        "observer_id y estimación calibrada con incertidumbre del protocolo de cuatro timestamps WS. "
        "No se restan relojes de procesos diferentes sin calibración. Timestamps invertidos causan fallo "
        "en el validador, en vez de producir ceros artificiales.", "",
        "Doble requestAnimationFrame estima una oportunidad de paint del navegador; no mide OBS, "
        "encoder ni luz del proyector. Resolución monotónica Windows y RTT limitan la precisión: "
        "0 ms significa no resuelto, no procesamiento instantáneo. Las restauraciones no cuentan como captions nuevos.", "",
        "## Ejecución integrada M8 (ms, misma sesión)", "",
        "| Etapa | n | Mediana | p90 | p95 | Máximo |",
        "|---|---:|---:|---:|---:|---:|"]
    for key, label in (
        ("asr_to_ready_ms", "B. ASR confirmado→READY"),
        ("ready_to_normalized_ms", "C. READY→fin normalización"),
        ("normalized_to_translation_ms", "D. Fin normalización→fin provider SINTÉTICO"),
        ("translation_queue_delay_ms", "Cola traducción"),
        ("provider_total_ms", "Solo provider SINTÉTICO"),
        ("translation_to_hub_ms", "Fin traducción→Hub"),
        ("translation_to_paint_estimate_ms", "E. Fin traducción→paint ESTIMADO"),
        ("asr_to_hub_ms", "ASR confirmado→Hub")):
        text.append(metric_row(label, e2e["summary_ms"][key]))
    uncertainties = [row["observer"]["delivery_uncertainty_ms"] for row in rows if row["observer"]]
    text += ["", "A. Captura/voz→ASR: **no medido**. DeepL real en esta ejecución: **no medido**, "
        "cero solicitudes. Nada de esta tabla representa latencia de una conferencia física.", "",
        f"Cola máxima observada: **{e2e['queue_max']}**; depth al publicar: "
        f"máximo {e2e['queue_depth_at_publish']['max']}. Muestras paint ausentes: "
        f"{e2e['paint_samples_missing']}/{len(rows)}. Incertidumbre de entrega WS (ms): "
        f"mediana {distribution(uncertainties)['median']:.3f}, máximo {max(uncertainties):.3f}. "
        f"Tasa: {len(rows) * 60 / end:.3f} READY/min sobre {end:.3f} s "
        "desde origen del manager hasta última publicación, incluido STOP.", "",
        "Evolución por orden de publicación (tercios 1–6, 7–12, 13–17):", "",
        "| ASR→READY por tercio | n | Mediana | p90 | p95 | Máximo |",
        "|---|---:|---:|---:|---:|---:|"]
    for name, start, finish in (("Inicial", 0, 6), ("Medio", 6, 12), ("Final", 12, len(rows))):
        text.append(metric_row(name, distribution([r["asr_to_ready_ms"] for r in rows[start:finish]])))
    text += ["", "Una sesión de un minuto no demuestra ausencia de deriva durante 90 minutos.", "",
        "## Replay determinista A (otra ejecución)", "",
        "| Medida en ms | n | Mediana | p90 | p95 | Máximo |",
        "|---|---:|---:|---:|---:|---:|",
        metric_row("ASR confirmado→READY virtual", full["latency_ms"]),
        metric_row("CPU normalizador real, reloj independiente", full["normalizer_processing_ms_separate_clock"]), "",
        "17 READY, palabras min/mediana/media/máx = 1/5/4.765/8; integridad RAW **81/81**, "
        "sin pérdida/duplicación/revisiones tardías; 9 cortes forzados whitespace, 5/12 unidades "
        "anotadas fragmentadas. Flush: soft_max_age 10, hard_max_age 3, punctuation 3, session_end 1. "
        "La variante reducida da 16 READY: no mezclar cadencias para comparar versiones.", "",
        "## Evidencia histórica M5.2 (no reejecutada con DeepL)", "",
        "Fuente inmutable: `benchmarks/M5_2_RESULTS.json`, hash en el JSON M8. "
        "Sesiones históricas separadas; no promediar medianas ni sumarlas para fabricar E2E.", "",
        "| Sesión / etapa (ms) | n | Mediana | p90 | p95 | Máximo |",
        "|---|---:|---:|---:|---:|---:|"]
    for session in historical["live_evidence"]:
        for key in ("asr_to_ready_ms", "ready_to_normalized_ms", "provider_total_ms", "asr_to_hub_ms"):
            text.append(metric_row(session["session_id"] + " / " + key,
                distribution([row.get(key) for row in session["samples"]])))
    text += ["", "La historia real y el replay atribuyen la mayor espera hasta NORMALIZED a ASR→READY. "
        "Operator M7 consulta cada 2 s y añade 0–2 s de espera visual a sus paneles; eso no es tiempo "
        "de normalizador ni afecta el WebSocket de OBS. Una observación visual de 6–7 s no es una "
        "medición física de extremo a extremo ni justifica modificar A en M8.", "",
        "## Reproducir / completar", "",
        "Ver comandos en [INSTALL_WINDOWS.md](INSTALL_WINDOWS.md). Regenerar esta tabla con "
        "`python -m benchmarks.release_report` después de guardar ambos JSON M8. "
        "p90/p95 = nearest rank ceil(p*n), mediana convencional; con n=17 p95=máximo. "
        "Los JSON contienen los registros por segmento y permiten recalcular las distribuciones.", "",
        "La prueba física y los límites de los historiales acotados están en "
        "[MANUAL_VALIDATION_V0_1.md](MANUAL_VALIDATION_V0_1.md). La grabación audiovisual de un único "
        "reloj debe completar captura/ASR y voz→proyección con FPS/incertidumbre y tercios de sesión. "
        "Los resultados de DeepL del fixture son históricos y sirven para revisión lingüística, "
        "no para medir D en este E2E ni aprobar la salida clínica.", ""]
    (ROOT / "LATENCY_BASELINE_V0_1.md").write_text("\n".join(text), encoding="utf-8")
    text = ["# M8 — READY, NORMALIZED y ENGLISH histórico del fixture médico", "",
        "Replay A nuevo; ENGLISH histórico M5.2 reutilizado solo con RAW, normalizado, "
        "configuración, hash de fixture/glosarios y contexto previo idénticos. "
        "No se llamó DeepL. No es validación clínica ni texto de referencia humana.", "",
        "| # | ASR confirmado / READY (s replay) | Motivo / corte | RAW ES | NORMALIZED ES | ENGLISH HISTÓRICO |",
        "|---|---|---|---|---|---|"]
    for index, segment in enumerate(full["segments"], 1):
        translation = segment["historical_translation"]
        values = [str(index), f"{segment['first_seen_at']:.3f} / {segment['emitted_at']:.3f}",
                  segment["reason"] + " / " + segment["boundary_kind"], segment["text"],
                  segment["normalization"]["normalized_text"], translation["text"] if translation else "NO MATCH"]
        text.append("| " + " | ".join(value.replace("|", "\\|") for value in values) + " |")
    (ROOT / "benchmarks/M8_MEDICAL_SEGMENTS.md").write_text("\n".join(text) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
