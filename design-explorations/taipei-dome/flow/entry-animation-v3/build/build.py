"""版本 3 排程：一個時鐘（樓梯口兩路、大隊交界對齊），拉式倒推離座時刻（spec §3.4），輸出 data.json 與 seats.csv。

用法: python3 build.py base.json plan.json ../data.json ../seats.csv [--no-avoid]
"""
import collections
import csv
import json
import math
import sys

import plan
import routes

V = 1.1                 # 單位/秒
HEADWAY = 0.4           # 同一路相鄰兩人節拍
STAGGER = 0.17          # 兩路錯開
T0 = 6.73               # 第一人離座
STAND_MIN = 0.6         # 沿用 2c 常數（版本 3 沒有站定）
DADUI_GAP = 0.8         # 大隊交界的對齊空檔：前一大隊隊尾先過西一入口線的轉入點
SHIFT_STEP, SHIFT_MAX, AVOID_ROUNDS = 0.05, 0.15, 60
ENTRY_HEADWAY = 0.4     # 西一入口每條線相鄰兩人：門前集合一部分人後，大隊以這個節奏連續進場
LANE_K = {'A': 0, 'B': 1}
DIRECT_LABEL = '門前集合（B2）'


def cum(pts):
    out = [0.0]
    for a, b in zip(pts, pts[1:]):
        out.append(out[-1] + math.dist(a, b))
    return out


def timed(pts, t0):
    out = [(pts[0][0], pts[0][1], t0)]
    t = t0
    for a, b in zip(pts, pts[1:]):
        dd = math.dist(a, b)
        if dd < 1e-9:
            continue
        t += dd / V
        out.append((b[0], b[1], t))
    return out


def prepare(G, people):
    """每人的路線與距離（不含時間）：to 從座位到門前集合位置（d_top 是其中到樓梯口的路程），dep 從門前位置到西一入口收攏點。"""
    R = {}
    for p in people:
        to, dep = G.queue_routes(p)
        cto = cum(to)
        k = G.stair_top_index(to)
        R[p['id']] = dict(to=to, dep=dep, L_to=cto[-1], d_top=cto[k], k_top=k, L_dep=cum(dep)[-1])
    return R


def aligned_clock(items, key_lane, key_seq, key_group, stagger_of, group_gap=0.0):
    """連續時鐘，各路在「群」（大隊）交界對齊：群 g 在所有路同時起拍 = 各路上一群最後一拍（含錯開）的最大值 + HEADWAY + group_gap。
    回傳相對時刻（第一群第一拍 = 0）與各群起拍時刻。"""
    lanes = sorted({it[key_lane] for it in items})
    groups = sorted({it[key_group] for it in items})
    by = collections.defaultdict(list)
    for it in items:
        by[(it[key_group], it[key_lane])].append(it)
    rel, t_group, prev_end = {}, {}, None
    for g in groups:
        t0 = 0.0 if prev_end is None else prev_end + HEADWAY + group_gap
        t_group[g] = t0
        ends = []
        for L in lanes:
            ps = sorted(by.get((g, L), []), key=lambda it: it[key_seq])
            for n, it in enumerate(ps):
                rel[it['id']] = t0 + HEADWAY * n + stagger_of(it)
            if ps:
                ends.append(t0 + HEADWAY * (len(ps) - 1) + stagger_of(ps[-1]))
        prev_end = max(ends)
    return rel, t_group


def schedule(G, people, R=None, shift=None):
    """兩個時鐘（spec §3.4、§3.4c）：
    1. 樓梯口時刻 S（兩路、大隊交界對齊）；離座 = S − 到樓梯口路程/V；到門前位置 = S + 樓梯口到門前位置路程/V。
    2. 西一入口時刻：大隊 k 第 j 條線第 n 位 G = T_k + ENTRY_HEADWAY·n + STAGGER·j；T_k 取讓每個人都來得及（G ≥ 一路走到底的時刻）
       且不早於前一大隊最後一拍 + HEADWAY + DADUI_GAP 的最小值——大約大隊三分之二的人到門前才出發，最後幾位邊到邊走。
    shift：個人整條時間線的平移秒數（避撞用）。"""
    R = R or prepare(G, people)
    shift = shift or {}
    rel, t_dadui = aligned_clock(people, 'lane', 'dadIdx', 'dadui', lambda it: STAGGER * LANE_K[it['lane']], group_gap=DADUI_GAP)
    T_S0 = max(T0 + R[p['id']]['d_top'] / V - rel[p['id']] for p in people)
    stair = {p['id']: T_S0 + rel[p['id']] for p in people}
    arrive_q = {p['id']: stair[p['id']] + (R[p['id']]['L_to'] - R[p['id']]['d_top']) / V for p in people}
    g_rel = {p['id']: ENTRY_HEADWAY * p['slot'] + STAGGER * p['gateLane'] for p in people}
    T_gate, prev_end = {}, None
    for d in sorted({p['dadui'] for p in people}):
        ps = [p for p in people if p['dadui'] == d]
        T = max(arrive_q[p['id']] + R[p['id']]['L_dep'] / V - g_rel[p['id']] for p in ps)
        if prev_end is not None:
            T = max(T, prev_end + HEADWAY + DADUI_GAP)
        T_gate[d] = T
        prev_end = max(T + g_rel[p['id']] for p in ps)
    out = {}
    for p in people:
        r, pid = R[p['id']], p['id']
        g = T_gate[p['dadui']] + g_rel[pid]
        out[pid] = dict(leave=stair[pid] - r['d_top'] / V, stair=stair[pid], assembly=arrive_q[pid], enter=g - r['L_dep'] / V, gate=g)
    for pid, dt in shift.items():
        for key in out[pid]:
            out[pid][key] += dt
    return out, dict(tStairStart=T_S0, tGateStart=min(v['gate'] for v in out.values()),
                     tDadui={k: round(v, 3) for k, v in T_gate.items()})


