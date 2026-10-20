"""2c 檢核（spec §3.7）。build.py 也用 check_all 寫 meta.checks。

用法: python3 check.py ../data.json   → 印表；重算與 meta.checks 比對；未通過 exit 1

所有數字都從 persons / restSeats 重算；data.json 裡 exits 的 used / capacity / order 只拿來比對，不信任。
"""
import collections
import json
import math
import sys

import plan
from collide import collisions
from geo import Poly, pairs

GAP_MIN, GAP_MAX = 0.25, 0.55      # 節拍容許 0.4 ± 0.15（避撞平移）
BOUNDARY_MAX = 5.0                 # 大隊／區塊交界的對齊空檔上限：最長欄差 6 拍 + 1 拍 + 0.8 空檔 + 0.85 錯開 ≈ 4.45
POPULATION = 1609
COMPARED = ('collisions', 'nesting', 'assignment', 'routes', 'seats', 'staging', 'capacity')   # 與 meta.checks 逐項比對的鍵


def _gaps(ps, tkey, group_key):
    """同一路依序號排好後的拍距：群內 / 交界分開統計；順序必須單調。"""
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
    """同一大隊三路頭一位（slot 0）的路徑折線兩兩不得相交——純幾何、不看時間：兩條隊伍的線交叉，再怎麼錯開都是人穿過人。
    departure：離開集結區（t.enter）到過西一入口後 3 秒；arrival：進到 B2 走廊起到站定（只看 B2 的集結區）。"""
    B2 = Poly(pairs(data['map']['b2Corridor']))
    heads = {(p['costume'], p['dadui'], p['lane']): p for p in data['persons'] if p['slot'] == 0}

    def seg(p, t0, t1):
        return [(q[0], q[1]) for q in p['path'] if t0 - 1e-6 <= q[2] <= t1 + 1e-6]

    def b2_entry_t(p):
        return next((q[2] for q in p['path'] if B2.proj(q[:2])[0] >= 0.9 and B2.proj(q[:2])[2] < 0.3), None)

    dep = arr = 0
    examples = []
    for c, d in sorted({k[:2] for k in heads}):
        for a, b in (('A', 'B'), ('A', 'C'), ('B', 'C')):
            pa, pb = heads.get((c, d, a)), heads.get((c, d, b))
            if not pa or not pb:
                continue
            t0, t1 = min(pa['t']['enter'], pb['t']['enter']), max(pa['t']['gate'], pb['t']['gate']) + 3
            n = _poly_cross(seg(pa, t0, t1), seg(pb, t0, t1))
            if n:
                dep += n
                examples.append(dict(phase='departure', block=f'{c}{d}', lanes=a + b, who=[pa['id'], pb['id']]))
            if pa['assembly'] in ('P1', 'P2', 'P3', 'P4', 'P5'):
                ta, tb = b2_entry_t(pa), b2_entry_t(pb)
                n = _poly_cross(seg(pa, ta, pa['t']['assembly']), seg(pb, tb, pb['t']['assembly'])) if ta is not None and tb is not None else 0
                if n:
                    arr += n
                    examples.append(dict(phase='arrival', block=f'{c}{d}', lanes=a + b, who=[pa['id'], pb['id']]))
    return dict(departureCrossings=dep, arrivalCrossings=arr, examples=examples[:4])


