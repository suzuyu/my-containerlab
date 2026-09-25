#!/usr/bin/env python3
"""Functional endpoint probes, including independent BDC and k04 NodePort."""
import argparse,json,subprocess,ipaddress,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--op',type=Path,required=True);p.add_argument('--cluster',default='adc-k02');p.add_argument('--mode',choices=['echo','separate','same'],default='echo');p.add_argument('--nodeport',type=int);p.add_argument('--tag',required=True);a=p.parse_args();rows=[]
for site in ['adc-t1sv0101','bdc-t1sv0104']:
 for af in [4,6]:
  host=('172.16.6.21' if af==4 else '[fd21:0:0:6::2:1]') if a.nodeport else ('172.16.14.20' if af==4 else '[fd21:0:0:14:0:0:1:100]')
  port=':'+str(a.nodeport) if a.nodeport else ''
  path='/' if a.mode=='echo' else '/report?af='+str(af)
  cmd=['docker','exec','clab-nxos-fabric-multisite-'+site,'curl','--noproxy','*','-fsS','--connect-timeout','3','--max-time','5','http://'+host+port+path]
  t=time.time();r=subprocess.run(cmd,text=True,capture_output=True,timeout=12);body={}
  try:body=json.loads(r.stdout)
  except ValueError:pass
  ok=r.returncode==0 and body.get('cluster')==a.cluster
  if a.mode!='echo':
   v='100' if a.mode=='same' else ('101' if a.cluster=='adc-k02' else '104');expected='172.16.24.'+v if af==4 else 'fd21:0:0:24::'+v
   try:ok=ok and ipaddress.ip_address(body.get('external',{}).get('observed_source','0.0.0.0'))==ipaddress.ip_address(expected)
   except ValueError:ok=False
  rows.append({'site':site,'af':af,'time':t,'duration':time.time()-t,'ok':ok,'rc':r.returncode,'response':body,'error':r.stderr})
  print(site,'IPv'+str(af),ok,body,flush=True)
a.op.joinpath(a.tag+'-functional.json').write_text(json.dumps(rows,indent=2))
raise SystemExit(0 if all(r['ok'] for r in rows) else 1)
