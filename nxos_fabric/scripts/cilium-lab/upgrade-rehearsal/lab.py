#!/usr/bin/env python3
"""Explicit, independently callable steps for the k02/k04 lab rehearsal.
Requires Docker/kubectl/NX-API access. Never saves startup-config.
"""
import argparse,base64,concurrent.futures,ipaddress,json,os,ssl,subprocess,time,urllib.request
from pathlib import Path
D=Path(__file__).resolve().parent
NS='cilium-upgrade-rehearsal'
CLUSTERS=['adc-k02','adc-k04']
IMAGE='docker.io/library/python:3.13-alpine@sha256:79e7a9b9ff1cbceff819f856fb374477792a5967759d94df266de7b7b4120e6f'
RESOURCES=['nodes','namespaces','services -A','ciliumloadbalancerippools','ciliumbgpadvertisements','ciliumbgppeerconfigs','ciliumegressgatewaypolicies','customresourcedefinitions','configmap cilium-config -n kube-system']
p=argparse.ArgumentParser();p.add_argument('--op',type=Path,required=True);p.add_argument('action',choices=['snapshot','render','apply','rank','gate','interface','policy','nexus-apply','nexus-restore','routes','cleanup','state','verify','restore-crd']);p.add_argument('--cluster',choices=CLUSTERS);p.add_argument('--value');p.add_argument('--tag',default='check');a=p.parse_args();op=a.op.resolve();op.mkdir(parents=True,exist_ok=True,mode=0o700);os.umask(0o077)
def run(cmd,check=True,**kw):
 r=subprocess.run(cmd,text=True,capture_output=True,timeout=kw.pop('timeout',120),**kw)
 if check and r.returncode:raise RuntimeError('Command failed: '+' '.join(cmd[:7])+': '+r.stderr[-2000:])
 return r

def kube(c,*args,**kw):return run(['kubectl','--context','kind-'+c,*args],**kw)
def apply(c,x):return kube(c,'apply','-f','-',input=json.dumps(x))
def nx(n,cmd,kind='cli_show_ascii'):
 d=json.loads(run(['docker','inspect','clab-nxos-fabric-multisite-'+n]).stdout)[0];env=dict(s.split('=',1) for s in d['Config']['Env'] if '=' in s)
 auth=base64.b64encode((env['USERNAME']+':'+env['PASSWORD']).encode()).decode();ip=d['NetworkSettings']['Networks']['mgmt-ext']['IPAddress']
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=ssl._create_unverified_context()))
 req=urllib.request.Request('https://'+ip+'/ins',data=json.dumps({'ins_api':{'version':'1.0','type':kind,'chunk':'0','sid':'1','input':cmd,'output_format':'json'}}).encode(),headers={'Content-Type':'application/json','Authorization':'Basic '+auth})
 rows=json.load(opener.open(req,timeout=90))['ins_api']['outputs']['output'];rows=rows if isinstance(rows,list) else [rows]
 (op/(n+'-last-nxapi.json')).write_text(json.dumps(rows,indent=2))
 for r in rows:
  if str(r.get('code'))!='200':raise RuntimeError(n+' NXAPI error: '+str(r.get('input'))+' '+str(r.get('clierror',r.get('msg'))))
 return rows

def nodeip(c,*args):return run(['docker','exec',c+'-worker','ip',*args])
def resource(kind,name,spec):return {'apiVersion':'cilium.io/v2','kind':kind,'metadata':{'name':name},'spec':spec}

if a.action=='snapshot':
 if (op/'snapshot-complete').exists():raise RuntimeError('Refuse to overwrite completed snapshot; use a new operation directory')
 for c in CLUSTERS+['bdc-k03']:
  for res in RESOURCES:
   f=op/(c+'-before-'+res.split()[0]+'.json')
   if f.exists():continue
   r=kube(c,'get',*res.split(),'-o','json',check=False)
   if r.returncode and res!='ciliumegressgatewaypolicies':raise RuntimeError(r.stderr)
   f.write_text(r.stdout if not r.returncode else json.dumps({'absent':True,'error':r.stderr}))
  for mode in [[],['--all']]:
   f=op/(c+'-before-values'+('-all' if mode else '')+'.json')
   if not f.exists():f.write_text(run(['helm','--kube-context','kind-'+c,'-n','kube-system','get','values','cilium','-o','json',*mode]).stdout)
 for n in ['adc-bgrt0101','adc-bgrt0102']:
  for typ in ['running','startup']:
   f=op/(n+'-before-'+typ+'.txt')
   if not f.exists():f.write_text(nx(n,'show '+typ+'-config')[0]['body'])
 for n in run(['docker','ps','--format','{{.Names}}']).stdout.splitlines():
  if n.startswith(('adc-k','bdc-k')):
   f=op/(n+'-before-addresses.json')
   if not f.exists():f.write_text(run(['docker','exec',n,'ip','-j','address','show']).stdout)
   for af in ['-4','-6']:
    f=op/(n+'-before-routes'+af+'.json')
    if not f.exists():f.write_text(run(['docker','exec',n,'ip',af,'-j','route','show','proto','static']).stdout)
 (op/'snapshot-complete').write_text(str(time.time()))
 print('Snapshots complete; no lab mutation')
