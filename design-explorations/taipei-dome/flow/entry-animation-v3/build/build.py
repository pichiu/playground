"""版本 3 排程：一個時鐘（樓梯口兩路、大隊交界對齊），拉式倒推離座時刻（spec §3.4），輸出 data.json 與 seats.csv。

用法: python3 build.py base.json plan.json ../data.json ../seats.csv [--no-avoid]
"""
import bisect
import collections
import csv
import json
import math
import sys

import plan
import routes

V = 1.1                 # 單位/秒
HEADWAY = 0.2           # 樓梯／走廊同一路相鄰兩人（一個接一個緊跟；下樓分成三條線後每條線約 0.6 秒一位）
STAGGER = 0.17          # 兩路錯開
T0 = 6.73               # 第一人離座
DADUI_GAP = 0.8         # 大隊交界的對齊空檔：前一大隊隊尾先過西一入口線的轉入點
SHIFT_STEP, SHIFT_MAX, AVOID_ROUNDS = 0.05, 0.15, 60
RANK_GAP = 0.6          # 門前隊伍一排六人並肩，排與排相隔（= 樓梯兩路 0.2 秒一人分成六條線後每條線的節奏）
SLOW = 0.075 / RANK_GAP # 門前隊伍推進的慢速（單位/秒）：前後間距 QUEUE_STEP 0.075、每 RANK_GAP 秒前進一格
TURN_T = 2.0            # 一排六人從隊頭一起轉進西一入口的時間（外側那條線路程長、走得快）
FILL_PAUSE = 1.0        # 大隊 1 把門前隊伍排滿後，稍停這麼久才開始推進
WAIT_MIN = 0.01         # 路徑上同一點停不到這麼久就不留停留點
LANE_K = {'A': 0, 'B': 1}
DIRECT_LABEL = '門前隊伍（B2）'


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
    """每人的路線與距離（不含時間）：to 從座位到自己那條線的起點（d_top 是其中到樓梯口的路程）。"""
    R = {}
    for p in people:
        to = G.entry_route(p)
        c = cum(to)
        R[p['id']] = dict(to=to, L_to=c[-1], d_top=c[G.stair_top_index(to)])
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


def head_rank(ranks, t):
    """此刻排在隊頭的是第幾排（連續值）：第 k 排在 ranks[k] 離開隊頭，後面一排用 RANK_GAP 秒慢慢補上一格。"""
    if t < ranks[0]:
        return 0.0
    k = bisect.bisect_right(ranks, t) - 1
    return k + min(1.0, (t - ranks[k]) / RANK_GAP)


def slot_s(line, r, ranks, t):
    """第 r 排在自己那條線上的位置（弧長）：隊頭往後 (r − 隊頭排號) 格，一格 QUEUE_STEP。"""
    return line.L - routes.QUEUE_STEP * (r - head_rank(ranks, t))


def rank_numbers(people):
    """排號：每個大隊從新的一排開始，大隊內第 slot 位就在第 slot 排；大隊人數少的那幾條線，大隊尾巴的幾排是空位。
    （不讓下一大隊往前補：下一大隊的場內路線會穿過上一大隊還沒站定的位置。）"""
    n = collections.Counter((p['dadui'], p['gateLane']) for p in people)
    start, off = {}, 0
    for d in sorted({p['dadui'] for p in people}):
        start[d] = off
        off += max(c for (dd, _), c in n.items() if dd == d)
    return {p['id']: start[p['dadui']] + p['slot'] for p in people}


