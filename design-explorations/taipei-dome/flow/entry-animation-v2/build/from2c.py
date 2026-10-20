"""把 2c 的 data.json 轉成 v2 頁面讀得懂的 DATA，寫回 ../index.html 的 `const DATA = …;` 那一行（頁面其餘部分不動）。

用法：python3 from2c.py ../../entry-animation/data.json ../index.html
對照：2c 的「出口 × 路」→ v2 的「塊 × 鏈」
  chain ← lane（A/B/C）、block ← exit、exitWave ← 該路的第幾段出口（1–3）、exitSide ← 出口的 N/S
  walkLane／corrLane ← 路 A/B/C 的 0–2（2c 的 laneIdx 是路內序號，不是路別）、laneIdx ← 西一入口六路（2c 的 gateLane）
  qi ← 該人在 2c 檔案（列）離座順序 files[].order 的位置；wave01 沿用頁面既有值（場內編舞分組，與動線無關）
"""
import json, re, sys

src, page = sys.argv[1:3]
c = json.load(open(src, encoding='utf-8'))
h = open(page, encoding='utf-8').read()
m = re.search(r'^const DATA = (.*);$', h, re.M)
if not m:
    sys.exit(f'{page} 裡找不到 `const DATA = …;` 那一行（wave01 要從它讀回來）')
old = json.loads(m.group(1))
oldp = {p['id']: p for p in old['persons']}
oldf = {f['lie']: f for f in old['files']}
exits = {e['key']: e for e in c['exits']}
seg_no = {L: {s['exit']: i + 1 for i, s in enumerate(v['segments'])} for L, v in c['lanes'].items()}
nodes = dict(c['nodes'])
node_floor = lambda k: nodes[k]['floor']
st = nodes['STAIR_TOP']
nodes['FEEDER'] = {'X': st['X'], 'Y': st['Y'], 'theta': st.get('theta', 180), 'label': '接尾下樓', 'floor': 'B1'}  # 白4 以後不集結，直接接在隊尾

P = []
for p in c['persons']:
    q = dict(p)
    o = oldp[p['id']]
    L = p['lane']
    q['zu'] = 'B1' if p['assembly'] in ('STAIR', 'FEEDER') else node_floor(p['assembly'])
    q['wave01'] = o['wave01']
    q['chain'], q['block'] = L, p['exit']
    q['exitWave'], q['exitSide'] = seg_no[L][p['exit']], exits[p['exit']]['side']
    q['walkLane'] = q['corrLane'] = 'ABC'.index(L)
    q['laneIdx'] = p['gateLane']
    q['gate'] = 'GATE6'
    P.append(q)
byid = {p['id']: p for p in P}

F = []
for f in c['files']:
    g = {k: v for k, v in f.items() if k in ('lie', 'dadui', 'costume', 'n', 'order', 'assembly', 'tLeave', 'tAssembly', 'tEnter', 'tGate', 'tArrive')}
    g['direction'] = oldf[f['lie']]['direction']   # 離座順序的文字說明（尾→頭），2c 同樣由排大的先走
    for i, pid in enumerate(f['order']):
        byid[pid]['qi'] = i
    ps = [byid[i] for i in f['order']]
    g['zu'] = ps[0]['zu']
    g['tDaduiStart'] = g['tGate']
    blocks = []
    for p in ps:
        if not blocks or blocks[-1]['block'] != p['block']:
            e = exits[p['block']]
            blocks.append({'block': p['block'], 'chain': p['chain'], 'from': f"{p['rest']['sec']}區{p['rest']['pai']}排{p['rest']['no']}號", 'n': 0,
                           'exitWave': p['exitWave'], 'exitSide': e['side'], 'exitSideLabel': f"走 {e['stairLabel']}", 'chainIdx': p['exitWave']})
        b = blocks[-1]
        b['n'] += 1
        b['to'] = f"{p['rest']['sec']}區{p['rest']['pai']}排{p['rest']['no']}號"
    g['blocks'] = blocks
    F.append(g)

c['meta']['assumptions'] = [s.replace('沿用版本 1 的示意圖面', '沿用原始示意圖面').replace('集結區位置沿用版本 2', '集結區位置沿用企劃手繪平面圖的估計') for s in c['meta']['assumptions']]
D = {k: c[k] for k in ('meta', 'phases', 'map', 'restSeats', 'others', 'exits', 'lanes', 'groups', 'stairSlots', 'zones')}   # 後五項給 redesign/f-exit.html（出口帶隊卡）
D['nodes'] = nodes
D['persons'] = P
D['files'] = F
line = 'const DATA = ' + json.dumps(D, ensure_ascii=False, separators=(',', ':')) + ';'
h = h[:m.start()] + line + h[m.end():]
open(page, 'w', encoding='utf-8').write(h)
print('ok', len(P), 'persons')