def person_path(base_person, r, t):
    """座位 → 門前集合位置（等速）→ 站著等 → 收攏點 → 場內（等速）；場內沿版本 1 幾何重計時。"""
    path = list(timed(r['to'], t['leave']))
    path.append((path[-1][0], path[-1][1], t['enter']))
    path += timed(r['dep'], t['enter'])[1:]
    post = [q for q in base_person['path'] if q[2] > base_person['t']['gate'] + 1e-6]
    tt, last = path[-1][2], path[-1]
    for x, y, _ in post:
        tt += math.dist((last[0], last[1]), (x, y)) / V
        path.append((x, y, tt))
        last = (x, y)
    rounded = [[round(x, 3), round(y, 3), round(z, 3)] for x, y, z in path]
    clean = [rounded[0]]
    for q in rounded[1:]:
        if q[:2] == clean[-1][:2] and q[2] - clean[-1][2] < 0.01:   # 沒等（或等不到 0.01 秒）就不留停留點
            continue
        clean.append(q)
    return clean


def _ids_between(persons, L, i0, i1):
    return [q['id'] for q in sorted((q for q in persons if q['lane'] == L and i0 <= q['laneIdx'] <= i1), key=lambda q: q['laneIdx'])]


def assemble(base, planj, G, R, sched, clocks, checks=None):
    who = {p['id']: p for p in base['persons']}
    people = planj['people']
    persons = []
    for p in people:
        r, t = R[p['id']], sched[p['id']]
        path = person_path(who[p['id']], r, t)
        tt = dict(leave=round(t['leave'], 3), stair=round(t['stair'], 3), assembly=round(t['assembly'], 3), enter=round(t['enter'], 3),
                  gate=round(t['gate'], 3), arrive=path[-1][2])
        persons.append(dict(id=p['id'], lie=p['lie'], pai=p['pai'], dadui=p['dadui'], costume=p['costume'], a=p['a'],
                            field=p['field'], rest=p['rest'], exit=p['exit'], exitSeq=p['exitSeq'], lane=p['lane'],
                            laneIdx=p['laneIdx'], gateLane=p['gateLane'], gateIdx=p['gateIdx'], slot=p['slot'],
                            assembly='DOOR', t=tt, path=path))
    P = {p['id']: p for p in persons}
    t_end = max(p['t']['arrive'] for p in persons)
    t_gate0 = min(p['t']['gate'] for p in persons)
    # exits：每段 = 某一路連續從這個出口出來的一串人
    exits = []
    for key in plan.EXITS:
        e = dict(planj['exits'][key])
        e['key'] = key
        e['entryU'] = round(G.B1.proj(tuple(e['entry']))[0], 3)
        segs = []
        for L in plan.LANES:
            for s in planj['lanes'][L]['segments']:
                if s['exit'] != key:
                    continue
                ids = _ids_between(persons, L, s['fromIdx'], s['toIdx'])
                segs.append(dict(lane=L, n=len(ids), firstId=ids[0], lastId=ids[-1], fromRow=P[ids[0]]['rest']['pai'], toRow=P[ids[-1]]['rest']['pai'],
                                 tFirstLeave=P[ids[0]]['t']['leave'], tLastLeave=P[ids[-1]]['t']['leave'], **{'from': s['from'], 'to': s['to']}))
        segs.sort(key=lambda s: s['tFirstLeave'])
        e['segments'] = segs
        exits.append(e)
    # groups：18 個（大隊 1 白、大隊 1 藍、…）
    groups = []
    for g in planj['groups']:
        members = [p for p in persons if p['costume'] == g['costume'] and p['dadui'] == g['dadui']]
        stair_t = [p['t']['stair'] for p in members]
        groups.append(dict(g, tStairFirst=min(stair_t), tStairLast=max(stair_t),
                           tGateFirst=min(p['t']['gate'] for p in members), tGateLast=max(p['t']['gate'] for p in members),
                           tAssembly=max(p['t']['assembly'] for p in members), tLeave=min(p['t']['leave'] for p in members), tEnter=min(p['t']['enter'] for p in members),
                           tArrive=max(p['t']['arrive'] for p in members)))
    # files（54 列）
    files = []
    for lie in range(1, 55):
        ps = sorted((p for p in persons if p['lie'] == lie), key=lambda p: p['gateIdx'])
        ex = []
        for p in sorted(ps, key=lambda p: p['laneIdx']):
            if p['exit'] not in ex:
                ex.append(p['exit'])
        files.append(dict(lie=lie, dadui=ps[0]['dadui'], costume=ps[0]['costume'], n=len(ps), lane=ps[0]['lane'], exits=ex,
                          assembly='DOOR', order=[p['id'] for p in ps],
                          tLeave=min(p['t']['leave'] for p in ps), tAssembly=max(p['t']['assembly'] for p in ps),
                          tEnter=min(p['t']['enter'] for p in ps), tGate=min(p['t']['gate'] for p in ps), tArrive=max(p['t']['arrive'] for p in ps)))
    # nodes：沒有集結區
    nodes = {}
    for k, n in base['nodes'].items():
        if k[0] == 'P' and k[1:].isdigit():
            continue
        n = dict(n)
        if k in ('STAIR_TOP', 'STAIR_BOT'):                     # 樓梯直段的頂與底（L 形轉角）
            q = G.STAIR_PTS[0 if k == 'STAIR_TOP' else 1]
            n['X'], n['Y'] = round(q[0], 3), round(q[1], 3)
        if k == 'GATE6':
            n['label'] = routes.GATE_LABEL
        if k == 'GATE6_IN':
            n['label'] = '西一入口(場內)'
        nodes[k] = n
    who_seat = {(p['rest']['sec'], p['rest']['pai'], p['rest']['no']): p['id'] for p in persons}
    rest = [dict(s, who=who_seat.get((s['sec'], s['pai'], s['no']))) for s in base['restSeats']]
    meta = dict(title='入經藏 西一＋桃竹 休息區→進場 動線資料（版本 3 兩路直進）', built='2026-10-22',
                mPerUnit=base['meta']['mPerUnit'], frame=base['meta']['frame'], population=len(persons), tEnd=t_end,
                speedUnitPerSec=V, headway=HEADWAY, laneStagger=STAGGER, t0=T0, daduiGap=DADUI_GAP,
                tStairStart=round(clocks['tStairStart'], 3), tGateStart=round(t_gate0, 3),
                rules=RULES, assumptions=ASSUMPTIONS, checks=checks or {})
    t_go = min(p['t']['enter'] for p in persons)
    phases = [dict(key='seated', label='休息區就座', t0=0, t1=T0),
              dict(key='descend', label='大隊 1 白藍兩路離座、下樓梯，在門前集合', t0=T0, t1=t_go),
              dict(key='enter', label='大隊 1→9 依序：門前集合約三分之二後六路進場（0.4 秒一位）；樓梯不停', t0=t_go, t1=t_end)]
    return dict(meta=meta, phases=phases, nodes=nodes, map=dict(base['map'], **G.stair_map(), gate=G.gate_map(), gateLanes=G.gate_lanes_map()), restSeats=rest, exits=exits,
                lanes=planj['lanes'], groups=groups, files=files, persons=persons, others=base['others'], stairSlots={}, zones={})


