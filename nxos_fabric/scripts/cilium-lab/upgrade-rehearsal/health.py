#!/usr/bin/env python3
"""Read-only post-restore checks, with raw output restricted to operation dir."""
import argparse,concurrent.futures,datetime,json,subprocess,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--op',type=Path,required=True);a=p.parse_args();out=[]
def run(cmd):return subprocess.run(cmd,capture_output=True,text=True,timeout=150)
for c in ['adc-k02','bdc-k03','adc-k04']:
 for label,args in [('status',['status']),('mesh',['clustermesh','status']),('bgp',['bgp','peers'])]:
  r=run(['cilium',*args,'--context','kind-'+c]);(a.op/(c+'-final-'+label+'.txt')).write_text(r.stdout+r.stderr)
  row={'cluster':c,'check':label,'ok':r.returncode==0}
  if label=='bgp':row['established']=r.stdout.lower().count('established');row['ok']=row['ok'] and row['established']==8
  out.append(row);print(row,flush=True)
 jobs=[]
 pods=json.loads(subprocess.check_output(['kubectl','--context','kind-'+c,'-n','kube-system','get','pods','-l','k8s-app=cilium','-o','json'],text=True))['items']
 def probe(pod):
  node=pod['spec']['nodeName'];r=run(['kubectl','--context','kind-'+c,'-n','kube-system','exec',pod['metadata']['name'],'--','cilium-health','status','-o','json'])
  (a.op/(node+'-final-health.json')).write_text(r.stdout);(a.op/(node+'-final-health.stderr')).write_text(r.stderr);checks=[]
  if r.returncode==0:
   for n in (json.loads(r.stdout).get('nodes') or []):
    for typ in ['host','health-endpoint']:
     ob=n.get(typ) or {}
     for addr in [ob.get('primary-address') or {},*(ob.get('secondary-addresses') or [])]:
      for protocol in ['icmp','http']:
       q=addr.get(protocol) or {}
       checks.append(bool(q.get('lastProbed')) and not q.get('status'))
  row={'cluster':c,'node':node,'check':'health','ok':len(checks)==72 and all(checks),'passed':sum(checks),'total':len(checks)}
  return row
 deadline=time.monotonic()+600;attempt=0
 while True:
  attempt+=1
  with concurrent.futures.ThreadPoolExecutor(max_workers=2) as e:results=list(e.map(probe,pods))
  (a.op/(c+'-health-attempt-'+str(attempt)+'.json')).write_text(json.dumps(results,indent=2))
  print(c,'health attempt',attempt,'passed',sum(r['passed'] for r in results),'/',sum(r['total'] for r in results),flush=True)
  if all(r['ok'] for r in results) or time.monotonic()>=deadline:break
  time.sleep(20)
 for row in results:out.append(row);print(row,flush=True)
before=json.loads((a.op/'adc-k04-before-services.json').read_text())
svc=next(x for x in before['items'] if x['metadata']['namespace']=='cilium-k04-preflight' and x['metadata']['name']=='k04-preflight')
port=svc['spec']['ports'][0]['nodePort']
for site in ['adc-t1sv0101','bdc-t1sv0104']:
 for host in ['172.16.6.21','172.16.6.22','[fd21:0:0:6::2:1]','[fd21:0:0:6::2:2]']:
  r=run(['docker','exec','clab-nxos-fabric-multisite-'+site,'curl','--noproxy','*','-fsS','--connect-timeout','10','--max-time','30','http://'+host+':'+str(port)+'/'])
  row={'check':'existing k04 NodePort','site':site,'host':host,'ok':r.returncode==0 and 'cluster=adc-k04' in r.stdout,'response':r.stdout,'error':r.stderr}
  out.append(row);print({k:v for k,v in row.items() if k not in ['response','error']},flush=True)
(a.op/'final-health-summary.json').write_text(json.dumps({'time':datetime.datetime.now().isoformat(),'checks':out},indent=2))
raise SystemExit(0 if all(r['ok'] for r in out) else 1)
