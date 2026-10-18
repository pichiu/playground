// 五個探索方向共用的最小引擎：資料只讀、依時間戳折線內插，不重新規劃動線。
// 各頁只決定「畫什麼、用什麼顏色」，投影與內插都在這裡。
(function(){
'use strict';
const D=window.DATA, P=D.persons, T_END=D.meta.tEnd;
const byId=new Map(P.map(p=>[p.id,p]));
const pairs=f=>Array.from({length:f.length/2},(_,i)=>[f[i*2],f[i*2+1]]);

function pos(p,t){const a=p.path;if(t<=a[0][2])return a[0];if(t>=a[a.length-1][2])return a[a.length-1];let lo=0,hi=a.length-1;while(hi-lo>1){const m=(lo+hi)>>1;if(a[m][2]<=t)lo=m;else hi=m;}const u=a[lo],v=a[hi],f=(t-u[2])/(v[2]-u[2]||1);return [u[0]+(v[0]-u[0])*f,u[1]+(v[1]-u[1])*f];}
// seated → walk(去集結) → wait(集結等待) → enter(進場中) → done
function state(p,t){const s=p.t;if(t<s.leave)return 'seated';if(t<s.assembly)return 'walk';if(t<s.enter)return 'wait';if(t<s.arrive)return 'enter';return 'done';}
function counts(t,list=P){const c={seated:0,walk:0,wait:0,enter:0,done:0};for(const p of list)c[state(p,t)]++;return c;}
function bounds(pts,pad=.6){let a=1e9,b=1e9,c=-1e9,d=-1e9;for(const [x,y] of pts){if(x<a)a=x;if(y<b)b=y;if(x>c)c=x;if(y>d)d=y;}return [a-pad,b-pad,c+pad,d+pad];}
const B={
  all:bounds([...pairs(D.map.wall),...D.map.stands.flatMap(s=>pairs(s.poly))],.4),
  field:bounds(P.map(p=>[p.field.X,p.field.Y])),
  west:bounds([...D.map.stands.flatMap(s=>pairs(s.poly)),...pairs(D.map.b2Corridor),...P.map(p=>[p.field.X,p.field.Y])],.5),
};
function fmt(v){v=Math.max(0,v);return String(Math.floor(v/60)).padStart(2,'0')+':'+String(Math.floor(v%60)).padStart(2,'0');}

// 投影：rotate=true 時順時針轉 90°，與 app《我的走位》同向（甲舞台朝上）。
class View{
  constructor(canvas,{rotate=false,pad=16}={}){this.c=canvas;this.ctx=canvas.getContext('2d');this.rotate=rotate;this.pad=pad;this.b=B.all;this.cam=null;this.resize();new ResizeObserver(()=>{this.resize();this.onresize&&this.onresize();}).observe(canvas);}
  resize(){const r=this.c.getBoundingClientRect();this.w=r.width;this.h=r.height;this.dpr=Math.min(2,devicePixelRatio||1);this.c.width=Math.round(this.w*this.dpr);this.c.height=Math.round(this.h*this.dpr);this.fit(this.b,true);}
  rot(x,y){return this.rotate?[-y,x]:[x,y];}
  fit(b,now=false){const cs=[[b[0],b[1]],[b[2],b[1]],[b[0],b[3]],[b[2],b[3]]].map(([x,y])=>this.rot(x,y)),r=bounds(cs,0);const s=Math.min((this.w-this.pad*2)/(r[2]-r[0]),(this.h-this.pad*2)/(r[3]-r[1]));const to={s,cx:(r[0]+r[2])/2,cy:(r[1]+r[3])/2};this.b=b;if(now||!this.s){Object.assign(this,to);this.cam=null;}else this.cam={from:{s:this.s,cx:this.cx,cy:this.cy},to,t0:performance.now()};}
  step(now){if(!this.cam)return false;const k=Math.min(1,(now-this.cam.t0)/650),e=1-Math.pow(1-k,4);for(const n of ['s','cx','cy'])this[n]=this.cam.from[n]+(this.cam.to[n]-this.cam.from[n])*e;if(k===1)this.cam=null;return true;}
  p(x,y){const [u,v]=this.rot(x,y);return [(u-this.cx)*this.s+this.w/2,(v-this.cy)*this.s+this.h/2];}
  begin(bg){const c=this.ctx;c.setTransform(this.dpr,0,0,this.dpr,0,0);if(bg){c.fillStyle=bg;c.fillRect(0,0,this.w,this.h);}else c.clearRect(0,0,this.w,this.h);return c;}
  path(flat,close=false){const c=this.ctx;c.beginPath();for(let i=0;i<flat.length;i+=2){const q=this.p(flat[i],flat[i+1]);i?c.lineTo(q[0],q[1]):c.moveTo(q[0],q[1]);}if(close)c.closePath();}
  stroke(flat,color,lw=1,dash=[],close=false){const c=this.ctx;this.path(flat,close);c.setLineDash(dash);c.strokeStyle=color;c.lineWidth=lw;c.stroke();c.setLineDash([]);}
  fill(flat,color,alpha=1){const c=this.ctx;this.path(flat,true);c.globalAlpha=alpha;c.fillStyle=color;c.fill();c.globalAlpha=1;}
  dot(x,y,r,fill,stroke,lw=1){const c=this.ctx,q=this.p(x,y);c.beginPath();c.arc(q[0],q[1],r,0,7);if(fill){c.fillStyle=fill;c.fill();}if(stroke){c.strokeStyle=stroke;c.lineWidth=lw;c.stroke();}}
  text(s,x,y,{color='#000',size=12,weight=500,align='center',base='middle',font='"Noto Sans TC",system-ui,sans-serif',halo=null,dx=0,dy=0}={}){const c=this.ctx,q=this.p(x,y);c.font=`${weight} ${size}px ${font}`;c.textAlign=align;c.textBaseline=base;if(halo){c.lineWidth=3.5;c.strokeStyle=halo;c.lineJoin='round';c.strokeText(s,q[0]+dx,q[1]+dy);}c.fillStyle=color;c.fillText(s,q[0]+dx,q[1]+dy);}
  // 場地底圖：pal 指定各層顏色，未給的層不畫。
  base(pal){const m=D.map;
    if(pal.floor)this.fill(m.base.field[0],pal.floor,pal.floorA??1);
    if(pal.fieldLine)for(const l of m.base.field)this.stroke(l,pal.fieldLine,.8);
    if(pal.stage)for(const l of m.base.stage)this.stroke(l,pal.stage,.6);
    if(pal.wall)this.stroke(m.wall,pal.wall,pal.wallW||1.2,[],true);
    if(pal.band){for(const b of [m.b1Band,m.b2Band,m.stairBand])this.fill(b,pal.band,pal.bandA??.18);for(const b of [m.walkBand,m.laneBand])this.fill(b,pal.lane||pal.band,pal.laneA??.14);}
    if(pal.corridor){this.stroke(m.b1Corridor,pal.corridor,1,[3,3]);this.stroke(m.b2Corridor,pal.corridor,1,[3,3]);this.stroke(m.stair,pal.corridor,2);}
    if(pal.stand)for(const s of m.stands)this.stroke(s.poly,pal.stand,.8,[],true),pal.standFill&&this.fill(s.poly,pal.standFill,pal.standFillA??1);
    if(pal.gate)this.stroke(m.gateIn,pal.gate,Math.max(3,.3*this.s));
    if(pal.pillar)for(const p of m.pillars)this.dot(p.X,p.Y,Math.max(1.2,p.r*this.s*.6),pal.pillar);
  }
}
window.Dome={D,P,T_END,byId,pos,state,counts,bounds,B,fmt,View,pairs};
})();
