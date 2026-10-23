"""Local-only projection of the launcher's network selection. No control writes."""
import ipaddress
import json
from pathlib import Path
import socket

STATE = Path(__file__).resolve().parents[1] / '.runtime/launcher/network.json'


def private_ip(value):
    if not isinstance(value, str):
        return None
    try:
        address = ipaddress.IPv4Address(value)
    except ipaddress.AddressValueError:
        return None
    return str(address) if any(address in ipaddress.ip_network(n) for n in (
        '10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')) else None


def network_status(path=None):
    result = {'local_ip': None, 'local_ips': [], 'overlay_pc_ip': None,
              'overlay_url': None, 'lan_enabled': False, 'network_profile': None, 'overlay_access': 'single',
              'operator_url': 'http://localhost:8010/operator'}
    try:
        data = json.loads(Path(path or STATE).read_text(encoding='utf-8-sig'))
        if not isinstance(data, dict):
            raise ValueError('Network state must be an object')
        result['local_ips'] = sorted({ip for value in data.get('local_ips', [])
                                     if (ip := private_ip(value))})
        result['local_ip'] = private_ip(data.get('local_ip', ''))
        result['overlay_pc_ip'] = private_ip(data.get('overlay_pc_ip', ''))
        result['network_profile'] = data.get('network_profile') if data.get('network_profile') in {'Private', 'Public', 'DomainAuthenticated'} else None
        result['overlay_access'] = 'any' if data.get('overlay_access') == 'any' else 'single'
        result['lan_enabled'] = (data.get('lan_enabled') is True and
            result['local_ip'] is not None and result['local_ip'] in result['local_ips'] and
            (result['overlay_access'] == 'any' or (result['network_profile'] == 'Private' and
            result['overlay_pc_ip'] is not None and result['local_ip'] != result['overlay_pc_ip'])))
        if result['lan_enabled']:
            result['overlay_url'] = f"http://{result['local_ip']}:3000/overlay"
    except (OSError, ValueError, TypeError):
        pass
    if not result['local_ips']:
        try:
            result['local_ips'] = sorted({ip for row in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
                                         if (ip := private_ip(row[4][0]))})
        except OSError:
            pass
    if not result['local_ip'] and len(result['local_ips']) == 1:
        result['local_ip'] = result['local_ips'][0]
    return result