elif a.action=='render':
 for c in CLUSTERS:
  run(['python3',str(D/'render.py'),'--cluster',c,'--image',IMAGE,'--output',str(op/(c+'-workload.json'))])
 print('Rendered resources',op)
elif a.action=='apply':
 assert a.cluster
 # Refuse if a namespace with this name was present before the test.
 before=json.loads((op/(a.cluster+'-before-namespaces.json')).read_text())
 assert not any(n['metadata']['name']==NS for n in before['items'])
 print(kube(a.cluster,'apply','-f',str(op/(a.cluster+'-workload.json'))).stdout)
elif a.action=='rank':
 assert a.cluster and a.value in ['off','candidate','current','preferred']
 print(kube(a.cluster,'-n',NS,'label','svc','app-a','handover-state='+a.value,'--overwrite').stdout)
elif a.action=='gate':
 assert a.cluster and a.value in ['on','off','status']
 pods=json.loads(kube(a.cluster,'-n',NS,'get','pods','-l','app=app-a','-o','json').stdout)['items']
 for pod in pods:
  code="import urllib.request,json; r=urllib.request.Request('http://127.0.0.1:8081/',data="+("None" if a.value=='status' else repr(json.dumps({'enabled':a.value=='on'}).encode()))+"); print(urllib.request.urlopen(r).read().decode())"
  if a.value=='off':
   code="""import urllib.request,json,time
url='http://127.0.0.1:8081/'
r=urllib.request.Request(url,data=b'{"enabled": false}')
v=json.load(urllib.request.urlopen(r,timeout=5));deadline=time.monotonic()+15
while v['active'] and time.monotonic()<deadline:
 time.sleep(.2);v=json.load(urllib.request.urlopen(url,timeout=5))
assert not v['enabled'] and v['active']==0,v
print(json.dumps(v))
"""
  print(pod['metadata']['name'],kube(a.cluster,'-n',NS,'exec',pod['metadata']['name'],'--','python3','-c',code).stdout.strip())
elif a.action=='interface':
 assert a.cluster and a.value in ['separate','same','remove']
 iface='uregress0';owner='cilium-upgrade-rehearsal';node=a.cluster+'-worker'
 before=json.loads((op/(node+'-before-addresses.json')).read_text());assert not any(d['ifname']==iface for d in before)
 current=json.loads(nodeip(a.cluster,'-j','-d','link','show').stdout);exists=next((d for d in current if d['ifname']==iface),None)
 if exists:assert exists.get('ifalias')==owner and exists.get('linkinfo',{}).get('info_kind')=='dummy'
 if a.value=='remove':
  if exists:nodeip(a.cluster,'link','del',iface)
 else:
  v='100' if a.value=='same' else ('101' if a.cluster=='adc-k02' else '104')
  ips=['172.16.24.'+v,'fd21:0:0:24::'+v]
  for n in run(['docker','ps','--format','{{.Names}}']).stdout.splitlines():
   if not n.startswith(('adc-k','bdc-k')):continue
   for d in json.loads(run(['docker','exec',n,'ip','-j','address','show']).stdout):
    for r in d.get('addr_info',[]):
     if ipaddress.ip_address(r['local']) in [ipaddress.ip_address(x) for x in ips]:assert n==node and d['ifname']==iface,(n,d['ifname'],'duplicate E')
  if not exists:
   nodeip(a.cluster,'link','add',iface,'type','dummy');nodeip(a.cluster,'link','set','dev',iface,'alias',owner)
  else:
   have=[ipaddress.ip_address(r['local']) for d in json.loads(nodeip(a.cluster,'-j','addr','show','dev',iface).stdout) for r in d.get('addr_info',[]) if r.get('scope')=='global']
   assert set(have).issubset({ipaddress.ip_address(x) for x in ips}),'Remove old interface explicitly before changing address mode'
  nodeip(a.cluster,'link','set','dev',iface,'up')
  for ip in ips:nodeip(a.cluster,'addr','replace',ip+('/128' if ':' in ip else '/32'),'dev',iface)
  time.sleep(2)
 print(node,iface,a.value)
