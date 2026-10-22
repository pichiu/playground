"""版本 3 檢核（spec §4）。build.py 也用 check_all 寫 meta.checks。

用法: python3 check.py ../data.json   → 印表；重算與 meta.checks 比對；未通過 exit 1

所有數字都從 persons / restSeats 重算；data.json 裡 exits 的 used / capacity / order 只拿來比對，不信任。
"""
import collections
import json
import sys

import build
import plan
import routes
from collide import collisions
from geo import Poly, pairs

GAP_MIN, GAP_MAX = build.HEADWAY - 0.15, build.HEADWAY + 0.15   # 樓梯口節拍容許 ± 0.15（避撞平移）
BOUNDARY_MAX = 7.0                 # 大隊交界：兩路同一大隊人數差到 12 人，短的那路空 0.4×12 + 0.4 + 0.8 ≈ 6.0 秒（spec §4）
GATE_GAP_MAX = 3 * build.HEADWAY + 0.6   # 西一入口每條線、同一大隊內：三列交錯約 3 拍一位 ± 避撞平移；大隊 1 頭一批 0.4 秒一位
RULE_SLACK = 0.4                   # 交界規則值 = 節拍 ×（兩路該大隊人數差）+ 節拍 + 大隊空檔（build.HEADWAY、build.DADUI_GAP），容許錯開與避撞平移 0.4（spec §4）
GATE_BOUNDARY_MAX = 12.0           # 西一入口每條線兩個大隊之間的空檔上限：一路接續，只有樓梯交界對齊的空檔（實際 ≤ 約 8 秒）
LATER_WAIT_MAX = 1.0               # 大隊 1 頭一批以外的人到門前就接著走，最多為了保持西一入口 0.4 秒間隔稍停
SHIFT_TOL = 0.16                   # 避撞平移上限 0.15
WAIT_SLACK = 0.05                  # 每人從離座到到位的時間不得超過路程 / 步速 + 這麼多（座標與時刻四捨五入的誤差）
WAIT_MIN = build.WAIT_MIN           # 等不到這麼久就不算停（建置時也不留停留點）
POPULATION = 1609
COMPARED = ('collisions', 'nesting', 'assignment', 'routes', 'continuity', 'waits', 'doorQueue', 'seats', 'capacity')   # 與 meta.checks 逐項比對的鍵


def _gaps(ps, tkey, group_key):
    """依序號排好後的拍距：群內 / 交界分開統計；順序必須單調。"""
    within, boundary, order_ok = [], [], True
    for a, b in zip(ps, ps[1:]):
        gap = b['t'][tkey] - a['t'][tkey]
        if gap < -1e-9:
            order_ok = False
        (within if a[group_key] == b[group_key] else boundary).append(gap)
    return dict(n=len(ps), minGap=round(min(within + boundary), 3) if ps[1:] else None,
                maxGapWithin=round(max(within), 3) if within else 0.0,
                maxGapBoundary=round(max(boundary), 3) if boundary else 0.0, orderOk=order_ok)


def _seg_cross(p1, p2, p3, p4):
    """兩線段是否真正相交（端點相觸、共線重疊不算）。"""
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    d1, d2, d3, d4 = cross(p3, p4, p1), cross(p3, p4, p2), cross(p1, p2, p3), cross(p1, p2, p4)
    return (d1 > 0) != (d2 > 0) and (d3 > 0) != (d4 > 0) and 0 not in (d1, d2, d3, d4)


def _poly_cross(a, b):
    return sum(1 for s1 in zip(a, a[1:]) for s2 in zip(b, b[1:]) if _seg_cross(*s1, *s2))