def schedule(G, people, R=None, shift=None):
    """兩個時鐘（spec §3.4、§3.4c）：
    1. 樓梯口時刻 S（兩路、大隊交界對齊）；下樓後以步速走到自己那條線的起點（t.entry）。
    2. 門前隊伍：六條線同一個排號的人是一排（rank_numbers：每個大隊從新的一排開始），一排一起離開隊頭（t.enter）、一起轉進西一入口（t.gate = t.enter + TURN_T）。
       排與排至少隔 RANK_GAP；隊伍以 QUEUE_STEP / RANK_GAP 的慢速推進，前後間距 QUEUE_STEP。
       大隊 1 先把隊伍排滿（隊伍不動），全部到齊後 FILL_PAUSE 秒第 0 排出發；之後一排接一排，哪一排有人還沒到就等他（隊伍停住）。
       每人下樓後以步速追上自己的位置（t.assembly），之後跟著隊伍走。
    shift：個人整條時間線的平移秒數（避撞用）。"""
    R = R or prepare(G, people)
    shift = shift or {}
    rel, _ = aligned_clock(people, 'lane', 'dadIdx', 'dadui', lambda it: STAGGER * LANE_K[it['lane']], group_gap=DADUI_GAP)
    T_S0 = max(T0 + R[p['id']]['d_top'] / V - rel[p['id']] for p in people)
    stair = {p['id']: T_S0 + rel[p['id']] for p in people}
    entry = {p['id']: stair[p['id']] + (R[p['id']]['L_to'] - R[p['id']]['d_top']) / V for p in people}
    rank_of = rank_numbers(people)
    n_rank = 1 + max(rank_of.values())
    reach = [0.0] * n_rank                            # 這一排每個人都走得到隊頭的最早時刻
    for p in people:
        line, r = G.line_poly(p['gateLane']), rank_of[p['id']]
        reach[r] = max(reach[r], entry[p['id']] + line.L / V)
    fill = max(entry[p['id']] + (G.line_poly(p['gateLane']).L - routes.QUEUE_STEP * rank_of[p['id']]) / V for p in people if p['dadui'] == 1)
    ranks = []
    for r in range(n_rank):
        ranks.append(max(reach[r], fill + FILL_PAUSE if r == 0 else ranks[-1] + RANK_GAP))
    out = {}
    for p in people:
        pid, r, line = p['id'], rank_of[p['id']], G.line_poly(p['gateLane'])
        t_e, g = entry[pid], ranks[r]
        lo, hi = t_e, g                                   # 追上自己的位置：步速走的弧長 = 隊伍裡那一格的弧長
        if slot_s(line, r, ranks, t_e) <= 0:
            hi = t_e                                      # 隊伍排到線的起點後面（太長），check.py 會抓出來
        else:
            for _ in range(60):
                mid = (lo + hi) / 2
                if (mid - t_e) * V < slot_s(line, r, ranks, mid):
                    lo = mid
                else:
                    hi = mid
        out[pid] = dict(leave=stair[pid] - R[pid]['d_top'] / V, stair=stair[pid], entry=t_e, assembly=hi, enter=g, gate=g + TURN_T)
    for pid, dt in shift.items():
        for key in out[pid]:
            out[pid][key] += dt
    return out, dict(tStairStart=T_S0, tGateStart=min(v['gate'] for v in out.values()), ranks=ranks, rankOf=rank_of)


