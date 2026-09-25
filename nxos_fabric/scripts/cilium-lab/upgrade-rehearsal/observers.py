#!/usr/bin/env python3
"""Temporary unprivileged mock/monitor sharing an existing lab client's network."""
import argparse,json,os,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--op',type=Path,required=True);p.add_argument('action',choices=['start','stop']);a=p.parse_args();op=a.op.resolve();d=Path(__file__).resolve().parent
image='python:3.13-alpine@sha256:79e7a9b9ff1cbceff819f856fb374477792a5967759d94df266de7b7b4120e6f'
names=['urehearsal-mock','urehearsal-monitor']
if a.action=='start':
 for n in names:
  assert subprocess.run(['docker','inspect',n],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode!=0,n+' already exists'
 (op/'mock').mkdir(exist_ok=True);(op/'monitor.stop').unlink(missing_ok=True)
 commands=[['python3','/app/app.py','--mock-dir','/data/mock','--port','18088'],['python3','/app/monitor.py','--state','/data/state.json','--output','/data/adc-probes.jsonl','--stop','/data/monitor.stop','--site','ADC','--interval','2']]
 for n,cmd in zip(names,commands):
  subprocess.run(['docker','run','-d','--name',n,'--label','lab-upgrade-operation='+str(op),'--user',str(os.getuid())+':'+str(os.getgid()),'--cap-drop','ALL','--read-only','--memory','128m','--network','container:clab-nxos-fabric-multisite-adc-t1sv0101','--mount','type=bind,src='+str(d)+',dst=/app,readonly','--mount','type=bind,src='+str(op)+',dst=/data',image,*cmd],check=True)
else:
 (op/'monitor.stop').touch()
 for n in reversed(names):
  r=subprocess.run(['docker','inspect',n],text=True,capture_output=True)
  if r.returncode:continue
  x=json.loads(r.stdout)[0];assert x['Config']['Labels'].get('lab-upgrade-operation')==str(op)
  log=subprocess.run(['docker','logs',n],capture_output=True,text=True)
  (op/(n+'.log')).write_text(log.stdout+log.stderr)
  subprocess.run(['docker','stop','-t','8',n],check=True);subprocess.run(['docker','rm',n],check=True)
