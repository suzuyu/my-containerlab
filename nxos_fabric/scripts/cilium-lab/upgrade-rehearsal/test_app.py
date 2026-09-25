#!/usr/bin/env python3
"""Test the observer contract: trust socket source, and preserve idempotency."""
import json,os,socket,subprocess,tempfile,time,unittest,urllib.error,urllib.request
from pathlib import Path
class MockContract(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name)
  cls.allow=cls.root/'allow.json';cls.allow.write_text('["127.0.0.1"]')
  with socket.socket() as s:s.bind(('127.0.0.1',0));cls.port=s.getsockname()[1]
  cls.proc=subprocess.Popen(['python3',str(Path(__file__).with_name('app.py')),'--mock-dir',str(cls.root),'--port',str(cls.port)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  cls.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
  for _ in range(50):
   try:
    with cls.opener.open('http://127.0.0.1:'+str(cls.port)+'/health',timeout=.2):return
   except OSError:time.sleep(.05)
  raise RuntimeError('mock did not start')
 @classmethod
 def tearDownClass(cls):cls.proc.terminate();cls.proc.wait(timeout=5);cls.temp.cleanup()
 def test_source_is_socket_not_header(self):
  self.allow.write_text('["127.0.0.1"]')
  req=urllib.request.Request('http://127.0.0.1:'+str(self.port)+'/health',headers={'X-Forwarded-For':'172.16.24.100'})
  with self.opener.open(req) as r:self.assertEqual(json.load(r)['observed_source'],'127.0.0.1')
 def test_denied_source_has_no_receipt(self):
  self.allow.write_text('["172.16.24.100"]')
  with self.assertRaises(urllib.error.HTTPError) as e:self.opener.open('http://127.0.0.1:'+str(self.port)+'/requests')
  self.assertEqual(e.exception.code,403)
 def test_ipv6_allowlist_normalization(self):
  self.allow.write_text('["0:0:0:0:0:0:0:1"]')
  with self.opener.open('http://[::1]:'+str(self.port)+'/health') as r:
   self.assertEqual(json.load(r)['observed_source'],'::1')
 def test_idempotent_receipt(self):
  self.allow.write_text('["127.0.0.1"]');receipts=[]
  for _ in range(2):
   req=urllib.request.Request('http://127.0.0.1:'+str(self.port)+'/requests',data=b'',headers={'Idempotency-Key':'run1-key1'})
   with self.opener.open(req) as r:receipts.append(json.load(r)['receipt'])
  self.assertEqual(receipts[0],receipts[1])
if __name__=='__main__':unittest.main()
