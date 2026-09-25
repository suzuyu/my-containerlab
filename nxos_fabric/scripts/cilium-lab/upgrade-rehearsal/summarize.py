#!/usr/bin/env python3
"""Report probe results without equating a polling gap with packet loss."""
import argparse,collections,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--op',type=Path,required=True);a=p.parse_args();op=a.op
f=op/'adc-probes.jsonl';rows=[json.loads(l) for l in f.read_text().splitlines() if l.strip()] if f.exists() else []
events=[json.loads(l) for l in (op/'events.jsonl').read_text().splitlines()]
g=collections.defaultdict(list)
for r in rows:g[(r['phase'],r['af'],r['target'])].append(r)
result=[]
for (phase,af,target),v in sorted(g.items()):
 ev=next(e for e in reversed(events) if e['phase']==phase)
 good=[r for r in v if r['ok']];three=[];confirm=None
 for r in v:
  three=three+[r] if r['ok'] else []
  if len(three)==3:confirm=three[-1]['end_time']-ev['time'];break
 r={'phase':phase,'af':af,'target':target,'samples':len(v),'http_errors':sum(x['status']!=200 for x in v),'expected_mismatches':sum(x['status']==200 and not x['ok'] for x in v),'first_expected_response_s':round(good[0]['end_time']-ev['time'],3) if good else None,'three_success_confirm_s':round(confirm,3) if confirm is not None else None,'max_request_s':round(max(x['duration'] for x in v),3),'observed_span_s':round(v[-1]['end_time']-v[0]['time'],3)}
 result.append(r);print(json.dumps(r))
# Stop phase through completion of the corresponding VIP phase is a business interval.
intervals=[]
for stem in ['eb-forward','eb-rollback']:
 starts=[e for e in events if e['phase']==stem+'-stop']
 if not starts:continue
 for af in [4,6]:
  begun=starts[-1]['time']
  sequence=[r for r in rows if r['target']=='A' and r['af']==af and r['phase'] in [stem+'-stop',stem+'-vip'] and r['time']>=begun]
  good=[r for r in sequence if r['ok']]
  vip=[r for r in sequence if r['phase']==stem+'-vip'];consecutive=[];confirmed=None
  for r in vip:
   consecutive=consecutive+[r] if r['ok'] else []
   if len(consecutive)==3:confirmed=r['end_time']-begun;break
  vg=[r for r in vip if r['ok']]
  intervals.append({'step':stem,'af':af,'stop_to_first_expected_s':round(good[0]['end_time']-begun,3) if good else None,'stop_to_post_vip_first_s':round(vg[0]['end_time']-begun,3) if vg else None,'stop_to_post_vip_three_s':round(confirmed,3) if confirmed is not None else None})
for x in intervals:print(json.dumps(x))
(op/'summary.json').write_text(json.dumps({'phases':result,'business_intervals':intervals,'note':'2s polling; first success includes request time; absence of errors does not prove zero interruption. Stop intervals include manual checks.'},indent=2))
