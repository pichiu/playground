"""2c 檢核（spec §3.7）。build.py 也用 check_all 寫 meta.checks。

用法: python3 check.py ../data.json   → 印表；重算與 meta.checks 比對；未通過 exit 1
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


def check_all(data):
    persons = data['persons']
    P = {p['id']: p for p in persons}
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
    # 3. 不斷拍：6口 六路、集結階段樓梯口三路、接尾者樓梯口三路
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
    # 4. 座位
    keys = [(p['rest']['sec'], p['rest']['pai'], p['rest']['no']) for p in persons]
    kinds = {(s['sec'], s['pai'], s['no']): s['kind'] for s in data['restSeats']}
    illegal = sum(1 for k in keys if kinds.get(k) in plan.UNUSED_KINDS or kinds.get(k) is None or (k[0] == '139' and k[2] <= 5))
    order_bad = 0
    for e in data['exits']:
        q = [P[i] for i in e['order']]
        pais = [p['rest']['pai'] for p in q]
        if pais != sorted(pais, reverse=True):
            order_bad += 1
        for pai in set(pais):
            nos = [p['rest']['no'] for p in q if p['rest']['pai'] == pai]
            want = sorted(nos) if plan.EXIT_DEF[e['key']]['fill'] == 'asc' else sorted(nos, reverse=True)
            if nos != want:
                order_bad += 1
    out['seats'] = dict(unique=len(set(keys)), population=len(persons), illegal=illegal, orderViolations=order_bad)
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
    # 6. 容量
    out['capacity'] = {e['key']: dict(used=e['used'], capacity=e['capacity']) for e in data['exits']}
    out['ok'] = bool(not st and not wk and not bad and cont_ok and len(set(keys)) == len(persons) == 1609 and illegal == 0 and order_bad == 0
                     and out['staging']['ok'] and all(v['used'] <= v['capacity'] for v in out['capacity'].values()))
    return out


def main(path):
    data = json.load(open(path, encoding='utf-8'))
    C = check_all(data)
    rows = [
        ('穿過站定者 / 走路互撞', f"{C['collisions']['standing']} / {C['collisions']['walking']}", '0 / 0', C['collisions']['standing'] == 0 == C['collisions']['walking']),
        ('逐序號巢狀違反', f"{C['nesting']['violations']} / {C['nesting']['indices']} 序號", '0', C['nesting']['violations'] == 0),
        ('不斷拍（群內拍距 / 交界空檔）', '6口 ' + ', '.join(f"{v['minGap']}–{v['maxGapWithin']}" for v in C['continuity']['gate'].values()), f'{GAP_MIN}–{GAP_MAX}；交界 ≤ {BOUNDARY_MAX}', C['continuity']['ok']),
        ('座位唯一 / 違規席 / 順序違反', f"{C['seats']['unique']} / {C['seats']['illegal']} / {C['seats']['orderViolations']}", '1609 / 0 / 0', C['seats']['unique'] == 1609 and C['seats']['illegal'] == 0 and C['seats']['orderViolations'] == 0),
        ('白3 隊尾 u − 0.1 ≥ 140 接入點 u；白2 在格位', f"{C['staging']['white3TailU']} vs {C['staging']['entry140U']}；{C['staging']['white2InSlots']}", '成立', C['staging']['ok']),
        ('出口用量 ≤ 可用席', ', '.join(f"{k} {v['used']}/{v['capacity']}" for k, v in C['capacity'].items()), '成立', all(v['used'] <= v['capacity'] for v in C['capacity'].values())),
    ]
    for name, val, thr, ok in rows:
        print(f"[{'OK' if ok else 'NG'}] {name}: {val}（門檻 {thr}）")
    meta = data['meta'].get('checks') or {}
    same = bool(meta) and all(meta.get(k) == C.get(k) for k in ('collisions', 'nesting', 'seats', 'staging', 'capacity')) and meta.get('ok') == C['ok']
    print('meta.checks 與重算一致' if same else 'meta.checks 與重算不一致或缺少', '；', '通過' if C['ok'] and same else '未通過')
    return 0 if C['ok'] and same else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1]))
