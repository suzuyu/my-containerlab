#!/usr/bin/env python3
"""Isolated lab application/mock. No external Python dependencies."""
import argparse
import http.server
import ipaddress
import json
import os
from pathlib import Path
import socket
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

os.umask(0o077)
P = argparse.ArgumentParser()
P.add_argument('--mock-dir', type=Path)
P.add_argument('--port', type=int, default=8080)
A = P.parse_args()
STATE = {'enabled': True, 'active': 0}
LOCK = threading.Lock()
CLUSTER = os.getenv('CLUSTER', 'external')
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

class Server(http.server.ThreadingHTTPServer):
    address_family = socket.AF_INET6
    daemon_threads = True
    def server_bind(self):
        self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        super().server_bind()

class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    def log_message(self, *args):
        pass
    def send(self, status, data):
        raw = json.dumps(data, sort_keys=True).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        try:
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            pass
    def do_GET(self):
        self.handle_request()
    def do_POST(self):
        self.handle_request()
    def handle_request(self):
        start = time.time()
        path = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(path.query)
        rid = self.headers.get('X-Request-ID', query.get('id', [''])[0])
        peer = ipaddress.ip_address(self.client_address[0])
        peer = str(peer.ipv4_mapped if getattr(peer, 'ipv4_mapped', None) else peer)
        body = {'cluster': CLUSTER, 'pod': socket.gethostname(), 'request_id': rid}
        if self.server.server_port == 8081:
            if self.command == 'POST':
                data = json.loads(self.rfile.read(int(self.headers.get('Content-Length', '0'))))
                with LOCK:
                    STATE['enabled'] = bool(data['enabled'])
            with LOCK:
                self.send(200, dict(STATE))
            return
        if A.mock_dir:
            allow = [str(ipaddress.ip_address(x)) for x in json.loads((A.mock_dir / 'allow.json').read_text())]
            status = 200 if peer in allow else 403
            body.update(observed_source=peer, allowed=status == 200)
            if status == 200 and path.path == '/requests':
                key = self.headers.get('Idempotency-Key', '')
                if not key:
                    status = 400
                else:
                    with sqlite3.connect(str(A.mock_dir / 'receipts.db'), timeout=10) as db:
                        db.execute('CREATE TABLE IF NOT EXISTS receipts (id INTEGER PRIMARY KEY, key TEXT UNIQUE NOT NULL)')
                        db.execute('INSERT OR IGNORE INTO receipts(key) VALUES (?)', (key,))
                        body['receipt'] = db.execute('SELECT id FROM receipts WHERE key=?', (key,)).fetchone()[0]
                        body['key'] = key
            record = dict(body, time=start, status=status, path=path.path)
            with LOCK:
                with (A.mock_dir / 'requests.jsonl').open('a') as f:
                    f.write(json.dumps(record) + '\n')
            self.send(status, body)
            return
        if path.path in ('/healthz', '/whoami'):
            self.send(200, body)
            return
        with LOCK:
            if not STATE['enabled']:
                self.send(503, dict(body, error='business disabled'))
                return
            STATE['active'] += 1
        try:
            if path.path in ('/report', '/submit'):
                af = query.get('af', ['4'])[0]
                host = os.environ['MOCK_V4'] if af == '4' else '[' + os.environ['MOCK_V6'] + ']'
                remote_path = '/requests' if path.path == '/submit' else '/reference'
                req = urllib.request.Request('http://' + host + ':18088' + remote_path,
                    headers={'X-Request-ID': rid, 'Idempotency-Key': rid, 'Connection': 'close'},
                    data=b'' if path.path == '/submit' else None)
                try:
                    with OPENER.open(req, timeout=3) as r:
                        body['external'] = json.load(r)
                    self.send(200, body)
                except (urllib.error.URLError, TimeoutError, OSError) as exc:
                    self.send(502, dict(body, error=str(exc)))
            else:
                self.send(200, body)
        finally:
            with LOCK:
                STATE['active'] -= 1

if not A.mock_dir:
    admin = http.server.ThreadingHTTPServer(('127.0.0.1', 8081), Handler)
    threading.Thread(target=admin.serve_forever, daemon=True).start()
Server(('::', A.port), Handler).serve_forever()
