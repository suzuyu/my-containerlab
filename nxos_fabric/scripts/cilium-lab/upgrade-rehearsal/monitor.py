#!/usr/bin/env python3
"""Run inside a Fabric client's network namespace; fixed, unretried probes."""
import argparse,concurrent.futures,ipaddress,json,os,threading,time,urllib.request,urllib.error
from pathlib import Path
os.umask(0o077)
p=argparse.ArgumentParser();p.add_argument('--state',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--stop',type=Path,required=True);p.add_argument('--site',required=True);p.add_argument('--interval',type=float,default=1);p.add_argument('--timeout',type=float,default=5)
a=p.parse_args();lock=threading.Lock();opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def loop(af,control=False):
 count=0
 while not a.stop.exists():
  state=json.loads(a.state.read_text());count+=1;t=time.time();mono=time.monotonic()
  ip=('172.16.14.21' if control else '172.16.14.20') if af==4 else ('[fd21:0:0:14:0:0:1:101]' if control else '[fd21:0:0:14:0:0:1:100]')
  path='/' if control or state.get('mode')=='echo' else '/report?af='+str(af)
  row={'time':t,'monotonic':mono,'phase':state['phase'],'site':a.site,'af':af,'target':'B' if control else 'A','expected_cluster':'adc-k02' if control else state.get('expected_cluster'),'expected_source':None if control else state.get('expected_source',{}).get(str(af)),'status':0}
  req=urllib.request.Request('http://'+ip+path,headers={'Connection':'close','X-Request-ID':a.site+'-'+str(af)+'-'+str(t)})
  try:
   with opener.open(req,timeout=a.timeout) as r:row.update(status=r.status,response=json.load(r))
  except urllib.error.HTTPError as e:
   row['status']=e.code
   try:row['response']=json.load(e)
   except Exception:row['error']=str(e)
  except Exception as e:row['error']=str(e)
  row['duration']=time.monotonic()-mono;row['end_time']=time.time()
  row['ok']=row['status']==200 and row.get('response',{}).get('cluster')==row['expected_cluster'] and (not row['expected_source'] or str(ipaddress.ip_address(row.get('response',{}).get('external',{}).get('observed_source','0.0.0.0')))==str(ipaddress.ip_address(row['expected_source'])))
  with lock:
   with a.output.open('a') as f:f.write(json.dumps(row)+'\n')
  time.sleep(max(0,a.interval*(5 if control else 1)-row['duration']))
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as e:
 for af in [4,6]:
  e.submit(loop,af)
  e.submit(loop,af,True)