elif a.action=='policy':
 assert a.cluster and a.value in ['separate','same','remove']
 if a.value=='remove':
  print(kube(a.cluster,'delete','ciliumegressgatewaypolicy','ureh-egress-4','ureh-egress-6','--ignore-not-found').stdout)
  print(kube(a.cluster,'delete','ciliumbgpadvertisement','ureh-egress','--ignore-not-found').stdout)
 else:
  v='100' if a.value=='same' else ('101' if a.cluster=='adc-k02' else '104')
  ad=resource('CiliumBGPAdvertisement','ureh-egress',{'advertisements':[{'advertisementType':'Interface','interface':{'name':'uregress0'}}]});ad['metadata']['labels']={'advertise':a.cluster[-3:]};apply(a.cluster,ad)
  for af,dest,ip in [(4,'172.16.0.1/32','172.16.24.'+v),(6,'fd21:0:0:1::101/128','fd21:0:0:24::'+v)]:
   pol=resource('CiliumEgressGatewayPolicy','ureh-egress-'+str(af),{'selectors':[{'podSelector':{'matchLabels':{'io.kubernetes.pod.namespace':NS,'app':'app-a'}}}],'destinationCIDRs':[dest],'egressGateway':{'nodeSelector':{'matchLabels':{'kubernetes.io/hostname':a.cluster+'-worker'}},'egressIP':ip}})
   apply(a.cluster,pol)
  print(a.cluster,'Policy',a.value)
elif a.action in ['nexus-apply','nexus-restore']:
 f=D.parents[2]/'nxos_multisite/configs/changes/cilium-upgrade-rehearsal'/('bgr-apply.cfg' if a.action=='nexus-apply' else 'bgr-restore.cfg');cmd=' ; '.join(l.strip() for l in f.read_text().splitlines() if l.strip() and not l.startswith('!'))
 for n in ['adc-bgrt0101','adc-bgrt0102']:
  before=(op/(n+'-before-running.txt')).read_text()
  assert 'UREH_' not in before
  for marker in ['route-map CILIUM_K02_IN_V4 in','route-map CILIUM_K02_IN_V6 in','route-map K04UP_BASE_V4 in','route-map K04UP_BASE_V6 in']:assert marker in before
  nx(n,cmd,'cli_conf');print(n,a.action,'OK',flush=True)
elif a.action=='routes':
 commands=['show bgp ipv4 unicast 172.16.14.20/32 vrf tenant1-vpc1','show bgp ipv6 unicast fd21:0:0:14:0:0:1:100/128 vrf tenant1-vpc1','show ip route 172.16.14.20 vrf tenant1-vpc1','show ipv6 route fd21:0:0:14:0:0:1:100 vrf tenant1-vpc1']
 if a.value in ['same','separate']:
  for v in (['100'] if a.value=='same' else ['101','104']):
   commands+=['show bgp ipv4 unicast 172.16.24.'+v+'/32 vrf tenant1-vpc1','show bgp ipv6 unicast fd21:0:0:24::'+v+'/128 vrf tenant1-vpc1']
 def collect(n):
  rows=nx(n,' ; '.join(commands));(op/(a.tag+'-'+n+'-routes.json')).write_text(json.dumps(rows,indent=2));return n+' routes saved'
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as e:
  for v in e.map(collect,['adc-bgrt0101','adc-bgrt0102']):print(v)
elif a.action=='cleanup':
 assert a.cluster
 before=json.loads((op/(a.cluster+'-before-namespaces.json')).read_text());assert not any(n['metadata']['name']==NS for n in before['items'])
 print(kube(a.cluster,'delete','namespace',NS,'--ignore-not-found','--wait=true','--timeout=90s').stdout)
 for typ,names in [('ciliumbgpadvertisement',['upgrade-rehearsal-candidate','upgrade-rehearsal-current','upgrade-rehearsal-preferred','ureh-egress']),('ciliumegressgatewaypolicy',['ureh-egress-4','ureh-egress-6'])]:
  r=kube(a.cluster,'delete',typ,*names,'--ignore-not-found',check=False)
  if r.returncode and 'doesn\'t have a resource type' not in r.stderr:raise RuntimeError(r.stderr)
 if a.cluster=='adc-k04':print(kube(a.cluster,'delete','ciliumloadbalancerippool','upgrade-rehearsal','--ignore-not-found').stdout)
