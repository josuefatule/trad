import argparse

def main():
    p=argparse.ArgumentParser(description='M4-B isolated diagnostics; services require fresh human authorization')
    sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('prepare');a.add_argument('--out',required=True)
    a=sub.add_parser('serve');a.add_argument('role',choices=['wlk','trad']);a.add_argument('--plan',required=True);a.add_argument('--authorization',required=True)
    a=sub.add_parser('capture');a.add_argument('--plan',required=True);a.add_argument('--out',required=True);a.add_argument('--authorization',required=True)
    a=sub.add_parser('analyze');a.add_argument('--capture',required=True);a.add_argument('--trad',required=True);a.add_argument('--wlk',required=True)
    a=sub.add_parser('offline');a.add_argument('--capture',required=True);a.add_argument('--out',required=True)
    a=sub.add_parser('align');a.add_argument('--capture',required=True)
    args=p.parse_args()
    if args.command=='prepare':
        from .prepare import prepare
        print(prepare(args.out))
    elif args.command=='serve':
        from .server import serve
        serve(args.role,args.plan,args.authorization)
    elif args.command=='capture':
        from .capture import capture
        capture(args)
    elif args.command=='analyze':
        from .analyze import analyze
        print(analyze(args.capture,args.trad,args.wlk))
    elif args.command=='offline':
        from .offline import offline
        offline(args.capture,args.out)
    else:
        from .align import align
        print(align(args.capture))

if __name__=='__main__':main()
