"""Start a detached owned service without inheriting the caller's console pipes."""
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    root = Path(__file__).resolve().parents[1]
    spec = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8-sig'))
    executable = Path(spec['executable']).resolve()
    if executable not in {root / '.venv/Scripts/python.exe', root / '.venv-wlk/Scripts/python.exe'}:
        raise ValueError('Use the existing TRAD environments')
    if spec['arguments'][:3] != ['-B', '-m', 'app.service_host']:
        raise ValueError('Only the owned service host can be detached')
    for name in ['stdout', 'stderr']:
        if Path(spec[name]).resolve().parent != root / '.runtime/launcher':
            raise ValueError('Logs must remain in the launcher runtime')
    with open(spec['stdout'], 'xb') as stdout, open(spec['stderr'], 'xb') as stderr:
        options = dict(cwd=root, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                       close_fds=True)
        if os.name == 'nt':
            options['creationflags'] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            options['start_new_session'] = True
        process = subprocess.Popen([str(executable), *spec['arguments']], **options)
    print(json.dumps({'pid': process.pid}))


if __name__ == '__main__':
    main()
