#!/usr/bin/env python3
"""Actual DoH egress probe; mock addresses and certificates are TEST ONLY.

All network traffic stays on loopback. Production TLS verification is not
changed. This is an optional runtime diagnostic, not a publishing gate.
"""
import argparse
import base64
import http.server
import json
import pathlib
import select
import socket
import socketserver
import ssl
import struct
import subprocess
import sys
import tempfile
import threading
import time
from urllib.request import Request, urlopen
from urllib.parse import urlsplit, parse_qs
import yaml
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.dont_write_bytecode = True
from build_rules import clash_dns_policies
parser = argparse.ArgumentParser(description='Probe actual Mihomo DoH egress with local mock proxies and IP DoH endpoints. Exit 2 means same-node requirements failed.')
parser.add_argument('--mihomo', default='mihomo', help='Mihomo binary to probe')
args = parser.parse_args()
records = []
observations = {}

def recv_exact(sock, n):
    data = b''
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise EOFError
        data += chunk
    return data

class HTTPS(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def do_GET(self):
        raw = parse_qs(urlsplit(self.path).query)['dns'][0]
        self.respond(base64.urlsafe_b64decode(raw + '=' * (-len(raw) % 4)))

    def do_POST(self):
        self.respond(self.rfile.read(int(self.headers['Content-Length'])))

    def respond(self, data):
        pos = 12
        labels = []
        while data[pos]:
            n = data[pos]
            labels.append(data[pos + 1:pos + 1 + n].decode())
            pos += n + 1
        pos += 1
        query_type = struct.unpack('!H', data[pos:pos + 2])[0]
        question = data[12:pos + 4]
        records.append({'node': self.server.node, 'resolver': self.headers.get('Host'), 'domain': '.'.join(labels), 'type': query_type})
        answer = struct.pack('!HHHHHH', struct.unpack('!H', data[:2])[0], 33152, 1, 1, 0, 0) + question + b'\xc0\x0c' + struct.pack('!HHIH', 16, 1, 0, 6) + b'\x05probe'
        self.send_response(200)
        self.send_header('Content-Type', 'application/dns-message')
        self.send_header('Content-Length', str(len(answer)))
        self.end_headers()
        self.wfile.write(answer)

    def log_message(self, *args):
        pass

class TCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

class SOCKS(socketserver.BaseRequestHandler):

    def handle(self):
        try:
            s = self.request
            s.settimeout(10)
            v, n = recv_exact(s, 2)
            recv_exact(s, n)
            s.sendall(b'\x05\x00')
            v, cmd, zero, kind = recv_exact(s, 4)
            if kind == 1:
                host = socket.inet_ntoa(recv_exact(s, 4))
            elif kind == 3:
                host = recv_exact(s, recv_exact(s, 1)[0]).decode()
            else:
                host = socket.inet_ntop(socket.AF_INET6, recv_exact(s, 16))
            port = struct.unpack('!H', recv_exact(s, 2))[0]
            upstream = socket.create_connection(('127.0.0.1', self.server.upstream), timeout=5)
            s.sendall(b'\x05\x00\x00\x01\x7f\x00\x00\x01' + struct.pack('!H', upstream.getsockname()[1]))
            with upstream:
                while True:
                    ready, _, _ = select.select([s, upstream], [], [], 10)
                    if not ready:
                        return
                    for a in ready:
                        d = a.recv(65536)
                        if not d:
                            return
                        (upstream if a is s else s).sendall(d)
        except (OSError, EOFError):
            pass

def port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]

def dns_query(p, domain):
    qname = b''.join((bytes([len(l)]) + l.encode() for l in domain.split('.'))) + b'\x00'
    packet = struct.pack('!HHHHHH', 123, 256, 1, 0, 0, 0) + qname + struct.pack('!HH', 16, 1)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(5)
        s.sendto(packet, ('127.0.0.1', p))
        return s.recv(65536)

def api(p, path, data=None):
    req = Request('http://127.0.0.1:' + str(p) + path, data=None if data is None else json.dumps(data).encode(), method='GET' if data is None else 'PUT', headers={'Content-Type': 'application/json'})
    with urlopen(req, timeout=2) as r:
        return r.read()
