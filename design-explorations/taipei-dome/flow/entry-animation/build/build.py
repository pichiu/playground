"""2c 排程：兩個連續時鐘的拉式倒推（spec §3.6），輸出 data.json 與 seats.csv。

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
HEADWAY = 0.4           # 同一路相鄰兩人節拍（走廊、樓梯、西一入口皆同）
STAGGER = 0.17          # 三路／六路錯開
T0 = 6.73               # 第一人離座
STAND_MIN = 0.6         # 站定後至少這麼久才起步
DADUI_GAP = 0.8         # 西一入口大隊交界的對齊空檔：外側路到各列轉入點的路程比內側短，前一大隊隊尾要先過
SHIFT_STEP, SHIFT_MAX, AVOID_ROUNDS = 0.05, 0.15, 60
LANE_K = {'A': 0, 'B': 1, 'C': 2}
ZONE_LABEL = {'P1': '集結區 1', 'P2': '藍 2·3', 'P3': '藍 4·5', 'P4': '藍 6·7', 'P5': '藍 8·9',
              'STAIR': '樓梯（白 2）', 'P6': '白 3（B1）', 'FEEDER': '不集結，直接接尾'}


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


def slot_indices(people):
    """欄內格位序 i：同列依排大→小（排大的先過西一入口）。"""
    by_lie = collections.defaultdict(list)
    for p in people:
        by_lie[p['lie']].append(p)
    out = {}
    for lie, ps in by_lie.items():
        for i, p in enumerate(sorted(ps, key=lambda q: -q['pai'])):
            out[p['id']] = i
    return out


def prepare(G, people):
    """每人的路線與距離（不含時間）。"""
    slot_i = slot_indices(people)
    R = {}
    for p in people:
        i = slot_i[p['id']]
        arr = G.arrival_route(p, i)
        dep = G.depart_route(p, i)
        carr = cum(arr)
        k = G.stair_top_index(arr)
        if p['assembly'] == 'FEEDER':
            d_top = carr[k]
        elif k is not None:
            d_top = carr[k]
        else:                                                   # P6：格位在樓梯口之前，算到樓梯口的虛擬距離
            d_top = carr[-1] + (routes.STAIR_U_B1 - G.slot_u(p, i))
        R[p['id']] = dict(i=i, arr=arr, dep=dep, L_arr=carr[-1], d_top=d_top, k_top=k, L_dep=cum(dep)[-1] if dep else 0.0)
    return R


def aligned_clock(items, key_lane, key_seq, key_group, stagger_of, group_gap=0.0):
    """連續時鐘，但各路在「群」（區塊／大隊）交界對齊：群 b 在所有路同時起拍 = 各路上一群最後一拍的最大值 + HEADWAY。
    回傳相對時刻（第一群第一拍 = 0）。items 需含 key_lane / key_seq（路內序號）/ key_group（群序）。"""
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
                ends.append(t0 + HEADWAY * (len(ps) - 1) + stagger_of(ps[-1]))   # 含錯開量：下一群最早的一路也在這一群最晚的一路之後
        prev_end = max(ends)
    return rel, t_group


def schedule(G, people, R=None, shift=None):
    """兩個連續時鐘（區塊／大隊交界對齊），拉式倒推離座時刻。shift：個人整條時間線的平移秒數（避撞用）。"""
    R = R or prepare(G, people)
    shift = shift or {}
    staged = [p for p in people if p['assembly'] != 'FEEDER']
    feeders = [p for p in people if p['assembly'] == 'FEEDER']
    # 1. 樓梯時鐘（集結階段）：藍9…白3 各區塊三路對齊
    relS, _ = aligned_clock([dict(p, _blk=plan.BLOCKS.index(p['block'])) for p in staged],
                            'lane', 'laneIdx', '_blk', lambda it: STAGGER * LANE_K[it['lane']])
    T_S0 = max(T0 + R[p['id']]['d_top'] / V - relS[p['id']] for p in staged)
    out = {}
    for p in staged:
        r = R[p['id']]
        S = T_S0 + relS[p['id']]
        leave = S - r['d_top'] / V
        out[p['id']] = dict(leave=leave, assembly=leave + r['L_arr'] / V, stairPlan=S)
    # 2. 西一入口時鐘（進場階段）：六路在大隊交界對齊。與樓梯時鐘重疊：不等全部集結完，每人只要自己站定 STAND_MIN 就能起步，
    #    大隊 1 在藍1、白1 隊頭站定後就出發，樓梯不停、白2 以後接續下樓（不重疊時樓梯在白3 與白4 之間空 36 秒）
    relG, t_dadui = aligned_clock(people, 'gateLane', 'gateIdx', 'dadui', lambda it: STAGGER * it['gateLane'], group_gap=DADUI_GAP)
    need = []
    for p in staged:
        need.append(out[p['id']]['assembly'] + STAND_MIN + R[p['id']]['L_dep'] / V - relG[p['id']])
    for p in feeders:
        need.append(T0 + R[p['id']]['L_arr'] / V - relG[p['id']])
    T_G0 = max(need)
    for p in people:
        r = R[p['id']]
        g = T_G0 + relG[p['id']]
        if p['assembly'] == 'FEEDER':
            leave = g - r['L_arr'] / V
            top = leave + cum(r['arr'])[r['k_top']] / V
            out[p['id']] = dict(leave=leave, assembly=top, enter=top, gate=g)
        else:
            out[p['id']].update(enter=g - r['L_dep'] / V, gate=g)
    for pid, dt in shift.items():
        for key in out[pid]:
            out[pid][key] += dt
    return out, dict(tStairStart=T_S0, tGateStart=T_G0,
                     tDadui={k: round(T_G0 + v, 3) for k, v in t_dadui.items()})


def person_path(base_person, p, r, t):
    """座位 → 格位（停留）→ 西一入口 → 場內，含時間；場內沿版本 1 幾何等速重計時。"""
    arr = timed(r['arr'], t['leave'])
    if p['assembly'] == 'FEEDER':
        path = list(arr)
    else:
        path = list(arr)
        path.append((arr[-1][0], arr[-1][1], t['enter']))
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
        if q[:2] == clean[-1][:2] and abs(q[2] - clean[-1][2]) < 1e-9:
            continue
        clean.append(q)
    return clean


def assemble(base, planj, G, R, sched, clocks, checks=None):
    who = {p['id']: p for p in base['persons']}
    people = planj['people']
    persons = []
    for p in people:
        r, t = R[p['id']], sched[p['id']]
        path = person_path(who[p['id']], p, r, t)
        tt = dict(leave=round(t['leave'], 3), assembly=round(t['assembly'], 3), enter=round(t['enter'], 3),
                  gate=round(t['gate'], 3), arrive=path[-1][2])
        if 'stairPlan' in t:
            tt['stairPlan'] = round(t['stairPlan'], 3)
        persons.append(dict(id=p['id'], lie=p['lie'], pai=p['pai'], dadui=p['dadui'], costume=p['costume'], a=p['a'],
                            field=p['field'], rest=p['rest'], exit=p['exit'], exitSeq=p['exitSeq'], lane=p['lane'],
                            laneIdx=p['laneIdx'], gateLane=p['gateLane'], gateIdx=p['gateIdx'], slot=r['i'],
                            assembly=p['assembly'], t=tt, path=path))
    P = {p['id']: p for p in persons}
    t_end = max(p['t']['arrive'] for p in persons)
    staged = [p for p in persons if p['assembly'] != 'FEEDER']
    first_enter = min(p['t']['enter'] for p in staged)
    # exits
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
                ids = [q['id'] for q in sorted((q for q in persons if q['lane'] == L and s['fromIdx'] <= q['laneIdx'] <= s['toIdx']), key=lambda q: q['laneIdx'])]
                segs.append(dict(lane=L, fromBlock=s['fromBlock'], toBlock=s['toBlock'], n=len(ids), firstId=ids[0], lastId=ids[-1],
                                 fromRow=P[ids[0]]['rest']['pai'], toRow=P[ids[-1]]['rest']['pai'],
                                 tFirstLeave=P[ids[0]]['t']['leave'], tLastLeave=P[ids[-1]]['t']['leave']))
        segs.sort(key=lambda s: s['tFirstLeave'])
        e['segments'] = segs
        exits.append(e)
    # groups
    groups = []
    for b in planj['blocks']:
        members = [p for p in persons if p['costume'] == b['costume'] and p['dadui'] == b['dadui']]
        stair_t = [p['t'].get('stairPlan', p['t']['enter']) for p in members]
        groups.append(dict(b, tStairFirst=min(stair_t), tStairLast=max(stair_t),
                           tGateFirst=min(p['t']['gate'] for p in members), tGateLast=max(p['t']['gate'] for p in members),
                           tAssembly=max(p['t']['assembly'] for p in members), tLeave=min(p['t']['leave'] for p in members),
                           tEnter=min(p['t']['enter'] for p in members)))
    # files（54 列）
    files = []
    for lie in range(1, 55):
        ps = sorted((p for p in persons if p['lie'] == lie), key=lambda p: p['gateIdx'])
        files.append(dict(lie=lie, dadui=ps[0]['dadui'], costume=ps[0]['costume'], n=len(ps), lane=ps[0]['lane'], exit=ps[0]['exit'],
                          assembly=ps[0]['assembly'], order=[p['id'] for p in ps],
                          tLeave=min(p['t']['leave'] for p in ps), tAssembly=max(p['t']['assembly'] for p in ps),
                          tEnter=min(p['t']['enter'] for p in ps), tGate=min(p['t']['gate'] for p in ps), tArrive=max(p['t']['arrive'] for p in ps)))
    # nodes
    nodes = {}
    for k, n in base['nodes'].items():
        if k in ('P7', 'P8', 'P9'):
            continue
        n = dict(n)
        if k in G.ZONES:
            Z = G.ZONES[k]
            n['label'], n['floor'] = Z['label'], Z['floor']
            n['dadui'] = min(b['dadui'] for b in planj['blocks'] if b['assembly'] == k)
            if Z['kind'] == 'LIFO' or Z['corr'] == 'B1':
                x, y = (G.B1 if Z['corr'] == 'B1' else G.B2).at(Z['head'])
                n['X'], n['Y'] = round(x, 3), round(y, 3)
        if k in ('STAIR_TOP', 'STAIR_BOT'):                     # 樓梯直段的頂與底（L 形轉角）
            q = G.STAIR_PTS[0 if k == 'STAIR_TOP' else 1]
            n['X'], n['Y'] = round(q[0], 3), round(q[1], 3)
        if k == 'STAIR_TOP':
            n['label'] = '樓梯(B1) · 白 2'
        if k == 'GATE6':
            n['label'] = routes.GATE_LABEL
        if k == 'GATE6_IN':
            n['label'] = '西一入口(場內)'
        nodes[k] = n
    who_seat = {(p['rest']['sec'], p['rest']['pai'], p['rest']['no']): p['id'] for p in persons}
    rest = [dict(s, who=who_seat.get((s['sec'], s['pai'], s['no']))) for s in base['restSeats']]
    zones = {k: dict(v) for k, v in G.ZONES.items()}
    w3 = [p for p in persons if p['assembly'] == 'P6']
    zones['P6']['tailU'] = round(min(G.slot_u(p, p['slot']) for p in w3), 3)
    meta = dict(title='入經藏 西一＋桃竹 休息區→集結→進場 動線資料（2c 七出口三路接續）', built='2026-10-19',
                mPerUnit=base['meta']['mPerUnit'], frame=base['meta']['frame'], population=len(persons), tEnd=t_end,
                speedUnitPerSec=V, headway=HEADWAY, laneStagger=STAGGER, t0=T0,
                tStairStart=round(clocks['tStairStart'], 3), tGateStart=round(clocks['tGateStart'], 3),
                rules=RULES, assumptions=ASSUMPTIONS, checks=checks or {})
    phases = [dict(key='seated', label='休息區就座', t0=0, t1=T0),
              dict(key='descend', label='藍9→藍1 下 B2 集結，白1 進集結區 1', t0=T0, t1=first_enter),
              dict(key='enter', label='大隊 1→9 由西一入口六路進場；樓梯不停，白2 樓梯、白3 B1 短暫候隊，白4 以後由出口接尾', t0=first_enter, t1=t_end)]
    return dict(meta=meta, phases=phases, nodes=nodes, map=dict(base['map'], **G.stair_map(), gate=G.gate_map()), restSeats=rest, exits=exits, lanes=planj['lanes'],
                groups=groups, files=files, persons=persons, others=base['others'],
                stairSlots={str(j): [list(q) for q in G.STAIR_SLOTS[j]] for j in range(3)}, zones=zones)


RULES = [
    '樓梯三路由北到南 A、B、C；A 最靠看台側。樓梯序：藍9→藍1，再白1→白9；每大隊三欄一欄一路（白 6k−5/6k−4/6k−3；藍1 6k−2/6k−1/6k；藍2–9 從死巷反向走回西一入口，6k/6k−1/6k−2，A 路才對到最先轉進場的那條線）',
    '七個出口：139、140、141、142、143、144、145，雙側可走的區只走靠樓梯那一側；任何時刻供 A 路的出口最近、供 C 路的最遠，所以走廊上不交叉',
    'A 路：139（藍9–藍3）→140（藍2–白7）→141（白8–9）；B 路：141（藍9–藍3）→142（藍2–白3）→143（白4–9）；C 路：142（藍9–7）→144（藍6–1）→145（白1–9）',
    '每個出口是一條隊伍：由上排往下、每排由出口側往中央，先走的坐上面；每欄只來自一個出口',
    '藍衣全部先下 B2 集結（藍 8·9／6·7／4·5／2·3，藍1 與白1 同在集結區 1）；白2 在樓梯、白3 在 B1 短暫候隊（數秒）；白4 以後依西一入口時刻倒推離座，直接接尾下樓',
    '進場依大隊 1→9，西一入口六路（北三路白、南三路藍）每路連續不斷拍；不等全部集結完：大隊 1 在藍1、白1 隊頭站定後就出發，樓梯同時不停、白2 以後接續下樓；西一入口之後沿原場內路徑',
]
ASSUMPTIONS = [
    '1 單位 ≈ 7.6 m；步速 1.1 單位/秒；同一路相鄰兩人 0.4 秒、三路／六路錯開 0.17 秒、站定後 0.6 秒才起步；皆為動畫節奏，不是現場秒數',
    '座位、看台幾何、走道口、西一入口與場內路徑沿用版本 1 的示意圖面；集結區位置沿用版本 2；139 的 1–5 號不用',
    '樓梯照企劃圖 6白 的綠色 L 形：直段是樓梯（順著 B1 走廊往南直下），橫段是樓梯下的 B2 平台；西一入口 4 扇門、可 12 人並排；長度與寬度為示意',
    '碰撞檢查為圖面點距（0.03 單位），不是人體寬度或通道容量認證',
]


def write_seats_csv(data, path):
    cols = ['位置編碼', '衣色', '大隊', '演繹列', '演繹位置', '休息區', '休息排', '座號', '出口', '出口帶隊序',
            '樓梯路', '樓梯序號', '欄內順序', '集結區', '西一入口路', '西一入口序號']
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(cols)
        for p in sorted(data['persons'], key=lambda p: (p['lie'], p['pai'])):
            w.writerow([p['id'], p['costume'], p['dadui'], p['lie'], p['pai'], p['rest']['sec'], p['rest']['pai'], p['rest']['no'],
                        p['exit'], p['exitSeq'] + 1, p['lane'], p['laneIdx'] + 1, p['slot'] + 1, ZONE_LABEL[p['assembly']],
                        p['gateLane'] + 1, p['gateIdx'] + 1])


def avoid(base, planj, G, R, sched, clocks):
    """碰撞避讓（spec §3.6 第 2 階）：每輪對每對碰撞，把序號較後的那位整條時間線延後 SHIFT_STEP，同一人累計不超過 SHIFT_MAX。"""
    from collide import collisions
    people = planj['people']
    shift = collections.defaultdict(float)
    unresolved = []
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
    unresolved = [dict(kind='standing', who=list(k) if isinstance(k, tuple) else [k, v[1]], t=v[0] if isinstance(v, tuple) else v) for k, v in st.items()]
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
    G.regions()
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
    print('全長', data['meta']['tEnd'], '秒；樓梯時鐘起點', data['meta']['tStairStart'], '；西一入口時鐘起點', data['meta']['tGateStart'],
          '；檢核', '通過' if data['meta']['checks'].get('ok') else ('未跑' if no_avoid else '未通過'))


if __name__ == '__main__':
    main(sys.argv[1:])
