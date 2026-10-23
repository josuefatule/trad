"""Preserve the first replay, then check the refined identifier policy."""
from pathlib import Path
from datetime import datetime, timezone
import sys
import subprocess
import boundary_normalizer as second
import evaluate_controls as replay

HERE=Path(__file__).resolve().parent
FIRST=HERE.parent


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    if (HERE/'protocol.json').exists():raise SystemExit('Frozen second revision already exists')
    if not (FIRST/'summary.json').exists():raise SystemExit('Wait until first replay completes')
    replay.verify_prior()
    first_protocol=replay.load(FIRST/'protocol.json')
    for r in first_protocol['sources']:
        assert replay.sha(FIRST/r['name'])==r['sha256']
    # Copy immutable input snapshots, not the original glossary or source evidence.
    for name in ['baseline.json','selection.json','thresholds.json','variant_preservation.json','regression_cases.json']:
        p=HERE/name
        if p.exists():assert p.read_bytes()==(FIRST/name).read_bytes()
        else:p.write_bytes((FIRST/name).read_bytes())
    replay.HERE=HERE
    tested=subprocess.run([sys.executable,'-B',str(HERE/'test_boundary.py')],capture_output=True,text=True,encoding='utf-8',cwd=replay.ROOT)
    replay.save('refinement_development_tests.json',dict(returncode=tested.returncode,output=tested.stdout+tested.stderr))
    if tested.returncode:raise SystemExit(tested.stdout+tested.stderr)
    first_findings=replay.load(FIRST/'context_comparison.json')
    protocol=dict(frozen_at_utc=datetime.now(timezone.utc).isoformat(),first_protocol_sha256=replay.sha(FIRST/'protocol.json'),
        same_sixty=True,same_thresholds=True,first_replay_preserved=True,
        motivated_by_first_replay_regressions=first_findings['regressed_cases'],
        refinement='Propagate an otherwise valid automatic phrase rejected only by an identifier boundary to all nested matches; keep unrelated spans repairable.',
        source_files=[dict(name=p.name,sha256=replay.sha(p)) for p in [HERE/'boundary_normalizer.py',HERE/'test_boundary.py',HERE/'replay_refined.py']],
        reused_engine_files=first_protocol['sources'],selection_sha256=replay.sha(HERE/'selection.json'),
        thresholds_sha256=replay.sha(HERE/'thresholds.json'),
        independent_holdout=False,threshold_retuning=False,integration_performed=False)
    (HERE/'protocol.json').write_text(replay.json.dumps(protocol,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    replay.HERE=HERE
    replay.INPUTS=replay.inputs()
    def refined_result(text,profile):
        selected,thresholds,variants=replay.INPUTS
        if profile=='old60':return second.first.ctx.candidate(text,selected,thresholds)
        return second.candidate(text,selected,thresholds,variants,profile)
    replay.result=refined_result
    print('Second revision frozen; first replay preserved',flush=True)
    constructed=replay.replay_constructed();contexts=replay.replay_contexts()
    regressions=replay.replay_regressions(replay.load(HERE/'regression_cases.json'));corpus=replay.speech()
    replay.save('preservation.json',replay.preservation())
    summary=dict(status='refined_laboratory_replay_complete_not_integrated',same_sixty=True,thresholds_unchanged=True,
        first_attempt_preserved=True,corpus_aggregate=corpus['aggregate'],constructed=constructed['summary'],contexts=contexts['summary'],
        context_improvements=len(contexts['improved_cases']),context_regressions=len(contexts['regressed_cases']),
        regression_summary=regressions['summary'],refinement_development_tests_passed=True,
        policy_developed_from_previously_observed_regressions=True,policy_retuned_after_this_replay=False,
        independent_holdout=False,new_asr_inference=False,independent_clinical_validation=False,integration_performed=False)
    replay.save('summary.json',summary)
    print(replay.json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