def check_all(data):
    persons = data['persons']
    out = {}
    # 1. 碰撞
    st, wk = collisions(persons, data['meta']['tEnd'])
    out['collisions'] = dict(standing=len(st), walking=len(wk),
                             examples=[dict(kind='standing', who=[k, v[1]], t=v[0]) for k, v in list(st.items())[:3]] +
                                      [dict(kind='walking', who=list(k), t=t) for k, t in list(wk.items())[:3]])
    # 2. 逐序號巢狀
    seqs = {L: sorted((p for p in persons if p['lane'] == L), key=lambda p: p['laneIdx']) for L in plan.LANES}
    n = min(len(v) for v in seqs.values())
    bad = []
    for i in range(n):
        ranks = [plan.EXIT_RANK[seqs[L][i]['exit']] for L in plan.LANES]
        if not (ranks[0] < ranks[1] < ranks[2]):
            bad.append(dict(idx=i, exits={L: seqs[L][i]['exit'] for L in plan.LANES}))
    out['nesting'] = dict(violations=len(bad), indices=n, examples=bad[:3])
    # 2b. 指派性質（§3.3）：每路換口只往上游；每序號三路出口在三座不同階梯；零拆欄（同一列同一出口）
    upstream, segments = [], {}
    for L in plan.LANES:
        pairs_ = list(zip(seqs[L], seqs[L][1:]))
        upstream += [dict(lane=L, idx=a['laneIdx'] + 1, exits=[a['exit'], b['exit']]) for a, b in pairs_ if plan.EXIT_RANK[b['exit']] < plan.EXIT_RANK[a['exit']]]
        segments[L] = 1 + sum(1 for a, b in pairs_ if a['exit'] != b['exit'])
    stairs_bad = []
    for i in range(n):
        stairs = [plan.STAIR_OF[seqs[L][i]['exit']] for L in plan.LANES]
        if len(set(stairs)) < len(plan.LANES):
            stairs_bad.append(dict(idx=i, stairs=stairs))
    by_col = collections.defaultdict(set)
    for p in persons:
        by_col[p['lie']].add(p['exit'])
    split = sorted(lie for lie, es in by_col.items() if len(es) > 1)
    out['assignment'] = dict(upstreamViolations=len(upstream), distinctStairViolations=len(stairs_bad), splitColumns=len(split), segments=segments,
                             examples=upstream[:2] + stairs_bad[:2] + [dict(lie=lie, exits=sorted(by_col[lie])) for lie in split[:2]])
    # 2c. 路徑不交叉：同一大隊三路（回西一入口 / 進集結區）
    out['routes'] = lane_crossings(data)
    # 3. 不斷拍：西一入口六路、集結階段樓梯口三路、接尾者樓梯口三路
    gate = {}
    for j in range(6):
        ps = sorted((p for p in persons if p['gateLane'] == j), key=lambda p: p['gateIdx'])
        gate[str(j)] = _gaps(ps, 'gate', 'dadui')
    stair1, feeder = {}, {}
    for L in plan.LANES:
        ps = [p for p in seqs[L] if 'stairPlan' in p['t']]
        stair1[L] = _gaps([dict(p, _blk=p['costume'] + str(p['dadui'])) for p in ps], 'stairPlan', '_blk')
        fs = [p for p in seqs[L] if p['assembly'] == 'FEEDER']
        feeder[L] = _gaps(fs, 'enter', 'dadui')
    cont_ok = all(v['orderOk'] and (v['minGap'] is None or v['minGap'] >= GAP_MIN) and v['maxGapWithin'] <= GAP_MAX and v['maxGapBoundary'] <= BOUNDARY_MAX
                  for v in list(gate.values()) + list(stair1.values()) + list(feeder.values()))
    out['continuity'] = dict(gate=gate, stairPhase1=stair1, feederStairTop=feeder, ok=cont_ok)
    # 4. 座位：唯一、合法、休息區＝出口的區、每出口由上排往下且由出口側往中央、exits.order 名單就是該出口全員（依 exitSeq）
    keys = [(p['rest']['sec'], p['rest']['pai'], p['rest']['no']) for p in persons]
    kinds = {(s['sec'], s['pai'], s['no']): s['kind'] for s in data['restSeats']}
    illegal = sum(1 for k in keys if kinds.get(k) in plan.UNUSED_KINDS or kinds.get(k) is None or (k[0] == '139' and k[2] <= 5))
    wrong_sec = sum(1 for p in persons if p['rest']['sec'] != plan.EXIT_DEF[p['exit']]['sec'])
    by_exit = {e: sorted((p for p in persons if p['exit'] == e), key=lambda p: p['exitSeq']) for e in plan.EXITS}
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
    out['seats'] = dict(unique=len(set(keys)), population=len(persons), illegal=illegal, wrongSection=wrong_sec, orderViolations=order_bad, orderCoverage=coverage_bad)
    # 5. 候隊
    B1 = Poly(pairs(data['map']['b1Corridor']))
    def at_assembly(p):
        return next(q[:2] for q in p['path'] if abs(q[2] - p['t']['assembly']) < 1e-6)
    w3 = [p for p in persons if p['assembly'] == 'P6']
    tail_u = min(B1.proj(at_assembly(p))[0] for p in w3)
    entry140 = next(e['entryU'] for e in data['exits'] if e['key'] == '140')
    slots = {j: [tuple(q) for q in v] for j, v in data['stairSlots'].items()}
    w2 = [p for p in persons if p['assembly'] == 'STAIR']
    in_slots = all(min(math.dist(at_assembly(p), s) for s in slots[str(p['gateLane'])]) < 0.02 for p in w2)
    out['staging'] = dict(white3TailU=round(tail_u, 3), entry140U=entry140, white2InSlots=in_slots, ok=bool(tail_u - 0.1 >= entry140 and in_slots))
    # 6. 容量：用量由 persons 計、可用席由 restSeats 重算，再與 exits 欄位比對
    cap = {}
    for e in plan.EXITS:
        used, capacity = len(by_exit[e]), len(plan.usable_seats(data, e))
        f = listed.get(e, {})
        cap[e] = dict(used=used, capacity=capacity, fieldsOk=bool(f.get('used') == used and f.get('capacity') == capacity))
    out['capacity'] = cap
    out['ok'] = bool(not st and not wk and not bad and not upstream and not stairs_bad and not split and cont_ok
                     and out['routes']['departureCrossings'] == 0 == out['routes']['arrivalCrossings']
                     and len(set(keys)) == len(persons) == POPULATION and illegal == 0 and wrong_sec == 0 and order_bad == 0 and coverage_bad == 0
                     and out['staging']['ok'] and all(v['used'] <= v['capacity'] and v['fieldsOk'] for v in cap.values()))
    return out