elif a.action=='state':
 assert a.value
 state=json.loads(a.value);state['time']=time.time();tmp=op/'state.tmp';tmp.write_text(json.dumps(state));tmp.replace(op/'state.json')
 with (op/'events.jsonl').open('a') as f:f.write(json.dumps(state)+'\n')
 print(state)

elif a.action=='verify':
 checks=[]
 def record(name,ok):
  checks.append({'check':name,'ok':bool(ok)});print(name,bool(ok),flush=True)
 def specs(x):
  return {i['metadata']['name']:i.get('spec',{}) for i in x.get('items',[])}
 for c in CLUSTERS+['bdc-k03']:
  current=json.loads(run(['helm','--kube-context','kind-'+c,'-n','kube-system','get','values','cilium','-o','json']).stdout)
  record(c+' user values',current==json.loads((op/(c+'-before-values.json')).read_text()))
  current=json.loads(kube(c,'-n','kube-system','get','configmap','cilium-config','-o','json').stdout)
  record(c+' ConfigMap data',current['data']==json.loads((op/(c+'-before-configmap.json')).read_text())['data'])
  for res in ['ciliumloadbalancerippools','ciliumbgpadvertisements','ciliumbgppeerconfigs','ciliumegressgatewaypolicies']:
   before=json.loads((op/(c+'-before-'+res+'.json')).read_text());r=kube(c,'get',res,'-o','json',check=False)
   record(c+' '+res, bool(r.returncode) if before.get('absent') else r.returncode==0 and specs(json.loads(r.stdout))==specs(before))
  current=json.loads(kube(c,'get','nodes','-o','json').stdout)
  record(c+' all Nodes Ready',len(current['items'])==3 and all(any(q['type']=='Ready' and q['status']=='True' for q in n['status']['conditions']) for n in current['items']))
  services=json.loads(kube(c,'get','services','-A','-o','json').stdout)
  old=json.loads((op/(c+'-before-services.json')).read_text())
  norm=lambda x:{(n['metadata']['namespace'],n['metadata']['name']):n['spec'] for n in x['items']}
  record(c+' Service specs',norm(services)==norm(old))
  (op/(c+'-after-nodes.json')).write_text(json.dumps(current))
 for f in op.glob('*-before-addresses.json'):
  n=f.name.removesuffix('-before-addresses.json');current=json.loads(run(['docker','exec',n,'ip','-j','address','show']).stdout)
  norm=lambda x:{(d['ifname'],str(ipaddress.ip_address(r['local'])),r['prefixlen']) for d in x for r in d.get('addr_info',[]) if r.get('scope')=='global'}
  record(n+' global addresses',norm(current)==norm(json.loads(f.read_text())))
  record(n+' no uregress0',not any(d['ifname']=='uregress0' for d in current))
  for af in ['-4','-6']:
   froute=op/(n+'-before-routes'+af+'.json')
   if froute.exists():record(n+' static routes '+af,json.loads(run(['docker','exec',n,'ip',af,'-j','route','show','proto','static']).stdout)==json.loads(froute.read_text()))
 for n in ['adc-bgrt0101','adc-bgrt0102']:
  rows=nx(n,'show running-config ; show startup-config')
  for typ,row in zip(['running','startup'],rows):
   (op/(n+'-after-'+typ+'.txt')).write_text(row['body'])
   norm=lambda text:[l.rstrip() for l in text.splitlines() if l.strip() and not l.lstrip().startswith('!')]
   record(n+' '+typ,norm(row['body'])==norm((op/(n+'-before-'+typ+'.txt')).read_text()))
 (op/'restore-verification.json').write_text(json.dumps(checks,indent=2))
 if not all(r['ok'] for r in checks):raise SystemExit(1)

elif a.action=='restore-crd':
 assert a.cluster
 name='ciliumegressgatewaypolicies.cilium.io'
 before=json.loads((op/(a.cluster+'-before-customresourcedefinitions.json')).read_text())
 if name in {x['metadata']['name'] for x in before['items']}:
  print(a.cluster,'Egress CRD existed before; retained')
 else:
  conf=json.loads(kube(a.cluster,'-n','kube-system','get','configmap','cilium-config','-o','json').stdout)
  assert conf['data'].get('enable-egress-gateway','false')=='false'
  r=kube(a.cluster,'get','ciliumegressgatewaypolicies','-o','json',check=False)
  if r.returncode==0:
   assert not json.loads(r.stdout)['items']
   print(kube(a.cluster,'delete','crd',name).stdout)
  else:print(a.cluster,'Egress CRD already absent')
