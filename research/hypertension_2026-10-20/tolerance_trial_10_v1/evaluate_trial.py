"""Frozen random ten-term threshold trial; CPU, local, no TRAD integration."""
from collections import Counter, defaultdict
from dataclasses import asdict
from difflib import SequenceMatcher
from pathlib import Path
import hashlib
import json
import re
import statistics
import sys
import time
import unicodedata
import wave

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from app.captions.terminology_normalizer import TerminologyNormalizer, NormalizerConfig, _tokens
from trad_lab.metrics import metrics, tokens, measurement_signatures, NEGATIONS, NUMBER_WORDS

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent / "integration_candidate"
CACHED = ROOT / "logs/trad_lab/20261020T074247Z/evaluation"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda: f.read(1024*1024), b""):
            h.update(b)
    return h.hexdigest()


def save(name, value):
    if Path(name).name != name:
        raise ValueError("Output stays in this trial directory")
    (HERE/name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")


def candidate(text, selected, thresholds):
    doc = {"terms": []}
    for item in selected:
        threshold = thresholds[item["concept_id"]]
        term = {"canonical": item["canonical_en"], "auto_apply": "exact" if threshold is None else "fuzzy"}
        if threshold is not None:
            term.update(auto_threshold=threshold, suggest_threshold=min(.86, threshold-.01))
        doc["terms"].append(term)
    normalizer = TerminologyNormalizer.from_documents([doc], NormalizerConfig())
    started = time.perf_counter_ns()
    result = normalizer.normalize("isolated-lab", text)
    changes = [asdict(c) for c in result.corrections if c.rule != "deterministic_spacing"]
    output = text
    for c in sorted(changes, key=lambda c: (c["start"], c["end"]), reverse=True):
        output = output[:c["start"]] + c["replacement"] + output[c["end"]:]
    return dict(text=output, changes=changes, wall_ms=(time.perf_counter_ns()-started)/1_000_000,
                controlled_text=text, policy="Simulated candidate artifact only; never passed to LIVE")


def make_cases(selected, concepts):
    result = []
    for item in selected:
        canonical = item["canonical_en"]; cid = item["concept_id"]
        matches = list(re.finditer(r"[A-Za-z]{5,}", canonical))
        longest = max(matches, key=lambda m: len(m.group()))
        start, end = longest.span(); word = longest.group()
        for split, fraction in [("calibration", .35), ("synthetic_checking", .65)]:
            k = max(1, min(len(word)-2, int(len(word)*fraction)))
            variants = [
                ("deletion", word[:k]+word[k+1:]),
                ("transposition", word[:k]+word[k+1]+word[k]+word[k+2:]),
                ("insertion", word[:k]+"x"+word[k:]),
                ("substitution", word[:k]+("z" if word[k].lower() != "z" else "x")+word[k+1:]),
                ("split_word", word[:k]+" "+word[k:]),
            ]
            for kind, variant in variants:
                text = canonical[:start]+variant+canonical[end:]
                if tokens(text) != tokens(canonical):
                    result.append(dict(concept_id=cid, split=split, kind=kind, positive=True, text=text,
                                       intended=canonical, origin="constructed_spelling_not_acoustic_or_prosodic"))
            gap = next(iter(re.finditer(r"[ -]+", canonical)), None)
            if gap:
                text = canonical[:gap.start()]+canonical[gap.end():]
                result.append(dict(concept_id=cid, split=split, kind="merged_words", positive=True, text=text,
                                   intended=canonical, origin="constructed_spelling_not_acoustic_or_prosodic"))
        names = [c["canonical_en"] for c in concepts if c["id"] != cid and
                 tokens(c["canonical_en"]) not in [tokens(f) for f in item["reference_forms"]]]
        nearby = sorted(set(names), key=lambda name: (-SequenceMatcher(None, canonical.casefold(), name.casefold()).ratio(), name))[:24]
        for i, name in enumerate(nearby):
            result.append(dict(concept_id=cid, split="calibration" if i % 2 == 0 else "synthetic_checking",
                               kind="distinct_glossary_concept", positive=False, text=name,
                               origin="separate_canonical_record_not_a_substitution_license"))
        qualifiers = {"systolic": "diastolic", "primary": "secondary", "sodium": "potassium", "ten": "five",
                      "American": "European", "receptor": "receptors", "events": "event", "inhibitors": "inhibitor"}
        for key, value in qualifiers.items():
            text, count = re.subn(r"\b"+key+r"\b", value, canonical)
            if count:
                for split in ("calibration", "synthetic_checking"):
                    result.append(dict(concept_id=cid, split=split, kind="preserve_qualifier_or_number", positive=False,
                                       text=text if split == "calibration" else "They discussed "+text+" today.",
                                       origin="constructed_contrast_do_not_rewrite_qualifier_or_inflection"))
        first_gap = re.search(r"[ -]+", canonical)
        if first_gap:
            text = canonical[:first_gap.end()]+"is not "+canonical[first_gap.end():]
            result.append(dict(concept_id=cid, split="calibration", kind="negation_intrusion", positive=False, text=text,
                               origin="constructed_no_absorption_of_negation"))
            text = canonical[:first_gap.end()]+"was never "+canonical[first_gap.end():]
            result.append(dict(concept_id=cid, split="synthetic_checking", kind="negation_intrusion", positive=False, text=text,
                               origin="constructed_no_absorption_of_negation"))
    for i, row in enumerate(result, 1):
        row["case_id"] = f"T{i:04d}"
    return result


def run_case(case, item, threshold):
    result = candidate(case["text"], [item], {item["concept_id"]: threshold})
    triggered = any(c["rule"] == "glossary_fuzzy" for c in result["changes"])
    recovered = tokens(result["text"]) == tokens(case.get("intended", "")) if case["positive"] else False
    return dict(case_id=case["case_id"], threshold=threshold, triggered=triggered,
                recovered=recovered, output=result["text"], changes=result["changes"])


def score_cases(rows, cases):
    index = {c["case_id"]: c for c in cases}
    positive = [r for r in rows if index[r["case_id"]]["positive"]]
    negative = [r for r in rows if not index[r["case_id"]]["positive"]]
    return dict(positive_cases=len(positive), recovered=sum(r["recovered"] for r in positive),
                negative_cases=len(negative), negative_triggers=sum(r["triggered"] for r in negative),
                missed_positive_case_ids=[r["case_id"] for r in positive if not r["recovered"]],
                negative_trigger_case_ids=[r["case_id"] for r in negative if r["triggered"]])


def calibrate(selected, cases, grid):
    decisions = []
    all_results = []
    for item in selected:
        cid = item["concept_id"]
        calibration = [c for c in cases if c["concept_id"] == cid and c["split"] == "calibration"]
        grid_scores = []
        for threshold in grid:
            rows = [run_case(case, item, threshold) for case in calibration]
            all_results += rows
            grid_scores.append(dict(threshold=threshold, **score_cases(rows, calibration)))
        eligible = [r for r in grid_scores if r["negative_triggers"] == 0]
        best = max(eligible, key=lambda r:(r["recovered"], r["threshold"])) if eligible else None
        decisions.append(dict(concept_id=cid, canonical_en=item["canonical_en"],
                              selected_auto_threshold=best["threshold"] if best else None,
                              safe_tested_grid_points=[r["threshold"] for r in eligible],
                              calibration_grid=grid_scores,
                              choice_rule="Maximum positive recovery with zero constructed negative triggers, then higher threshold; no ASR checking used.",
                              baseline_auto_threshold=.90, threshold_is_not_calibrated_probability=True,
                              operational_approval=False))
    return decisions, all_results


def ref_map(reference_words, hypothesis_words, edits):
    result = {}; i = j = 0
    for e in edits:
        while i < e["ref_index"] and j < e["hyp_index"]:
            result[i] = j; i += 1; j += 1
        if i != e["ref_index"] or j != e["hyp_index"]:
            raise ValueError("Alignment trace inconsistent")
        if e["op"] == "S":
            result[i] = j; i += 1; j += 1
        elif e["op"] == "D":
            result[i] = None; i += 1
        else:
            j += 1
    while i < len(reference_words) and j < len(hypothesis_words):
        result[i] = j; i += 1; j += 1
    if i != len(reference_words) or j != len(hypothesis_words):
        raise ValueError("Unconsumed alignment trace")
    return result


def extracted_span(left, right, mapped, hyp, edits):
    indices = [mapped[i] for i in range(left, right) if mapped[i] is not None]
    indices += [e["hyp_index"] for e in edits if e["op"] == "I" and left <= e["ref_index"] < right]
    if not indices:
        return [], []
    low, high = min(indices), max(indices)+1
    return hyp[low:high], list(range(low, high))


def occurrences(selected, sources):
    rows = []
    for item in selected:
        for source in sources:
            ref = tokens(source["reference_raw"]); spans = {}
            for form in item["reference_forms"]:
                target = tokens(form)
                for i in range(len(ref)-len(target)+1):
                    if ref[i:i+len(target)] == target:
                        spans[(i, i+len(target))] = form
            for (left, right), form in sorted(spans.items()):
                rows.append(dict(concept_id=item["concept_id"], canonical_en=item["canonical_en"], sample_id=source["id"],
                                 ref_left=left, ref_right=right, reference_form=form, reference_tokens=ref[left:right],
                                 reference_context=" ".join(ref[max(0,left-8):right+8])))
    return rows


def cue_signature(text):
    values = tokens(text)
    return dict(negations=[w for w in values if w in NEGATIONS],
                number_words=[w for w in values if w in NUMBER_WORDS],
                measurements=[r["value"] for r in measurement_signatures(text)])


def check_corpus(selected, decisions, sources, positions):
    tuned = {r["concept_id"]: r["selected_auto_threshold"] for r in decisions}
    profiles = {"raw": None, "uniform_090": {r["concept_id"]:.90 for r in selected}, "individualized": tuned}
    rows = []; per_occurrence = []; changes = []; full_outputs = []
    for model in ("small", "medium", "large-v3-turbo"):
        for source in sources:
            path = CACHED/"models"/model/source["id"]/"result.json"
            data = load(path); raw = data["hypothesis_raw"]; reference = data["reference_raw"]
            if sha(source["audio_path"]) != source["audio_sha256"] or sha(source["reference_path"]) != source["reference_sha256"]:
                raise ValueError("Corpus source changed")
            if data["reference_raw"] != source["reference_raw"] or data["variant"] != "baseline":
                raise ValueError("Only comparable existing baseline inferences")
            if raw != (path.parent/"hypothesis.raw.txt").read_text(encoding="utf-8-sig"):
                raise ValueError("Cached hypothesis changed")
            ref_words = tokens(reference)
            for profile, thresholds in profiles.items():
                applied = dict(text=raw, changes=[], wall_ms=0) if thresholds is None else candidate(raw, selected, thresholds)
                measured = data["metrics"] if applied["text"] == raw else metrics(reference, applied["text"])
                hyp_words = tokens(applied["text"])
                mapped = ref_map(ref_words, hyp_words, measured["word_edits"])
                row = dict(model=model, sample_id=source["id"], profile=profile,
                           word_errors=measured["word_errors"], reference_words=measured["reference_words"], wer=measured["wer"],
                           character_errors=measured["character_errors"], reference_characters=measured["reference_characters"],
                           simulated_corrections=len(applied["changes"]), native_wall_ms=applied["wall_ms"],
                           clinical_cue_signature_changed=cue_signature(raw) != cue_signature(applied["text"]))
                rows.append(row)
                for correction in applied["changes"]:
                    changes.append(dict(model=model, sample_id=source["id"], profile=profile, **correction,
                                        before_context=raw[max(0,correction["start"]-65):correction["end"]+65],
                                        cue_changed=cue_signature(correction["source"]) != cue_signature(correction["replacement"])))
                for occurrence in positions:
                    if occurrence["sample_id"] != source["id"]:
                        continue
                    phrase, indices = extracted_span(occurrence["ref_left"], occurrence["ref_right"], mapped, hyp_words, measured["word_edits"])
                    per_occurrence.append(dict(**occurrence, model=model, profile=profile,
                                               observed_tokens=phrase, exact_reference_form=phrase == occurrence["reference_tokens"],
                                               hypothesis_token_indices=indices))
                full_outputs.append(dict(model=model, sample_id=source["id"], profile=profile,
                                         candidate_text=applied["text"], original_hypothesis_sha256=sha(path.parent/"hypothesis.raw.txt")))
            print(f"Checking cached speech: {model}/{source['id']}", flush=True)
    aggregated = []
    for model in ("small", "medium", "large-v3-turbo"):
        for profile in profiles:
            items = [r for r in rows if r["model"] == model and r["profile"] == profile]
            errors = sum(r["word_errors"] for r in items); words = sum(r["reference_words"] for r in items)
            aggregated.append(dict(model=model, profile=profile, word_errors=errors, reference_words=words, wer=errors/words,
                                   simulated_corrections=sum(r["simulated_corrections"] for r in items),
                                   samples_with_changed_cues=sum(r["clinical_cue_signature_changed"] for r in items)))
    return dict(rows=rows, aggregate=aggregated, occurrences=per_occurrence, simulated_corrections=changes,
                outputs=full_outputs, protocol="Exploratory post-ASR text checking. No new speech or independent intonation experiment.")


def audio_examples(selected, sources, checked):
    folder = HERE/"audio_examples"; folder.mkdir(exist_ok=True)
    examples = []
    for number, item in enumerate(selected, 1):
        choices = [r for r in checked["occurrences"] if r["concept_id"] == item["concept_id"] and r["profile"] == "raw" and r["model"] == "small"]
        for choice in choices:
            if not choice["hypothesis_token_indices"]:
                continue
            source = next(s for s in sources if s["id"] == choice["sample_id"])
            data = load(CACHED/"models/small"/source["id"]/"result.json")
            word_tokens = []; intervals = []
            for segment in data["segments"]:
                for word in segment["words"]:
                    values = tokens(word["word"]); word_tokens += values
                    intervals += [(word["start"], word["end"])]*len(values)
            if word_tokens != tokens(data["hypothesis_raw"]):
                continue
            indices = choice["hypothesis_token_indices"]
            start = max(0, min(intervals[i][0] for i in indices)-.8)
            end = max(intervals[i][1] for i in indices)+.8
            with wave.open(str(source["wav_path"]), "rb") as src:
                rate = src.getframerate(); first = int(start*rate); last = min(src.getnframes(), int(end*rate))
                src.setpos(first); pcm = src.readframes(last-first)
                params = src.getparams()
            target = folder/f"{number:02d}_{item['concept_id']}.wav"
            with wave.open(str(target), "wb") as dest:
                dest.setparams(params); dest.writeframes(pcm)
            examples.append(dict(concept_id=item["concept_id"], canonical_en=item["canonical_en"], path=str(target),
                                 sha256=sha(target), source_wav=source["wav_path"], source_sha256=sha(source["wav_path"]),
                                 first_sample=first, last_sample_exclusive=last, sample_rate=rate,
                                 expected_provisional_reference=choice["reference_form"],
                                 asr_aligned_phrase=" ".join(choice["observed_tokens"]),
                                 locator="Approximate cached ASR word timestamps, verified token mapping; not manually certified acoustic boundaries.",
                                 manipulated_prosody=False))
            break
    return examples


def preserve():
    rows = load(HERE/"baseline.json")["files"]; observations = []; strict_count = 0
    for row in rows:
        p = Path(row["path"])
        if not p.is_absolute():
            p = ROOT/p
        actual = sha(p) if p.is_file() else None
        strict = row["path"].startswith(("research/", "glossaries/", "logs/trad_lab/20261020T074247Z/evaluation/", "C:/TRAD-LAB/corpus/")) or row["path"] in {"app/captions/terminology_normalizer.py", "trad_lab/metrics.py"}
        strict_count += int(strict)
        if actual != row["sha256"]:
            if strict:
                raise ValueError(f"Protected source/evidence changed: {p}")
            observations.append(dict(path=row["path"], before_sha256=row["sha256"], observed_sha256=actual,
                                     decision="Concurrent outside-write-boundary change, not reverted"))
    return dict(original_glossary_package_prior_research_audio_and_asr_unchanged=True,
                files_checked=len(rows), strictly_protected_files_checked=strict_count,
                other_snapshot_observations=observations, authored_path=str(HERE), integration_performed=False)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if (HERE/"summary.json").exists():
        raise SystemExit("Completed trial exists; do not overwrite.")
    selection = load(HERE/"selection.json"); selected = selection["selected"]; protocol = load(HERE/"protocol.json")
    concepts = load(PACKAGE/"concepts.json")["concepts"]
    cases = make_cases(selected, concepts); save("constructed_cases.json", cases)
    decisions, calibration_results = calibrate(selected, cases, protocol["tolerance_grid"])
    save("threshold_decisions.json", decisions); save("calibration_results.json", calibration_results)
    print("Thresholds frozen from constructed calibration only", flush=True)
    checking = []
    for item in selected:
        threshold = next(r["selected_auto_threshold"] for r in decisions if r["concept_id"] == item["concept_id"])
        subset = [c for c in cases if c["concept_id"] == item["concept_id"] and c["split"] == "synthetic_checking"]
        for profile, value in [("uniform_090", .90), ("individualized", threshold)]:
            rows = [run_case(c, item, value) for c in subset]
            checking.append(dict(concept_id=item["concept_id"], profile=profile, threshold=value,
                                 **score_cases(rows, subset), results=rows))
    save("synthetic_checking.json", checking)
    sources = load(CACHED/"inputs/inputs.json")
    positions = occurrences(selected, sources); save("reference_occurrences.json", positions)
    checked = check_corpus(selected, decisions, sources, positions); save("real_speech_checking.json", checked)
    clips = audio_examples(selected, sources, checked); save("audio_examples.json", clips)
    table = []
    for item in selected:
        decision = next(r for r in decisions if r["concept_id"] == item["concept_id"])
        synth = {r["profile"]: {k:v for k,v in r.items() if k != "results"} for r in checking if r["concept_id"] == item["concept_id"]}
        real = {}
        for profile in ("raw", "uniform_090", "individualized"):
            obs = [r for r in checked["occurrences"] if r["concept_id"] == item["concept_id"] and r["profile"] == profile]
            real[profile] = dict(observations=len(obs), exact_reference_form=sum(r["exact_reference_form"] for r in obs))
        table.append(dict(concept_id=item["concept_id"], canonical_en=item["canonical_en"], preferred_es=item["preferred_es"],
                          selected_auto_threshold=decision["selected_auto_threshold"], safe_tested_grid_points=decision["safe_tested_grid_points"],
                          synthetic_checking=synth, real_speech=real, operational_approval=False))
    save("term_results.json", table)
    save("preservation.json", preserve())
    summary = dict(status="ten_term_exploratory_trial_complete_not_integrated", seed=selection["seed"], pool_size=selection["pool_size"],
                   selected_terms=10, unique_reference_occurrences=len(positions), model_observations=len(positions)*3,
                   recorded_audio_examples=len(clips), independent_prosody_variations_tested=0,
                   new_asr_inference=False, synthetic_cases_are_not_pronunciations=True,
                   corpus_aggregate=checked["aggregate"], integration_performed=False,
                   thresholds_are_not_calibrated_probabilities=True,
                   limits="Calibration and checking constructed cases share a generator. Cached English corpus was explored previously; source files 02/03 may be adjacent portions of one lecture. No independent speakers, prosody manipulation, Spanish speech or clinical certification claimed.")
    save("summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
