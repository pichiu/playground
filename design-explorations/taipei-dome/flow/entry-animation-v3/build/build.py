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
DADUI_GAP = 0.8         # 大隊交界的對齊空檔：前一大隊隊尾先過西一入口線的轉入點
SHIFT_STEP, SHIFT_MAX, AVOID_ROUNDS = 0.05, 0.15, 60
FIRST_BATCH = 10        # 大隊 1 在門前每條線先集合這麼多人、六條線切齊，再開始進場；之後一路接續、不分大隊停下
ENTRY_HEADWAY = 0.4     # 西一入口每條線相鄰兩人：門前集合一部分人後，大隊以這個節奏連續進場
WAIT_MIN = 0.01         # 在門前等不到這麼久就不算停，路徑上不留停留點（check.py 同一個值）
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
        R[p['id']] = route_at(G, p, None)
    return R


def route_at(G, p, q):
    """站在自己那條線第 q 位（None＝列內位次）時的路線與距離；L_full 是不停一路走到收攏點的路程。"""
    to, dep = G.queue_routes(p, q)
    cto = cum(to)
    k = G.stair_top_index(to)
    return dict(to=to, dep=dep, L_to=cto[-1], d_top=cto[k], k_top=k, L_dep=cum(dep)[-1], L_full=cto[-1] + cum(dep)[-1], q=q)


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
    1. 樓梯口時刻 S（兩路、大隊交界對齊）；不停的話過西一入口 = S + 樓梯口到收攏點路程/V。
    2. 西一入口：每條線一條隊伍、一路接續不分大隊——G = max(自己不停的時刻, 同一線前一位 + ENTRY_HEADWAY)。
       只有大隊 1 先在門前每條線集合 FIRST_BATCH 人、六條線切齊（同 2c：G = T_1 + 0.4·位次 + 0.17·j），之後誰到門前就接著走；
       被前一位擋住的人站在自己那條線上（隊頭往後第 q 位，q＝此刻還在他前面排著的人數），輪到才走。
    shift：個人整條時間線的平移秒數（避撞用）。"""
    R = R or prepare(G, people)
    shift = shift or {}
    rel, _ = aligned_clock(people, 'lane', 'dadIdx', 'dadui', lambda it: STAGGER * LANE_K[it['lane']], group_gap=DADUI_GAP)
    T_S0 = max(T0 + R[p['id']]['d_top'] / V - rel[p['id']] for p in people)
    stair = {p['id']: T_S0 + rel[p['id']] for p in people}
    natural = {p['id']: stair[p['id']] + (R[p['id']]['L_full'] - R[p['id']]['d_top']) / V for p in people}
    first = [p for p in people if p['dadui'] == 1 and p['slot'] < FIRST_BATCH]
    T1 = max(natural[p['id']] - ENTRY_HEADWAY * p['slot'] - STAGGER * p['gateLane'] for p in first)
    lines = collections.defaultdict(list)
    for p in people:
        lines[p['gateLane']].append(p)
    out = {}
    for j, ps in lines.items():
        ps.sort(key=lambda p: (p['dadui'], p['slot']))
        prev = None                                     # (過門時刻, 站的位次或 None, 起步時刻)
        for p in ps:
            pid = p['id']
            g = natural[pid]
            if p['dadui'] == 1:
                g = max(g, T1 + ENTRY_HEADWAY * p['slot'] + STAGGER * j)
            if prev is not None:
                g = max(g, prev[0] + ENTRY_HEADWAY)
            spot = None
            if g - natural[pid] >= WAIT_MIN:
                # 站位不往前補：前一位還站著就排在他後面一格，前一位已經起步就站隊頭
                spot = prev[1] + 1 if prev is not None and prev[1] is not None and prev[2] > stair[pid] + (R[pid]['L_to'] - R[pid]['d_top']) / V else 0
                if spot != (R[pid]['q'] if R[pid]['q'] is not None else p['slot']):
                    R[pid] = route_at(G, p, spot)
            r = R[pid]
            out[pid] = dict(leave=stair[pid] - r['d_top'] / V, stair=stair[pid], assembly=stair[pid] + (r['L_to'] - r['d_top']) / V,
                            enter=g - r['L_dep'] / V, gate=g)
            prev = (g, spot, out[pid]['enter'])
    for pid, dt in shift.items():
        for key in out[pid]:
            out[pid][key] += dt
    return out, dict(tStairStart=T_S0, tGateStart=min(v['gate'] for v in out.values()))


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
        if q[:2] == clean[-1][:2] and q[2] - clean[-1][2] < WAIT_MIN:   # 沒等（或等不到 WAIT_MIN）就不留停留點
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
              dict(key='enter', label='大隊 1 頭一批切齊後進場，之後一路接續（每路 0.4 秒起）；樓梯不停', t0=t_go, t1=t_end)]
    return dict(meta=meta, phases=phases, nodes=nodes, map=dict(base['map'], **G.stair_map(), gate=G.gate_map(), gateLanes=G.gate_lanes_map()), restSeats=rest, exits=exits,
                lanes=planj['lanes'], groups=groups, files=files, persons=persons, others=base['others'])


RULES = [
    '兩路：A 路白衣靠看台側、B 路藍衣外側（B1 走廊、樓梯、B2 都一樣）；大隊 1→9 依序，兩路同時走',
    '每一路三列交錯排隊：每列排大的先，三列輪流各出一人（白衣列 6k−5→6k−4→6k−3，藍衣列 6k−2→6k−1→6k），排完的列跳過',
    '出口：白衣依序用 139 → 140 → 141 → 142，藍衣用 142 → 143 → 144 → 145；出口坐滿才換下一個，換口可以落在大隊中間',
    '142 兩路共用：藍衣大隊 1–3 先從上排出，白衣大隊 9 最後從下排出；任何時刻白衣用的出口都比藍衣近、且在不同階梯，所以走廊上不交叉',
    '每個出口是一條隊伍：由上排往下、每排由出口側往中央，先走的坐上面',
    '不在 B2 集結區、不在樓梯或走廊候隊：下樓後白衣散到北三條線、藍衣散到南三條線，大隊 1 先在西一入口前每條線集合 10 人、六條線切齊，0.4 秒一位、錯開 0.17 秒進場；之後一路接續，誰到門前就接著走，不再分大隊停下（過門後還有迴廊）；之後沿原場內路徑',
]
ASSUMPTIONS = [
    '1 單位 ≈ 7.6 m；步速 1.1 單位/秒；同一路相鄰兩人 0.4 秒、兩路錯開 0.17 秒、大隊交界加 0.8 秒；皆為動畫節奏，不是現場秒數',
    '座位、看台幾何、走道口、西一入口與場內路徑沿用版本 1 的示意圖面；139 的 1–5 號不用',
    '樓梯照企劃圖 6白 的綠色 L 形：直段是樓梯（順著 B1 走廊往南直下），橫段是樓梯下的 B2 平台；西一入口 4 扇門、可 12 人並排；長度與寬度為示意',
    '碰撞檢查為圖面點距（0.03 單位），不是人體寬度或通道容量認證',
    '沒有中途緩衝：任何一人延誤，後面整路跟著延誤（只有大隊 1 頭一批在門前等）',
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
    """碰撞避讓（spec §3.6）：每輪對每對碰撞，把西一入口較晚的那位整條時間線延後 SHIFT_STEP，同一人累計不超過 SHIFT_MAX。
    回傳最後的 sched、clocks、組好的 data 與它的碰撞結果（main 直接沿用，不再重組、重算）。"""
    from collide import collisions
    people = planj['people']
    shift = collections.defaultdict(float)
    for rnd in range(AVOID_ROUNDS + 1):
        data = assemble(base, planj, G, R, sched, clocks)
        st, wk = collisions(data['persons'], data['meta']['tEnd'])
        print('  避撞第', rnd, '輪：穿過站定者', len(st), '互撞', len(wk), file=sys.stderr)
        if (not st and not wk) or rnd == AVOID_ROUNDS:
            break
        P = {p['id']: p for p in data['persons']}
        later = {a if P[a]['t']['gate'] > P[b]['t']['gate'] else b for (a, b) in wk} | set(st)
        moved = False
        for pid in later:
            if shift[pid] + SHIFT_STEP <= SHIFT_MAX + 1e-9:
                shift[pid] += SHIFT_STEP
                moved = True
        if not moved:
            break
        sched, clocks = schedule(G, people, R, shift)
    return sched, clocks, data, (st, wk)


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
    if no_avoid:
        data = assemble(base, planj, G, R, sched, clocks)
    else:
        import check
        sched, clocks, data, coll = avoid(base, planj, G, R, sched, clocks)
        data['meta']['checks'] = check.check_all(data, coll)          # 碰撞已在 avoid 最後一輪算過；check.py CLI 會再獨立重算
    json.dump(data, open(out_path, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    write_seats_csv(data, csv_path)
    print('全長', data['meta']['tEnd'], '秒；樓梯時鐘起點', data['meta']['tStairStart'], '；第一位過西一入口', data['meta']['tGateStart'],
          '；檢核', '通過' if data['meta']['checks'].get('ok') else ('未跑' if no_avoid else '未通過'))


if __name__ == '__main__':
    main(sys.argv[1:])