def main(path):
    data = json.load(open(path, encoding='utf-8'))
    C = check_all(data)
    A, S, Rt = C['assignment'], C['seats'], C['routes']
    rows = [
        ('穿過站定者 / 走路互撞', f"{C['collisions']['standing']} / {C['collisions']['walking']}", '0 / 0', C['collisions']['standing'] == 0 == C['collisions']['walking']),
        ('逐序號巢狀違反', f"{C['nesting']['violations']} / {C['nesting']['indices']} 序號", '0', C['nesting']['violations'] == 0),
        ('指派：換口往下游 / 三路同階梯 / 拆欄', f"{A['upstreamViolations']} / {A['distinctStairViolations']} / {A['splitColumns']}（每路 {'、'.join(f'{L} {A['segments'][L]} 段' for L in plan.LANES)}）",
         '0 / 0 / 0', A['upstreamViolations'] == 0 == A['distinctStairViolations'] == A['splitColumns']),
        ('同一大隊三路路徑交叉（回西一入口 / 進集結區）', f"{Rt['departureCrossings']} / {Rt['arrivalCrossings']}", '0 / 0', Rt['departureCrossings'] == 0 == Rt['arrivalCrossings']),
        ('不斷拍（群內拍距 / 交界空檔）', '西一入口 ' + ', '.join(f"{v['minGap']}–{v['maxGapWithin']}" for v in C['continuity']['gate'].values()), f'{GAP_MIN}–{GAP_MAX}；交界 ≤ {BOUNDARY_MAX}', C['continuity']['ok']),
        ('座位唯一 / 違規席 / 區不符 / 順序違反 / 名單不符', f"{S['unique']} / {S['illegal']} / {S['wrongSection']} / {S['orderViolations']} / {S['orderCoverage']}", f'{POPULATION} / 0 / 0 / 0 / 0',
         S['unique'] == POPULATION and S['illegal'] == 0 == S['wrongSection'] == S['orderViolations'] == S['orderCoverage']),
        ('白3 隊尾 u − 0.1 ≥ 140 接入點 u；白2 在格位', f"{C['staging']['white3TailU']} vs {C['staging']['entry140U']}；{C['staging']['white2InSlots']}", '成立', C['staging']['ok']),
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