def lane_crossings(data):
    """純幾何、不看時間：兩條隊伍的線交叉，再怎麼錯開都是人穿過人。
    B2：每大隊六列頭一位（各列 gateIdx 最小者），從進 B2 走廊（u ≥ 0.9、離中線 < 0.3）到過西一入口後 3 秒，兩兩不相交。
    B1：每大隊兩路頭一位，從離座到樓梯口，不相交。"""
    B2 = Poly(pairs(data['map']['b2Corridor']))
    heads = {}
    for p in data['persons']:
        k = (p['dadui'], p['gateLane'])
        if k not in heads or p['gateIdx'] < heads[k]['gateIdx']:
            heads[k] = p
    lane_heads = {}
    for p in data['persons']:
        k = (p['dadui'], p['lane'])
        if k not in lane_heads or p['laneIdx'] < lane_heads[k]['laneIdx']:
            lane_heads[k] = p

    def b2_part(p):
        out, inside = [], False
        for q in p['path']:
            if q[2] > p['t']['gate'] + 3 + 1e-6:
                break
            if not inside:
                u, _, dist = B2.proj(q[:2])
                inside = q[2] >= p['t']['stair'] and u >= 0.9 and dist < 0.3
            if inside:
                out.append((q[0], q[1]))
        return out

    def b1_part(p):
        return [(q[0], q[1]) for q in p['path'] if q[2] <= p['t']['stair'] + 1e-6]

    n, examples = 0, []
    for d in range(1, 10):
        parts = {j: b2_part(heads[(d, j)]) for j in range(6) if (d, j) in heads}
        for i in parts:
            for j in parts:
                if i < j:
                    c = _poly_cross(parts[i], parts[j])
                    if c:
                        n += c
                        examples.append(dict(phase='B2', dadui=d, lines=[i, j], who=[heads[(d, i)]['id'], heads[(d, j)]['id']]))
        if (d, 'A') in lane_heads and (d, 'B') in lane_heads:
            c = _poly_cross(b1_part(lane_heads[(d, 'A')]), b1_part(lane_heads[(d, 'B')]))
            if c:
                n += c
                examples.append(dict(phase='B1', dadui=d, lines=['A', 'B'], who=[lane_heads[(d, 'A')]['id'], lane_heads[(d, 'B')]['id']]))
    return dict(crossings=n, examples=examples[:4])


