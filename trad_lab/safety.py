"""Read-only LIVE guard; credentials stay in memory, never in outputs."""
import json
import socket
import urllib.error
import urllib.request
from urllib.parse import urlsplit


class LiveGuard:
    def __init__(self,base='http://localhost:8010'):
        self.base=base;self.token=None

    def check(self):
        try:
            with urllib.request.urlopen(self.base+'/health',timeout=2) as r:json.load(r)
        except urllib.error.URLError:
            # Fail closed if a port is listening but status cannot be established.
            port=urlsplit(self.base).port or 80
            for family,host in [(socket.AF_INET,'127.0.0.1'),(socket.AF_INET6,'::1')]:
                try:
                    with socket.socket(family) as sock:
                        sock.settimeout(.5)
                        if sock.connect_ex((host,port))==0:return {'safe':False,'reason':'service_listening_status_unverified'}
                except OSError:pass
            return {'safe':True,'reason':'TRAD_8010_not_listening'}
        try:
            if self.token is None:
                with urllib.request.urlopen(self.base+'/api/operator/bootstrap',timeout=2) as r:self.token=json.load(r)['control_token']
            req=urllib.request.Request(self.base+'/api/operator/status',headers={'X-Operator-Token':self.token})
            with urllib.request.urlopen(req,timeout=2) as r:state=json.load(r)
        except urllib.error.HTTPError as exc:
            if exc.code in (401,403):self.token=None
            return {'safe':False,'reason':'operator_status_unverified'}
        except Exception:
            return {'safe':False,'reason':'operator_status_unverified'}
        if state.get('state') not in {'waiting','stopped','disconnected','error','connecting','live','draining'}:
            return {'safe':False,'reason':'unknown_session_state'}
        active=state.get('session_open') or state.get('state') in {'connecting','live','draining'}
        return {'safe':not bool(active),'reason':'TRAD_active' if active else 'TRAD_inactive',
            'state':state.get('state'),'session_open':state.get('session_open')}


def gpu_snapshot():
    import subprocess
    result=subprocess.run(['nvidia-smi','--query-gpu=name,driver_version,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=8)
    if result.returncode:raise RuntimeError('nvidia-smi unavailable')
    cells=[x.strip() for x in result.stdout.splitlines()[0].split(',')]
    return dict(zip(['name','driver','total_mib','used_mib','free_mib','util_percent','temperature_c'],cells))