with tempfile.TemporaryDirectory(prefix='proxyrules-probe-') as tmp:
    tmp = pathlib.Path(tmp)
    cert = tmp / 'cert.pem'
    key = tmp / 'key.pem'
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', str(key), '-out', str(cert), '-days', '1', '-subj', '/CN=localhost'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert, key)
    servers = []
    nodes = []
    for node in ['node-us', 'node-jp', 'DIRECT']:
        h = http.server.ThreadingHTTPServer(('127.0.0.1', 0), HTTPS)
        h.node = node
        h.socket = ctx.wrap_socket(h.socket, server_side=True)
        servers.append(h)
        threading.Thread(target=h.serve_forever, daemon=True).start()
        if node != 'DIRECT':
            proxy = TCPServer(('127.0.0.1', 0), SOCKS)
            proxy.upstream = h.server_port
            servers.append(proxy)
            threading.Thread(target=proxy.serve_forever, daemon=True).start()
            nodes.append({'name': node, 'type': 'socks5', 'server': '127.0.0.1', 'port': proxy.server_address[1]})
        else:
            direct_port = h.server_port
    for address in ('127.0.0.2', '127.0.0.3'):
        h = http.server.ThreadingHTTPServer((address, direct_port), HTTPS)
        h.node = 'DIRECT'
        h.socket = ctx.wrap_socket(h.socket, server_side=True)
        servers.append(h)
        threading.Thread(target=h.serve_forever, daemon=True).start()
    rules = ['DOMAIN-SUFFIX,ai.example,AI', 'DOMAIN-SUFFIX,video.example,Video', 'DOMAIN-SUFFIX,direct.example,DIRECT', 'MATCH,Other']
    policies, providers = clash_dns_policies(rules)

    def mock_url(url):
        base, group = url.split('#')
        base = base.replace('https://120.53.53.53/dns-query', f'https://127.0.0.1:{direct_port}/dns-query').replace('https://1.12.12.12/dns-query', f'https://127.0.0.1:{direct_port}/dns-query').replace('https://1.1.1.1/dns-query', f'https://127.0.0.2:{direct_port}/dns-query').replace('https://8.8.8.8/dns-query', f'https://127.0.0.3:{direct_port}/dns-query')
        return base + '#' + group + '&skip-cert-verify=true'
    policies = {k: [mock_url(v) for v in values] for k, values in policies.items()}
    mixed, dns, controller = (port(), port(), port())
    config = {'mixed-port': mixed, 'external-controller': f'127.0.0.1:{controller}', 'mode': 'rule', 'log-level': 'debug', 'proxies': nodes, 'proxy-groups': [{'name': name, 'type': 'select', 'proxies': members} for name, members in [('AI', ['node-us', 'node-jp', 'DIRECT']), ('Video', ['node-jp', 'node-us', 'DIRECT']), ('Other', ['node-jp', 'node-us', 'DIRECT'])]], 'rules': rules, 'rule-providers': providers, 'dns': {'enable': True, 'listen': f'127.0.0.1:{dns}', 'enhanced-mode': 'fake-ip', 'respect-rules': True, 'proxy-server-nameserver': [mock_url('https://1.12.12.12/dns-query#DIRECT')], 'direct-nameserver': [mock_url('https://1.12.12.12/dns-query#DIRECT')], 'direct-nameserver-follow-policy': False, 'default-nameserver': [mock_url('https://1.12.12.12/dns-query#DIRECT')], 'nameserver': [mock_url('https://1.1.1.1/dns-query#Other')], 'nameserver-policy': policies}}
    path = tmp / 'config.yaml'
    path.write_text(yaml.safe_dump(config, sort_keys=False))
    logs = open(tmp / 'log', 'w+')
    p = subprocess.Popen([args.mihomo, '-d', str(tmp), '-f', str(path)], stdout=logs, stderr=logs)
    try:
        for i in range(100):
            try:
                api(controller, '/version')
                break
            except OSError:
                time.sleep(0.05)
        start = len(records)
        dns_query(dns, 'one.ai.example')
        observations['AI initial'] = [r for r in records if r['domain'] == 'one.ai.example']
        print('AI initial', observations['AI initial'], flush=True)
        start = len(records)
        dns_query(dns, 'one.video.example')
        observations['Video initial'] = [r for r in records if r['domain'] == 'one.video.example']
        print('Video initial', observations['Video initial'], flush=True)
        api(controller, '/proxies/AI', {'name': 'node-jp'})
        start = len(records)
        dns_query(dns, 'two.ai.example')
        observations['AI after switch to JP'] = [r for r in records if r['domain'] == 'two.ai.example']
        print('AI after switch to JP', observations['AI after switch to JP'], flush=True)
        api(controller, '/proxies/AI', {'name': 'DIRECT'})
        start = len(records)
        dns_query(dns, 'three.ai.example')
        observations['AI after switch DIRECT'] = [r for r in records if r['domain'] == 'three.ai.example']
        print('AI after switch DIRECT', observations['AI after switch DIRECT'], flush=True)
        start = len(records)
        dns_query(dns, 'one.direct.example')
        observations['Static DIRECT'] = [r for r in records if r['domain'] == 'one.direct.example']
        print('Static DIRECT', observations['Static DIRECT'], flush=True)
    finally:
        p.terminate()
        p.wait(timeout=5)
        logs.flush()
        logs.close()
        for server in servers:
            server.shutdown()
            server.server_close()
expected_nodes = {'AI initial': 'node-us', 'Video initial': 'node-jp', 'AI after switch to JP': 'node-jp', 'AI after switch DIRECT': 'DIRECT', 'Static DIRECT': 'DIRECT'}
failures = []
for name, node in expected_nodes.items():
    queries = observations.get(name, [])
    if not queries or any((query['node'] != node for query in queries)):
        failures.append(name + ': query did not use the selected node')
    if name == 'AI after switch DIRECT' and any((not query['resolver'].startswith('127.0.0.1:') for query in queries)):
        failures.append(name + ': resolver did not switch to Ali mock endpoint')
print(json.dumps({'same_node_requirements_met': not failures, 'failures': failures}, ensure_ascii=False, indent=2))
sys.exit(2 if failures else 0)