RULES = [
    '兩路：A 路白衣靠看台側、B 路藍衣外側（B1 走廊、樓梯、B2 都一樣）；大隊 1→9 依序，兩路同時走',
    '每一路三列交錯排隊：每列排大的先，三列輪流各出一人（白衣列 6k−5→6k−4→6k−3，藍衣列 6k−2→6k−1→6k），排完的列跳過',
    '出口：白衣依序用 139 → 140 → 141 → 142，藍衣用 142 → 143 → 144 → 145；出口坐滿才換下一個，換口可以落在大隊中間',
    '142 兩路共用：藍衣大隊 1–3 先從上排出，白衣大隊 9 最後從下排出；任何時刻白衣用的出口都比藍衣近、且在不同階梯，所以走廊上不交叉',
    '每個出口是一條隊伍：由上排往下、每排由出口側往中央，先走的坐上面',
    '不在 B2 集結區、不在樓梯或走廊候隊：下樓後白衣散到北三條線、藍衣散到南三條線，在西一入口前六條線切齊排隊；每個大隊約三分之二的人到齊就六路一起進場，每條線 0.4 秒一位、六條線錯開 0.17 秒，最後幾位邊到邊走跟上；之後沿原場內路徑',
]
ASSUMPTIONS = [
    '1 單位 ≈ 7.6 m；步速 1.1 單位/秒；同一路相鄰兩人 0.4 秒、兩路錯開 0.17 秒、大隊交界加 0.8 秒；皆為動畫節奏，不是現場秒數',
    '座位、看台幾何、走道口、西一入口與場內路徑沿用版本 1 的示意圖面；139 的 1–5 號不用',
    '樓梯照企劃圖 6白 的綠色 L 形：直段是樓梯（順著 B1 走廊往南直下），橫段是樓梯下的 B2 平台；西一入口 4 扇門、可 12 人並排；長度與寬度為示意',
    '碰撞檢查為圖面點距（0.03 單位），不是人體寬度或通道容量認證',
    '門前集合是唯一的緩衝：門前之前任何一人延誤，後面整路跟著延誤',
]


