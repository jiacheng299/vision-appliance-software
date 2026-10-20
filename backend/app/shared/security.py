import os
import json
import ipaddress
import socket
from urllib.parse import urlsplit, urlunsplit, unquote
from cryptography.fernet import Fernet
from .errors import Error


def same_origin_request(connection):
    """Reject unrelated websites without requiring accounts or cookies."""
    if connection.headers.get('sec-fetch-site') == 'cross-site':
        return False
    origin = connection.headers.get('origin')
    if not origin:
        return True
    try:
        parts = urlsplit(origin)
        return parts.scheme in ('http', 'https') and parts.netloc == connection.headers.get('host')
    except ValueError:
        return False

class Vault:
    def __init__(self, config):
        path = config.var_root / 'secrets' / 'camera.key'
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(descriptor,'wb') as file:
                file.write(Fernet.generate_key())
        self.fernet = Fernet(path.read_bytes())
    def encrypt(self, values):
        return self.fernet.encrypt(json.dumps(values).encode()).decode()
    def decrypt(self, value):
        return json.loads(self.fernet.decrypt(value.encode())) if value else {'username':'','password':''}

def camera_address(value, networks):
    try:
        parts = urlsplit(value)
        if parts.scheme not in ('rtsp','rtsps') or not parts.hostname or parts.query or parts.fragment:
            raise ValueError()
        if any(ord(c)<32 for c in value):
            raise ValueError()
        port = parts.port or (322 if parts.scheme == 'rtsps' else 554)
        addresses = socket.getaddrinfo(parts.hostname,port,type=socket.SOCK_STREAM)
        allowed = [ipaddress.ip_network(n) for n in networks]
        ips = {record[4][0] for record in addresses}
        if not ips or not all(any(ipaddress.ip_address(ip) in net for net in allowed if net.version == ipaddress.ip_address(ip).version) for ip in ips):
            raise ValueError()
        host = parts.hostname
        host = f'[{host}]' if ':' in host else host
        netloc = host + (f':{parts.port}' if parts.port else '')
        public_address = urlunsplit((parts.scheme,netloc,parts.path or '/', '', ''))
        credentials = {'username':unquote(parts.username or ''),'password':unquote(parts.password or '')}
        return public_address, credentials, sorted(ips)[0]
    except (ValueError,OSError):
        raise Error(422,'camera_address_forbidden','摄像头地址须为允许网段内的 RTSP 地址，且不能包含查询参数；请检查安全设置。')
