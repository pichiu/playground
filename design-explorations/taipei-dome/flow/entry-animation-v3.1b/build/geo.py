import math, bisect
class Poly:
    def __init__(s, pts):
        s.p=[tuple(map(float,q)) for q in pts]; s.cum=[0.0]
        for a,b in zip(s.p,s.p[1:]): s.cum.append(s.cum[-1]+math.dist(a,b))
        s.L=s.cum[-1]
    def at(s,u):
        u=max(0,min(s.L,u)); i=max(0,min(len(s.p)-2,bisect.bisect_right(s.cum,u)-1))
        a,b=s.p[i],s.p[i+1]; seg=s.cum[i+1]-s.cum[i] or 1e-9; f=(u-s.cum[i])/seg
        return (a[0]+(b[0]-a[0])*f, a[1]+(b[1]-a[1])*f)
    def tan(s,u,h=0.15):
        a=s.at(u-h); b=s.at(u+h); d=math.dist(a,b) or 1e-9
        return ((b[0]-a[0])/d,(b[1]-a[1])/d)
    def nrm(s,u):  # left normal of direction (screen coords y down): rotate tangent
        tx,ty=s.tan(u); return (ty,-tx)
    def off(s,u,o):
        x,y=s.at(u); nx,ny=s.nrm(u); return (x+nx*o,y+ny*o)
    def proj(s,q):
        best=(1e9,0,0)
        for i,(a,b) in enumerate(zip(s.p,s.p[1:])):
            dx,dy=b[0]-a[0],b[1]-a[1]; L2=dx*dx+dy*dy or 1e-12
            f=max(0,min(1,((q[0]-a[0])*dx+(q[1]-a[1])*dy)/L2)); x=a[0]+dx*f; y=a[1]+dy*f
            dd=math.dist(q,(x,y))
            if dd<best[0]:
                u=s.cum[i]+f*math.sqrt(L2); nx,ny=s.nrm(u)
                best=(dd,u,(q[0]-x)*nx+(q[1]-y)*ny)
        return best[1],best[2],best[0]   # u, signed offset, dist
def pairs(flat): return [(flat[i],flat[i+1]) for i in range(0,len(flat),2)]
def flat(pts, nd=3): return [round(v, nd) for q in pts for v in q]
