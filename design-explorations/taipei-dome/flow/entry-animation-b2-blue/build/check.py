import json,sys,numpy as np
class cKDTree:
    def __init__(s,pts): s.a=np.array(pts)
    def query_ball_point(s,q,r):
        d=np.hypot(s.a[:,0]-q[0],s.a[:,1]-q[1]); return np.nonzero(d<r)[0]
d=json.load(open(sys.argv[1])); P=d['persons']
def pos(p,t):
    a=p['path']
    if t<=a[0][2]: return a[0][:2]
    if t>=a[-1][2]: return a[-1][:2]
    lo,hi=0,len(a)-1
    while hi-lo>1:
        m=(lo+hi)//2
        if a[m][2]<=t: lo=m
        else: hi=m
    u,v=a[lo],a[hi]; f=(t-u[2])/((v[2]-u[2]) or 1)
    return (u[0]+(v[0]-u[0])*f,u[1]+(v[1]-u[1])*f)
bad=set(); ex={}
for t in np.arange(6,d['meta']['tEnd'],0.25):
    st=[p for p in P if p['t']['assembly']<=t<p['t']['enter']-0.05]
    mv=[p for p in P if (p['t']['leave']<t<p['t']['assembly']-0.05) or (p['t']['enter']+0.05<t<p['t']['gate'])]
    if not st or not mv: continue
    tr=cKDTree([pos(p,t) for p in st])
    for p in mv:
        q=pos(p,t)
        for k in tr.query_ball_point(q,0.03):
            s=st[k]
            if s['lie']==p['lie']: continue
            bad.add(p['id']); ex.setdefault(p['id'],(round(t,1),s['id'],s['assembly'],p['assembly']))
print('穿過站定者人數',len(bad))
import collections
print(collections.Counter((v[3],v[2]) for v in ex.values()))
print(list(ex.items())[:12])
