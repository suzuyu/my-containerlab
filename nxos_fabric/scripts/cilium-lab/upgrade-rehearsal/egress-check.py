#!/usr/bin/env python3
"""Probe external mock directly from every A Pod, even when business gate is off."""
import argparse,json,subprocess,ipaddress,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--op',type=Path,required=True);p.add_argument('--cluster',required=True,choices=['adc-k02','adc-k04']);p.add_argument('--mode',choices=['separate','same'],required=True);p.add_argument('--tag',required=True);a=p.parse_args();k=['kubectl','--context','kind-'+a.cluster];ns='cilium-upgrade-rehearsal';v='100' if a.mode=='same' else ('101' if a.cluster=='adc-k02' else '104');rows=[]
pods=json.loads(subprocess.check_output(k+['-n',ns,'get','pods','-l','app=app-a','-o','json'],text=True))['items']
for pod in pods:
 for af,host,expect in [(4,'172.16.0.1','172.16.24.'+v),(6,'[fd21:0:0:1::101]','fd21:0:0:24::'+v)]:
  code="import urllib.request; o=urllib.request.build_opener(urllib.request.ProxyHandler({})); print(o.open('http://"+host+":18088/health',timeout=5).read().decode())"
  r=subprocess.run(k+['-n',ns,'exec',pod['metadata']['name'],'--','python3','-c',code],capture_output=True,text=True,timeout=15);body={}
  try:body=json.loads(r.stdout)
  except ValueError:pass
  ok=r.returncode==0 and ipaddress.ip_address(body.get('observed_source','0.0.0.0'))==ipaddress.ip_address(expect)
  rows.append({'pod':pod['metadata']['name'],'node':pod['spec']['nodeName'],'af':af,'ok':ok,'response':body,'error':r.stderr});print(rows[-1],flush=True)
a.op.joinpath(a.tag+'-egress-check.json').write_text(json.dumps(rows,indent=2))
raise SystemExit(0 if len(rows)==4 and all(r['ok'] for r in rows) else 1)