def check_all(data, coll=None):
    """coll：已算好的 (穿過站定者, 走路互撞)，build.py 從避撞最後一輪帶進來；沒給就重算。"""
    persons = data['persons']
    out = {}
    # 1. 碰撞
    st, wk = coll if coll is not None else collisions(persons, data['meta']['tEnd'])
    out['collisions'] = dict(standing=len(st), walking=len(wk),
                             examples=[dict(kind='standing', who=[k, v[1]], t=v[0]) for k, v in list(st.items())[:3]] +
                                      [dict(kind='walking', who=list(k), t=t) for k, t in list(wk.items())[:3]])
    # 2. 依時間的巢狀：兩路依通過樓梯口時刻合併，兩路都開始後 A 的出口比 B 近、且不在同一座階梯
    bad, same = plan.nesting_violations(persons, key=lambda p: (p['t']['stair'], p['lane']))
    out['nesting'] = dict(violations=len(bad), sameStair=len(same), examples=(bad + same)[:3])
    # 2b. 指派：每路換口只往上游；換口前那個出口已用滿（兩路合計）；分坐兩出口的列數只列出、不算違反
    seqs = {L: sorted((p for p in persons if p['lane'] == L), key=lambda p: p['laneIdx']) for L in plan.LANES}
    by_exit = {e: sorted((p for p in persons if p['exit'] == e), key=lambda p: p['exitSeq']) for e in plan.EXITS}
    cap_of = {e: len(plan.usable_seats(data, e)) for e in plan.EXITS}
    upstream, not_full, segments, examples = 0, 0, {}, []
    for L in plan.LANES:
        pairs_ = [(a, b) for a, b in zip(seqs[L], seqs[L][1:]) if a['exit'] != b['exit']]
        segments[L] = 1 + len(pairs_)
        for a, b in pairs_:
            if plan.EXIT_RANK[b['exit']] < plan.EXIT_RANK[a['exit']]:
                upstream += 1
                examples.append(dict(lane=L, idx=b['laneIdx'], exits=[a['exit'], b['exit']]))
            elif len(by_exit[a['exit']]) < cap_of[a['exit']]:
                not_full += 1
                examples.append(dict(lane=L, idx=b['laneIdx'], exits=[a['exit'], b['exit']], used=len(by_exit[a['exit']]), capacity=cap_of[a['exit']]))
    by_col = collections.defaultdict(set)
    for p in persons:
        by_col[p['lie']].add(p['exit'])
    split = sorted(lie for lie, es in by_col.items() if len(es) > 1)
    out['assignment'] = dict(upstreamViolations=upstream, notFullSwitches=not_full, segments=segments, splitColumns=len(split),
                             splitLies=split, examples=examples[:3])
    # 2c. 路徑不交叉
    out['routes'] = lane_crossings(data)
    # 3. 不斷拍：樓梯口兩路（t.enter）、西一入口六路（t.gate）
    stair = {L: _gaps(seqs[L], 'stair', 'dadui') for L in plan.LANES}
    gate = {}
    for j in range(6):
        ps = sorted((p for p in persons if p['gateLane'] == j), key=lambda p: p['gateIdx'])
        gate[str(j)] = _gaps(ps, 'gate', 'dadui')
    n_ld = collections.Counter((p['lane'], p['dadui']) for p in persons)
    rule_bad = []
    for L in plan.LANES:
        for a, b in zip(seqs[L], seqs[L][1:]):
            if a['dadui'] != b['dadui']:
                d = a['dadui']
                rule = build.HEADWAY * (max(n_ld[(M, d)] for M in plan.LANES) - n_ld[(L, d)]) + build.HEADWAY + build.DADUI_GAP
                gap = b['t']['stair'] - a['t']['stair']
                if gap > rule + RULE_SLACK + 1e-6:
                    rule_bad.append(dict(lane=L, dadui=d, gap=round(gap, 3), rule=round(rule, 3)))
    cont_ok = not rule_bad and all(v['maxGapBoundary'] <= GATE_BOUNDARY_MAX for v in gate.values()) and all(v['orderOk'] and v['minGap'] >= GAP_MIN and v['maxGapWithin'] <= GAP_MAX and v['maxGapBoundary'] <= BOUNDARY_MAX for v in stair.values()) and \
        all(v['orderOk'] and v['minGap'] >= GAP_MIN and v['maxGapWithin'] <= GATE_GAP_MAX for v in gate.values())
    out['continuity'] = dict(stair=stair, gate=gate, boundaryRuleViolations=len(rule_bad), boundaryExamples=rule_bad[:3], ok=cont_ok)
    # 3b. 只在門前自己的位置等：離座到門前、門前到到位全程等速（時間 = 路程 / 步速）；
    #     停留只有一段：assembly → enter，站在自己那條線（B2 偏移 0.2 − 0.08j）、隊頭往後第 slot 位（u 4.2 − 0.075·slot）
    V = data['meta']['speedUnitPerSec']
    B2 = Poly(pairs(data['map']['b2Corridor']))

    def extra(a):
        return (a[-1][2] - a[0][2]) - build.cum([q[:2] for q in a])[-1] / V if len(a) > 1 else 0.0
    # 圖面的 B2 線是從樓梯平台截起的，u 與建置用的整條折線差一個常數：以大隊 1 頭一批隊頭（第 0 位）的 u 當隊頭那條線。
    # 有等的人站在自己那條線、隊頭往後整數格（0.075 一格）；門前位置是路線上的頂點，時刻就是 t.assembly
    def spot_of(p):
        q = min(p['path'], key=lambda q: abs(q[2] - p['t']['assembly']))
        return q if abs(q[2] - p['t']['assembly']) < 2e-3 else None
    first = [p for p in persons if p['dadui'] == 1 and p['slot'] < build.FIRST_BATCH]
    heads = sorted(B2.proj(spot_of(p)[:2])[0] for p in first if p['slot'] == 0 and spot_of(p))
    head_u = heads[len(heads) // 2] if heads else 0.0

    def spot_k(p):
        """站在隊頭往後第幾格（不在自己那條線上、不在整數格上就回 None）。"""
        q = spot_of(p)
        if q is None:
            return None
        u, o, _ = B2.proj(q[:2])
        k = round((head_u - u) / routes.QUEUE_STEP)
        return k if k >= 0 and abs(head_u - routes.QUEUE_STEP * k - u) <= 0.01 and abs(o - routes.line_off(p['gateLane'])) <= 0.01 else None

    def spot_ok(p):
        return p['t']['enter'] - p['t']['assembly'] < WAIT_MIN or spot_k(p) is not None
    wait_bad, waits = [], []
    for p in persons:
        t, a = p['t'], p['path']
        ka = next((i for i, q in enumerate(a) if abs(q[2] - t['assembly']) < 1e-6), None)
        ke = next((i for i, q in enumerate(a) if abs(q[2] - t['enter']) < 1e-6), None)
        w = t['enter'] - t['assembly']
        bad = p.get('adv') or w < -1e-9 or abs(a[0][2] - t['leave']) > 1e-6 or abs(a[-1][2] - t['arrive']) > 1e-6 or not spot_ok(p)
        if not bad and w >= WAIT_MIN:
            bad = ka is None or ke is None or ke != ka + 1 or a[ka][:2] != a[ke][:2]
        if not bad:
            pre, post = (a[:ka + 1], a[ke:]) if w >= WAIT_MIN else (a, [])
            bad = extra(pre) > WAIT_SLACK or extra(post) > WAIT_SLACK
        if bad:
            wait_bad.append(p['id'])
        waits.append(max(0.0, w))
    out['waits'] = dict(violations=len(wait_bad), examples=wait_bad[:3], maxWait=round(max(waits), 3),
                        waiting=sum(1 for w in waits if w >= WAIT_MIN))
    # 3c. 門前切齊、一路接續：大隊 1 頭一批每條線 FIRST_BATCH 人，六條線的第一位站同一條線（切齊），G = T_1 + 0.4·slot + 0.17·j；
    #     其餘的人到門前就接著走（最多為了保持西一入口 0.4 秒間隔稍停 LATER_WAIT_MAX）
    q_bad = []
    base_t = sorted(p['t']['gate'] - build.ENTRY_HEADWAY * p['slot'] - build.STAGGER * p['gateLane'] for p in first)
    T1 = base_t[len(base_t) // 2] if base_t else 0.0
    off = [p['id'] for p in first if abs(p['t']['gate'] - build.ENTRY_HEADWAY * p['slot'] - build.STAGGER * p['gateLane'] - T1) > SHIFT_TOL
           or not spot_ok(p) or (p['slot'] == 0 and spot_k(p) != 0)]   # 六條線的隊頭都站在第 0 格（切齊）
    if off:
        q_bad.append(dict(part='first', who=off[:4]))
    later = [p['id'] for p in persons if p not in first and p['t']['enter'] - p['t']['assembly'] > LATER_WAIT_MAX]
    if later:
        q_bad.append(dict(part='later', who=later[:4]))
    out['doorQueue'] = dict(firstBatch=len(first), laterWaiting=len(later), violations=len(off) + len(later), examples=q_bad[:3])
    # 4. 座位：唯一、合法、休息區＝出口的區、每出口由上排往下且由出口側往中央、exits.order 名單就是該出口全員（依 exitSeq）
    keys = [(p['rest']['sec'], p['rest']['pai'], p['rest']['no']) for p in persons]
    seat_of = {(s['sec'], s['pai'], s['no']): s for s in data['restSeats']}
    illegal = sum(1 for k in keys if k not in seat_of or not plan.seat_usable(seat_of[k]))
    wrong_sec = sum(1 for p in persons if p['rest']['sec'] != plan.EXIT_DEF[p['exit']]['sec'])
    listed = {e['key']: e for e in data['exits']}
    order_bad = coverage_bad = 0
    for e in plan.EXITS:
        q = by_exit[e]
        if [p['exitSeq'] for p in q] != list(range(len(q))) or listed.get(e, {}).get('order') != [p['id'] for p in q]:
            coverage_bad += 1
        pais = [p['rest']['pai'] for p in q]
        if pais != sorted(pais, reverse=True):
            order_bad += 1
        for pai in set(pais):
            nos = [p['rest']['no'] for p in q if p['rest']['pai'] == pai]
            want = sorted(nos) if plan.EXIT_DEF[e]['fill'] == 'asc' else sorted(nos, reverse=True)
            if nos != want:
                order_bad += 1
        leaves = [p['t']['leave'] for p in q]                  # FIFO：先走的坐上面
        if any(b < a - 0.15 - 1e-6 for a, b in zip(leaves, leaves[1:])):
            order_bad += 1
    out['seats'] = dict(unique=len(set(keys)), population=len(persons), illegal=illegal, wrongSection=wrong_sec, orderViolations=order_bad, orderCoverage=coverage_bad)
    # 5. 容量：用量由 persons 計、可用席由 restSeats 重算，再與 exits 欄位比對
    cap = {}
    for e in plan.EXITS:
        used = len(by_exit[e])
        f = listed.get(e, {})
        cap[e] = dict(used=used, capacity=cap_of[e], fieldsOk=bool(f.get('used') == used and f.get('capacity') == cap_of[e]))
    out['capacity'] = cap
    out['ok'] = bool(not st and not wk and not bad and not same and upstream == 0 and not_full == 0 and cont_ok
                     and out['routes']['crossings'] == 0 and not wait_bad and not q_bad
                     and len(set(keys)) == len(persons) == POPULATION and illegal == 0 and wrong_sec == 0 and order_bad == 0 and coverage_bad == 0
                     and all(v['used'] <= v['capacity'] and v['fieldsOk'] for v in cap.values()))
    return out


def main(path):
    data = json.load(open(path, encoding='utf-8'))
    C = check_all(data)
    A, S, Rt, Cn = C['assignment'], C['seats'], C['routes'], C['continuity']
    rng = lambda vs: f"{min(v['minGap'] for v in vs)}–{max(v['maxGapWithin'] for v in vs)}"
    rows = [
        ('穿過站定者 / 走路互撞', f"{C['collisions']['standing']} / {C['collisions']['walking']}", '0 / 0', C['collisions']['standing'] == 0 == C['collisions']['walking']),
        ('依時間巢狀：出口順序違反 / 同一座階梯', f"{C['nesting']['violations']} / {C['nesting']['sameStair']}", '0 / 0', C['nesting']['violations'] == 0 == C['nesting']['sameStair']),
        ('指派：換口往下游 / 未坐滿就換', f"{A['upstreamViolations']} / {A['notFullSwitches']}（每路 {'、'.join(f'{L} {A['segments'][L]} 段' for L in plan.LANES)}；分坐兩出口 {A['splitColumns']} 列）",
         '0 / 0', A['upstreamViolations'] == 0 == A['notFullSwitches']),
        ('路徑交叉（B2 六列 / B1 兩路）', f"{Rt['crossings']}", '0', Rt['crossings'] == 0),
        ('不斷拍', f"樓梯 {rng(Cn['stair'].values())}，交界 ≤ {max(v['maxGapBoundary'] for v in Cn['stair'].values())}（超出規則值 {Cn['boundaryRuleViolations']} 處）；西一入口 {rng(Cn['gate'].values())}",
         f'樓梯 {GAP_MIN}–{GAP_MAX}、交界 ≤ {BOUNDARY_MAX}；西一入口 ≥ {GAP_MIN}、大隊內 ≤ {GATE_GAP_MAX}、大隊間 ≤ {GATE_BOUNDARY_MAX}', Cn['ok']),
        ('只在門前自己的位置等', f"{C['waits']['violations']}（{C['waits']['waiting']} 人等，最久 {C['waits']['maxWait']} 秒）", '0', C['waits']['violations'] == 0),
        ('門前切齊、一路接續（大隊 1 頭一批切齊後進場，其餘到門前就走）', f"{C['doorQueue']['violations']}（頭一批 {C['doorQueue']['firstBatch']} 人；其餘停超過 {LATER_WAIT_MAX} 秒 {C['doorQueue']['laterWaiting']} 人）", '0', C['doorQueue']['violations'] == 0),
        ('座位唯一 / 違規席 / 區不符 / 順序違反 / 名單不符', f"{S['unique']} / {S['illegal']} / {S['wrongSection']} / {S['orderViolations']} / {S['orderCoverage']}", f'{POPULATION} / 0 / 0 / 0 / 0',
         S['unique'] == POPULATION and S['illegal'] == 0 == S['wrongSection'] == S['orderViolations'] == S['orderCoverage']),
        ('出口用量 ≤ 可用席（重算，與 exits 欄位一致）', ', '.join(f"{k} {v['used']}/{v['capacity']}" + ('' if v['fieldsOk'] else '（欄位不符）') for k, v in C['capacity'].items()), '成立',
         all(v['used'] <= v['capacity'] and v['fieldsOk'] for v in C['capacity'].values())),
    ]
    for name, val, thr, ok in rows:
        print(f"[{'OK' if ok else 'NG'}] {name}: {val}（門檻 {thr}）")
    meta = data['meta'].get('checks') or {}
    same = bool(meta) and all(meta.get(k) == C.get(k) for k in COMPARED) and meta.get('ok') == C['ok']
    print('meta.checks 與重算一致' if same else 'meta.checks 與重算不一致或缺少', '；', '通過' if C['ok'] and same else '未通過')
    return 0 if C['ok'] and same else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1]))