def write_seats_csv(data, path):
    cols = ['位置編碼', '衣色', '大隊', '演繹列', '演繹位置', '休息區', '休息排', '座號', '出口', '出口帶隊序',
            '樓梯路', '樓梯序號', '欄內順序', '集結區', '西一入口路', '西一入口序號']
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(cols)
        for p in sorted(data['persons'], key=lambda p: (p['lie'], p['pai'])):
            w.writerow([p['id'], p['costume'], p['dadui'], p['lie'], p['pai'], p['rest']['sec'], p['rest']['pai'], p['rest']['no'],
                        p['exit'], p['exitSeq'] + 1, p['lane'], p['laneIdx'] + 1, p['slot'] + 1, DIRECT_LABEL,
                        p['gateLane'] + 1, p['gateIdx'] + 1])


def avoid(base, planj, G, R, sched, clocks):
    """碰撞避讓（spec §3.6）：每輪對每對碰撞，把西一入口較晚的那位整條時間線延後 SHIFT_STEP，同一人累計不超過 SHIFT_MAX。"""
    from collide import collisions
    people = planj['people']
    shift = collections.defaultdict(float)
    for rnd in range(AVOID_ROUNDS):
        data = assemble(base, planj, G, R, sched, clocks)
        st, wk = collisions(data['persons'], data['meta']['tEnd'])
        print('  避撞第', rnd, '輪：穿過站定者', len(st), '互撞', len(wk), file=sys.stderr)
        if not st and not wk:
            return sched, clocks, []
        P = {p['id']: p for p in data['persons']}
        later = set()
        for (a, b) in wk:
            later.add(a if P[a]['t']['gate'] > P[b]['t']['gate'] else b)
        for a in st:
            later.add(a)
        moved = False
        for pid in later:
            if shift[pid] + SHIFT_STEP <= SHIFT_MAX + 1e-9:
                shift[pid] += SHIFT_STEP
                moved = True
        if not moved:
            break
        sched, clocks = schedule(G, people, R, shift)
    data = assemble(base, planj, G, R, sched, clocks)
    st, wk = collisions(data['persons'], data['meta']['tEnd'])
    unresolved = [dict(kind='standing', who=[k, v[1]], t=v[0]) for k, v in st.items()]
    unresolved += [dict(kind='walking', who=list(k), t=t) for k, t in wk.items()]
    return sched, clocks, unresolved


def main(argv):
    args = [a for a in argv if not a.startswith('--')]
    no_avoid = '--no-avoid' in argv
    if len(args) != 4:
        raise SystemExit(__doc__)
    base_path, plan_path, out_path, csv_path = args
    base = json.load(open(base_path, encoding='utf-8'))
    planj = json.load(open(plan_path, encoding='utf-8'))
    G = routes.Geometry(base)
    people = planj['people']
    R = prepare(G, people)
    sched, clocks = schedule(G, people, R)
    unresolved = []
    if not no_avoid:
        sched, clocks, unresolved = avoid(base, planj, G, R, sched, clocks)
    data = assemble(base, planj, G, R, sched, clocks)
    if not no_avoid:
        import check
        data['meta']['checks'] = check.check_all(data)
        if unresolved:
            data['meta']['checks']['collisions']['unresolved'] = unresolved
            data['meta']['checks']['ok'] = False
    json.dump(data, open(out_path, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    write_seats_csv(data, csv_path)
    print('全長', data['meta']['tEnd'], '秒；樓梯時鐘起點', data['meta']['tStairStart'], '；第一位過西一入口', data['meta']['tGateStart'],
          '；檢核', '通過' if data['meta']['checks'].get('ok') else ('未跑' if no_avoid else '未通過'))


if __name__ == '__main__':
    main(sys.argv[1:])
