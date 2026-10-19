"""Exact closest approach for each overlapping pair of linear timed segments.
Includes rest seats, P1 waits, and permanent final positions; floor aware.
Radius .03 is a diagram-unit regression threshold, NOT human clearance.
"""
import json,math,collections,itertools,numpy as np,gzip,sys
from pathlib import Path
R=.03;CELL=.5
for mode,source in [('2a',Path(__file__).parent/'white-verification-tracks.json.gz'),('2b',Path(__file__).parent.parent/'entry-animation-v2b/white-verification-tracks.json.gz')]:
 D=json.load(gzip.open(source,'rt'));ss=[]
 for p in D['people']:
  for s in p['segments']:
   if s['t1']>s['t0']+1e-9:ss.append(dict(s,pid=p['id'],costume=p['costume'],dadui=p['dadui'],lie=p['lie']))
 grid=collections.defaultdict(list)
 def cells(s,pad=0):
  a,b=s['a'],s['b']
  return itertools.product(range(math.floor((min(a[0],b[0])-pad)/CELL),math.floor((max(a[0],b[0])+pad)/CELL)+1),range(math.floor((min(a[1],b[1])-pad)/CELL),math.floor((max(a[1],b[1])+pad)/CELL)+1))
 for i,s in enumerate(ss):
  for x,y in cells(s):grid[s['floor'],x,y].append(i)
 aa=np.array([s['a'] for s in ss]);bb=np.array([s['b'] for s in ss]);t0=np.array([s['t0'] for s in ss]);t1=np.array([s['t1'] for s in ss]);vv=(bb-aa)/(t1-t0)[:,None];pids=np.array([s['pid'] for s in ss]);white=np.array([s['costume']=='白' for s in ss]);moving=np.linalg.norm(bb-aa,axis=1)>1e-9
 hits={};near=collections.Counter();segpairs=0
 for i,s in enumerate(ss):
  if not moving[i]:continue
  cand=set()
  for x,y in cells(s,R):cand.update(grid.get((s['floor'],x,y),()))
  js=np.array(sorted(cand),dtype=int);js=js[(pids[js]!=pids[i]) & (t0[js]<t1[i]) & (t1[js]>t0[i]) & (white[i] | white[js]) & ((~moving[js]) | (js>i))]
  if not len(js):continue
  lo=np.maximum(t0[i],t0[js]);hi=np.minimum(t1[i],t1[js]);d0=(aa[i]+vv[i]*(lo-t0[i])[:,None])-(aa[js]+vv[js]*(lo-t0[js])[:,None]);dv=vv[i]-vv[js];den=np.sum(dv*dv,axis=1);dt=np.clip(-np.sum(d0*dv,axis=1)/np.maximum(den,1e-15),0,hi-lo);dist=np.linalg.norm(d0+dv*dt[:,None],axis=1)
  for k in np.where(dist<R-1e-8)[0]:
   j=int(js[k]);other=ss[j];segpairs+=1;key=tuple(sorted((s['pid'],other['pid'])));near[s['stage']+' × '+other['stage']]+=1
   ex=dict(first=s['pid'],second=other['pid'],firstCostume=s['costume'],secondCostume=other['costume'],firstStage=s['stage'],secondStage=other['stage'],floor=s['floor'],time=float(lo[k]+dt[k]),distance=float(dist[k]),firstSegment=[s['a'],s['b']],secondSegment=[other['a'],other['b']])
   if key not in hits or ex['distance']<hits[key]['distance']:hits[key]=ex
 result=dict(method='Exact relative-velocity minimum on every temporally overlapping pair of linear path segments. Includes stationary rest, assembly and final field positions. All moving-versus-moving or moving-versus-stationary pairs involving at least one white person, across all 1,609 people.',radiusFigureUnits=R,uniquePairs=len(hits),segmentHits=segpairs,byStage=dict(near),examples=sorted(hits.values(),key=lambda x:x['time']),caution='Diagram point separation only; no physical body widths or measured aisle boundaries.')
 Path(f'white-continuous-timing-audit-{mode}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(mode,len(hits),dict(near),flush=True)