def person_path(G, base_person, p, r, t, ranks, rank):
    """座位 → 自己那條線的起點 → 步速追上隊伍 → 跟著隊伍（慢行或站住）到隊頭 → 一排一起轉進西一入口 → 場內（步速，沿版本 1 幾何重計時）。"""
    line = G.line_poly(p['gateLane'])
    dt = t['enter'] - ranks[rank]                 # 避撞平移
    path = list(timed(r['to'], t['leave']))
    s_join = (t['assembly'] - t['entry']) * V
    path += [(x, y, t['entry'] + s / V) for x, y, s in _line_pts(line, 0.0, s_join)][1:]
    # 隊伍裡：排號改變的時刻（離開隊頭、補上一格）是折點，速度不變的折點省略
    knots = [t['assembly']] + sorted({k + dt for g in ranks[:rank] for k in (g, g + RANK_GAP) if t['assembly'] + 1e-9 < k + dt < t['enter'] - 1e-9}) + [t['enter']]
    su = [(k, slot_s(line, rank, ranks, k - dt)) for k in knots]
    su[0], su[-1] = (t['assembly'], s_join), (t['enter'], line.L)
    keep = [su[0]]
    for i in range(1, len(su) - 1):
        (t0, s0), (t1, s1), (t2, s2) = keep[-1], su[i], su[i + 1]
        if abs((s1 - s0) / max(t1 - t0, 1e-9) - (s2 - s1) / max(t2 - t1, 1e-9)) > 1e-6:
            keep.append(su[i])
    keep.append(su[-1])
    for (t0, s0), (t1, s1) in zip(keep, keep[1:]):
        pts = _line_pts(line, s0, s1)
        for x, y, s in pts[1:]:
            path.append((x, y, t0 + (t1 - t0) * ((s - s0) / (s1 - s0) if s1 - s0 > 1e-9 else 1.0)))
    gx, gy = G.turn_route(p['gateLane'])[1]
    path.append((gx, gy, t['gate']))
    post = [q for q in base_person['path'] if q[2] > base_person['t']['gate'] + 1e-6]
    tt, last = path[-1][2], path[-1]
    for x, y, _ in post:
        tt += math.dist((last[0], last[1]), (x, y)) / V
        path.append((x, y, tt))
        last = (x, y)
    rounded = [[round(x, 3), round(y, 3), round(z, 3)] for x, y, z in path]
    clean = [rounded[0]]
    for q in rounded[1:]:
        if q[:2] == clean[-1][:2] and q[2] - clean[-1][2] < WAIT_MIN:
            continue
        if q[2] <= clean[-1][2] and q[:2] != clean[-1][:2]:
            q = [q[0], q[1], round(clean[-1][2] + 0.001, 3)]
        clean.append(q)
    return clean


def _line_pts(line, s0, s1):
    """線上 s0 → s1 的點（含中間的折點），附弧長。"""
    inner = [(q[0], q[1], c) for q, c in zip(line.p, line.cum) if s0 + 1e-9 < c < s1 - 1e-9]
    a, b = line.at(s0), line.at(s1)
    return [(a[0], a[1], s0)] + inner + [(b[0], b[1], s1)]


def _ids_between(persons, L, i0, i1):
    return [q['id'] for q in sorted((q for q in persons if q['lane'] == L and i0 <= q['laneIdx'] <= i1), key=lambda q: q['laneIdx'])]


