import re, json
from xml.etree import ElementTree as ET
NS={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
def col2n(c):
    n=0
    for ch in c: n=n*26+ord(ch)-64
    return n
def n2col(n):
    s=''
    while n: n,r=divmod(n-1,26); s=chr(65+r)+s
    return s
def load(u, sheet='sheet8.xml'):
    ss=ET.parse(f'{u}/xl/sharedStrings.xml').getroot()
    strs=[''.join(t.text or '' for t in si.iter('{%s}t'%NS['m'])) for si in ss.findall('m:si',NS)]
    sh=ET.parse(f'{u}/xl/worksheets/{sheet}').getroot()
    cells={}
    for c in sh.iter('{%s}c'%NS['m']):
        r=c.get('r'); t=c.get('t'); s=int(c.get('s') or 0)
        v=None
        if t=='inlineStr': v=''.join(x.text or '' for x in c.iter('{%s}t'%NS['m']))
        else:
            ve=c.find('m:v',NS)
            if ve is not None: v=strs[int(ve.text)] if t=='s' else ve.text
        m=re.match(r'([A-Z]+)(\d+)',r); cells[(int(m.group(2)),col2n(m.group(1)))]=(v,s)
    return cells
def seatmap(cells):
    # section headers in row 2
    heads=sorted((c,v) for (r,c),(v,s) in cells.items() if r==2 and v and re.match(r'\d{3}',v))
    out={}
    for i,(hc,hv) in enumerate(heads):
        sec=hv[:3]; lo=hc-1; hi=(heads[i+1][0]-2) if i+1<len(heads) else 999
        for (r,c),(v,s) in cells.items():
            if lo<=c<=hi and r>=5 and v is not None and re.fullmatch(r'\d+',str(v).split('.')[0]) and c!=lo:
                lab=None
                for cc in range(c,lo-1,-1):
                    x=cells.get((r,cc))
                    if x and x[0] and str(x[0]).endswith('排'): lab=x[0];break
                if lab is None: continue
                pai=int(lab[:-1]); no=int(float(v))
                if (sec,pai,no) in out: continue
                below=cells.get((r+1,c))
                out[(sec,pai,no)]=dict(r=r+1,c=c,who=below[0] if below else None,s=below[1] if below else None)
    return out
