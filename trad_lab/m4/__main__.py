import argparse


def main():
    parser=argparse.ArgumentParser(description='Isolated M4 experiments, cached small only')
    sub=parser.add_subparsers(dest='command',required=True)
    report=sub.add_parser('report');report.add_argument('--root',required=True)
    audio=sub.add_parser('audio-diagnostic');audio.add_argument('--source',required=True);audio.add_argument('--captured',required=True);audio.add_argument('--out',required=True)
    references=sub.add_parser('prepare-references');references.add_argument('--m3',required=True);references.add_argument('--out',required=True)
    for name,repeats in [('offline',3),('simul',2),('pipeline',2),('resampler',2),('local-agreement',2)]:
        p=sub.add_parser(name);p.add_argument('--clips',required=True);p.add_argument('--out',required=True)
        p.add_argument('--glossary',required=True);p.add_argument('--repeats',type=int,default=repeats)
        if name=='simul':p.add_argument('--chunk-s',type=float,default=1.)
    args=parser.parse_args()
    if args.command=='report':
        from .report import summarize
        summarize(args.root);return
    if args.command=='audio-diagnostic':
        from .audio_analysis import analyze
        analyze(args.source,args.captured,args.out);return
    if args.command=='prepare-references':
        from .references import prepare
        prepare(args.m3,args.out);return
    if not 1<=args.repeats<=5:parser.error('repeats must be 1..5')
    from .experiments import offline,simul
    if args.command=='simul':
        if args.chunk_s not in {.5,1.}:parser.error('fixed chunk must be 0.5 or 1.0 s')
        simul(args)
    elif args.command=='local-agreement':
        from .local_agreement import run
        run(args)
    elif args.command=='resampler':
        from .resampler_experiment import run
        run(args)
    elif args.command=='pipeline':
        import asyncio
        from .pipeline import run
        asyncio.run(run(args))
    else:offline(args)


if __name__=='__main__':main()
