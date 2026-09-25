#!/usr/bin/env python3
"""Render owned lab resources as JSON (valid Kubernetes YAML), without deploying."""
import argparse,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--cluster',choices=['adc-k02','adc-k04'],required=True);p.add_argument('--image',required=True);p.add_argument('--output',type=Path,required=True)
a=p.parse_args();k=a.cluster[-3:];ns='cilium-upgrade-rehearsal';items=[]
def obj(kind,name,spec=None,labels=None,annotations=None,namespace=None,api='v1',**extra):
 m={'name':name}
 if namespace:m['namespace']=namespace
 if labels:m['labels']=labels
 if annotations:m['annotations']=annotations
 x={'apiVersion':api,'kind':kind,'metadata':m,**extra}
 if spec is not None:x['spec']=spec
 items.append(x);return x
obj('Namespace',ns,annotations={'clustermesh.cilium.io/global':'false'})
obj('ConfigMap','upgrade-app',namespace=ns,data={'app.py':Path(__file__).with_name('app.py').read_text()})
for name in (['app-a','control-b'] if k=='k02' else ['app-a']):
 lab={'app':name,'lab-upgrade':'rehearsal'}
 pod={'nodeSelector':{'bgp-speaker':'true'},'affinity':{'podAntiAffinity':{'requiredDuringSchedulingIgnoredDuringExecution':[{'labelSelector':{'matchLabels':lab},'topologyKey':'kubernetes.io/hostname'}]}},'containers':[{'name':'app','image':a.image,'command':['python3','/app/app.py'],'env':[{'name':'CLUSTER','value':a.cluster},{'name':'MOCK_V4','value':'172.16.0.1'},{'name':'MOCK_V6','value':'fd21:0:0:1::101'}],'ports':[{'name':'http','containerPort':8080}],'readinessProbe':{'httpGet':{'path':'/healthz','port':'http'},'periodSeconds':3},'resources':{'requests':{'cpu':'20m','memory':'32Mi'},'limits':{'memory':'96Mi'}},'volumeMounts':[{'name':'app','mountPath':'/app','readOnly':True}]}],'volumes':[{'name':'app','configMap':{'name':'upgrade-app'}}]}
 obj('Deployment',name,{'replicas':2,'selector':{'matchLabels':lab},'template':{'metadata':{'labels':lab},'spec':pod}},namespace=ns,api='apps/v1')
 ips='172.16.14.20,fd21:0:0:14:0:0:1:100' if name=='app-a' else '172.16.14.21,fd21:0:0:14:0:0:1:101'
 labels={'lb-pool':'app' if k=='k02' else 'upgrade-rehearsal','upgrade-test':'true','handover-state':'current' if k=='k02' else 'off'}
 if name=='control-b':labels['bgp-advertise']='true'
 obj('Service',name,{'type':'LoadBalancer','loadBalancerClass':'io.cilium/bgp-control-plane','ipFamilyPolicy':'RequireDualStack','ipFamilies':['IPv4','IPv6'],'externalTrafficPolicy':'Cluster','selector':lab,'ports':[{'name':'http','port':80,'targetPort':'http'}]},labels=labels,annotations={'lbipam.cilium.io/ips':ips,'service.cilium.io/global':'false','service.cilium.io/shared':'false'},namespace=ns)
if k=='k04':obj('CiliumLoadBalancerIPPool','upgrade-rehearsal',{'blocks':[{'start':'172.16.14.20','stop':'172.16.14.20'},{'start':'fd21:0:0:14:0:0:1:100','stop':'fd21:0:0:14:0:0:1:100'}],'serviceSelector':{'matchLabels':{'lb-pool':'upgrade-rehearsal'}}},api='cilium.io/v2')
for state,rank in [('candidate',100),('current',200),('preferred',300)]:
 obj('CiliumBGPAdvertisement','upgrade-rehearsal-'+state,{'advertisements':[{'advertisementType':'Service','service':{'addresses':['LoadBalancerIP']},'selector':{'matchLabels':{'upgrade-test':'true','handover-state':state,'io.kubernetes.service.namespace':ns,'io.kubernetes.service.name':'app-a'}},'attributes':{'communities':{'standard':['65010:'+str(rank)]}}}]},labels={'advertise':k},api='cilium.io/v2')
a.output.write_text(json.dumps({'apiVersion':'v1','kind':'List','items':items},indent=2)+'\n')
