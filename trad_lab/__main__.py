import argparse
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description='TRAD-LAB: local evaluation, no LIVE modifications or DeepL')
    sub=parser.add_subparsers(dest='command',required=True)
    evaluate=sub.add_parser('evaluate')
    evaluate.add_argument('--corpus',required=True);evaluate.add_argument('--out',required=True)
    evaluate.add_argument('--glossary',required=True)
    evaluate.add_argument('--models',nargs='+',choices=['small','medium','large-v3-turbo'],default=['small','medium','large-v3-turbo'])
    evaluate.add_argument('--allow-download',action='store_true',help='Allow missing model weights only; never install packages')
    evaluate.add_argument('--with-context',action='store_true',help='Additional small-only initial_prompt experiment, separate from baseline ranking')
    evaluate.add_argument('--resume',action='store_true',help='Reuse completed models only with identical input hashes/profile; archive failed attempts')
    evaluate.add_argument('--model-timeout-seconds',type=float,default=1800)
    worker=sub.add_parser('_worker')
    worker.add_argument('--out',required=True);worker.add_argument('--glossary',required=True)
    worker.add_argument('--model',required=True,choices=['small','medium','large-v3-turbo'])
    worker.add_argument('--allow-download',action='store_true');worker.add_argument('--context',action='store_true')
    audit=sub.add_parser('audit-glossary');audit.add_argument('--glossary',required=True);audit.add_argument('--out',required=True)
    summarize=sub.add_parser('report');summarize.add_argument('--out',required=True);summarize.add_argument('--glossary',required=True)
    stream=sub.add_parser('stream-capture',help='Requires authorized isolated servers; never starts services')
    stream.add_argument('--url',default='http://127.0.0.1:18010');stream.add_argument('--audio',required=True)
    stream.add_argument('--reference',help='Only a reference matching this exact fragment; omitted means disagreement analysis only')
    stream.add_argument('--out',required=True)
    same=sub.add_parser('same-pcm',help='GPU replay on source clip and exact captured PCM, after lab STOP')
    same.add_argument('--capture',required=True);same.add_argument('--source',required=True)
    same.add_argument('--glossary',required=True);same.add_argument('--out',required=True)
    args=parser.parse_args()
    if args.command=='evaluate':
        from .runner import evaluate
        return evaluate(args)
    if args.command=='_worker':
        from .runner import model_worker
        return model_worker(args)
    if args.command=='audit-glossary':
        from .glossary import audit
        from .runner import save
        result=audit(args.glossary);save(args.out,result)
        print('Glossary audit:',result['term_count'],'terms; compatible:',result['schema_compatible'])
    if args.command=='report':
        from .report import reports
        reports(Path(args.out),args.glossary)
    if args.command=='stream-capture':
        from .streaming import capture
        capture(args)
    if args.command=='same-pcm':
        from .same_pcm import compare
        return compare(args)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