def assemble(base, planj, G, R, sched, clocks, checks=None):
    who = {p['id']: p for p in base['persons']}
    people = planj['people']
    persons = []
    for p in people:
        r, t = R[p['id']], sched[p['id']]
        path = person_path(G, who[p['id']], p, r, t, clocks['ranks'], clocks['rankOf'][p['id']])
        tt = dict(leave=round(t['leave'], 3), stair=round(t['stair'], 3), entry=round(t['entry'], 3), assembly=round(t['assembly'], 3), enter=round(t['enter'], 3),
                  gate=round(t['gate'], 3), arrive=path[-1][2])
        persons.append(dict(id=p['id'], lie=p['lie'], pai=p['pai'], dadui=p['dadui'], costume=p['costume'], a=p['a'],
                            field=p['field'], rest=p['rest'], exit=p['exit'], exitSeq=p['exitSeq'], lane=p['lane'],
                            laneIdx=p['laneIdx'], gateLane=p['gateLane'], gateIdx=p['gateIdx'], slot=p['slot'], rank=clocks['rankOf'][p['id']],
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
    rest = [dict(s, kind=plan.seat_kind(s), who=who_seat.get((s['sec'], s['pai'], s['no']))) for s in base['restSeats']]
    meta = dict(title='入經藏 西一＋桃竹 休息區→進場 動線資料（版本 3 兩路直進）', built='2026-10-22',
                mPerUnit=base['meta']['mPerUnit'], frame=base['meta']['frame'], population=len(persons), tEnd=t_end,
                speedUnitPerSec=V, headway=HEADWAY, laneStagger=STAGGER, rankGap=RANK_GAP, queueSpeed=round(SLOW, 4), turnT=TURN_T, t0=T0, daduiGap=DADUI_GAP,
                tStairStart=round(clocks['tStairStart'], 3), tGateStart=round(t_gate0, 3),
                rules=RULES, assumptions=ASSUMPTIONS, checks=checks or {})
    t_go = min(p['t']['enter'] for p in persons)
    phases = [dict(key='seated', label='休息區就座', t0=0, t1=T0),
              dict(key='descend', label='大隊 1 白藍兩路離座、下樓梯，排滿門前隊伍', t0=T0, t1=t_go),
              dict(key='enter', label='門前隊伍慢慢推進，一排六人並肩一起轉進西一入口，一排接一排；樓梯不停', t0=t_go, t1=t_end)]
    return dict(meta=meta, phases=phases, nodes=nodes, map=dict(base['map'], **G.stair_map(), gate=G.gate_map(), gateLanes=G.gate_lanes_map()), restSeats=rest, exits=exits,
                lanes=planj['lanes'], groups=groups, files=files, persons=persons, others=base['others'])


RULES = [
    '兩路：A 路白衣靠看台側、B 路藍衣外側（B1 走廊、樓梯、B2 都一樣）；大隊 1→9 依序，兩路同時走',
    '每一路三列交錯排隊：每列排大的先，三列輪流各出一人（白衣列 6k−5→6k−4→6k−3，藍衣列 6k−2→6k−1→6k），排完的列跳過',
    '出口：白衣依序用 139 → 140 → 141 → 142，藍衣用 142 → 143 → 144 → 145；出口坐滿才換下一個，換口可以落在大隊中間',
    '142 兩路共用：藍衣大隊 1–3 先從上排出，白衣大隊 9 最後從下排出；任何時刻白衣用的出口都比藍衣近、且在不同階梯，所以走廊上不交叉',
    '每個出口是一條隊伍：由上排往下、每排由出口側往中央，先走的坐上面',
    '不進 B2 集結區、不在樓梯或 B1 走廊候隊：下樓後白衣散到北三條線、藍衣散到南三條線，在樓梯口到西一入口這段 B2 走廊（舞台後方）排成六條線的門前隊伍；大隊 1 先把隊伍排滿，之後隊伍慢慢往前推，一排六人並肩、一起轉進西一入口，一排接一排不停；每個大隊從新的一排開始；之後沿原場內路徑',
]
ASSUMPTIONS = [
    '1 單位 ≈ 7.6 m；步速 1.1 單位/秒；樓梯同一路相鄰兩人 0.2 秒（一個接一個緊跟）、兩路錯開 0.17 秒、大隊交界加 0.8 秒；門前隊伍前後間距 0.075 單位、0.6 秒一排、慢行 0.125 單位/秒，一排轉進門 2 秒；皆為動畫節奏，不是現場秒數',
    '座位、看台幾何、走道口、西一入口與場內路徑沿用版本 1 的示意圖面；保留不坐：139 的 34 席給台東（第 1–10 排 1–3 號、第 11–12 排 4–5 號）、144 第 1–6 排 72 席',
    '樓梯照企劃圖 6白 的綠色 L 形：直段是樓梯（順著 B1 走廊往南直下），橫段是樓梯下的 B2 平台；西一入口 4 扇門、可 12 人並排；長度與寬度為示意',
    '碰撞檢查為圖面點距（0.03 單位），不是人體寬度或通道容量認證',
    '門前隊伍是唯一的緩衝：樓梯以上沒有候隊，任何一人延誤，後面整路跟著延誤；門前隊伍一排有人沒到，整個隊伍停住等他',
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
