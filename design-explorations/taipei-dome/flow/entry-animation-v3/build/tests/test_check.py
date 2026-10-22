import json
import subprocess
import sys

import pytest

import build
import check


@pytest.fixture(scope='session')
def built(pipeline):
    return pipeline


def _copy(D):
    return json.loads(json.dumps(D))


def test_check_all_green(built):
    _, D = built
    C = check.check_all(D)
    assert C['ok'], json.dumps({k: v for k, v in C.items() if k != 'capacity'}, ensure_ascii=False)[:3000]
    assert C['collisions']['standing'] == 0 == C['collisions']['walking']
    assert C['nesting'] == dict(violations=0, sameStair=0, examples=[])
    A = C['assignment']
    assert A['upstreamViolations'] == 0 == A['notFullSwitches'] and A['segments'] == {'A': 4, 'B': 4} and A['splitColumns'] == 18
    assert C['routes']['crossings'] == 0 and C['waits']['violations'] == 0 and C['doorQueue']['violations'] == 0
    assert C['seats']['unique'] == 1609 and C['seats']['illegal'] == 0 == C['seats']['orderViolations'] == C['seats']['wrongSection'] == C['seats']['orderCoverage']
    assert C['capacity']['142'] == dict(used=255, capacity=255, fieldsOk=True)
    assert all(v['minGap'] >= check.GAP_MIN and v['maxGapWithin'] <= check.GAP_MAX and v['maxGapBoundary'] <= check.BOUNDARY_MAX for v in C['continuity']['stair'].values())
    assert all(v['minGap'] >= 0.25 and v['maxGapWithin'] <= check.GATE_GAP_MAX and v['maxGapBoundary'] <= 12 for v in C['continuity']['gate'].values())
    assert D['meta']['checks']['ok'] is True and all(D['meta']['checks'][k] == C[k] for k in check.COMPARED)


def test_boundary_gap_matches_rule(built):          # Review Focus 4
    _, D = built
    n = {(L, d): sum(1 for p in D['persons'] if p['lane'] == L and p['dadui'] == d) for L in 'AB' for d in range(1, 10)}
    for L in 'AB':
        ps = sorted((p for p in D['persons'] if p['lane'] == L), key=lambda p: p['laneIdx'])
        for a, b in zip(ps, ps[1:]):
            if a['dadui'] != b['dadui']:
                d = a['dadui']
                rule = build.HEADWAY * (max(n[('A', d)], n[('B', d)]) - n[(L, d)]) + build.HEADWAY + build.DADUI_GAP
                assert b['t']['stair'] - a['t']['stair'] <= rule + 0.4 + 1e-6
                assert rule <= check.BOUNDARY_MAX


def test_check_cli_exit_code(built):
    tmp, _ = built
    r = subprocess.run([sys.executable, 'check.py', str(tmp / 'data.json')], capture_output=True, text=True, cwd=check.__file__.rsplit('/', 1)[0])
    assert r.returncode == 0, r.stdout + r.stderr
    assert '通過' in r.stdout


def test_check_detects_nesting_swap(built):
    _, D = built
    D = _copy(D)
    a = next(p for p in D['persons'] if p['lane'] == 'A' and p['laneIdx'] == 0)
    b = next(p for p in D['persons'] if p['lane'] == 'B' and p['laneIdx'] == 0)
    a['exit'], b['exit'] = b['exit'], a['exit']
    C = check.check_all(D)
    assert C['nesting']['violations'] > 0 and C['ok'] is False


def test_check_detects_same_stair(built):
    _, D = built
    D = _copy(D)
    b = next(p for p in D['persons'] if p['lane'] == 'B' and p['laneIdx'] == 0)
    assert b['exit'] == '142'
    b['exit'] = '140'                # 139 與 140 同一座階梯；rank 仍是 A < B
    C = check.check_all(D)
    assert C['nesting']['sameStair'] > 0 and C['ok'] is False


def test_check_detects_early_switch(built):
    # A 路 139 段最後一位改成 140：139 還有空席就換口
    _, D = built
    D = _copy(D)
    a = max((p for p in D['persons'] if p['lane'] == 'A' and p['exit'] == '139'), key=lambda p: p['laneIdx'])
    a['exit'] = '140'
    C = check.check_all(D)
    assert C['assignment']['notFullSwitches'] > 0 and C['ok'] is False


def test_check_detects_downstream_switch(built):
    _, D = built
    D = _copy(D)
    a = max((p for p in D['persons'] if p['lane'] == 'A'), key=lambda p: p['laneIdx'])
    a['exit'] = '139'
    C = check.check_all(D)
    assert C['assignment']['upstreamViolations'] == 1 and C['ok'] is False


def test_check_detects_wait_outside_queue(built):     # 只能在門前自己的位置等：在 B1 走廊停一下就算違反
    _, D = built
    D = _copy(D)
    p = D['persons'][10]
    k = 4
    q = p['path'][k]
    p['path'].insert(k + 1, [q[0], q[1], q[2] + 1.0])
    for r in p['path'][k + 2:]:
        r[2] += 1.0
    for key in ('stair', 'assembly', 'enter', 'gate', 'arrive'):
        p['t'][key] += 1.0
    C = check.check_all(D)
    assert C['waits']['violations'] >= 1 and C['ok'] is False



def test_check_recomputes_capacity_not_trusting_fields(built):
    _, D = built
    D = _copy(D)
    e = next(e for e in D['exits'] if e['key'] == '140')
    e['used'], e['capacity'] = 1, 9999
    C = check.check_all(D)
    assert C['capacity']['140']['used'] == 291 and C['capacity']['140']['capacity'] == 291
    assert C['capacity']['140']['fieldsOk'] is False and C['ok'] is False


def test_check_detects_order_list_tampering(built):
    _, D = built
    D = _copy(D)
    e = next(e for e in D['exits'] if e['key'] == '145')
    e['order'] = e['order'][:-1]
    C = check.check_all(D)
    assert C['seats']['orderCoverage'] == 1 and C['ok'] is False


def test_check_detects_lane_crossing(built):
    # 把大隊 4 白衣 j=0 頭一位在 B2 的路段推到藍衣那一側（−0.30）：會穿過藍衣三條線的頭一位
    from geo import Poly, pairs
    _, D = built
    D = _copy(D)
    B2 = Poly(pairs(D['map']['b2Corridor']))
    a = min((p for p in D['persons'] if p['dadui'] == 4 and p['gateLane'] == 0), key=lambda p: p['gateIdx'])
    for q in a['path']:
        u, o, dist = B2.proj(q[:2])
        if a['t']['stair'] + 0.8 <= q[2] < a['t']['gate'] - 0.3 and dist < 0.3:
            q[0], q[1] = B2.off(u, -0.30)
    C = check.check_all(D)
    assert C['routes']['crossings'] > 0 and C['ok'] is False


def test_check_enforces_boundary_rule(built):          # final review：交界空檔要等於規則值，不只是 ≤ 7 秒
    _, D = built
    D = _copy(D)
    for p in D['persons']:
        if p['lane'] == 'B' and p['dadui'] >= 3:
            p['t']['stair'] += 3.0
    C = check.check_all(D)
    assert C['continuity']['stair']['B']['maxGapBoundary'] < check.BOUNDARY_MAX
    assert C['continuity']['boundaryRuleViolations'] >= 1 and C['continuity']['ok'] is False and C['ok'] is False


def test_check_detects_slow_segment(built):            # 放慢某一段（不重複點）也算等
    _, D = built
    D = _copy(D)
    p = D['persons'][30]
    k = len(p['path']) - 3
    for q in p['path'][k:]:
        q[2] += 1.0
    p['t']['arrive'] = p['path'][-1][2]
    C = check.check_all(D)
    assert C['waits']['violations'] >= 1 and C['ok'] is False


def test_check_door_queue_tamper(built):                # 門前切齊：把某一大隊某條線的隊頭往後挪，就不齊了
    _, D = built
    C = check.check_all(D)
    assert C['doorQueue']['violations'] == 0 and C['doorQueue']['firstBatch'] == 60 and C['doorQueue']['laterWaiting'] == 0
    D = _copy(D)
    p = next(q for q in D['persons'] if q['dadui'] == 1 and q['slot'] == 0 and q['gateLane'] == 3)
    for q in p['path']:
        if p['t']['assembly'] - 1e-6 <= q[2] <= p['t']['enter'] + 1e-6:
            q[0] += 0.2
    C = check.check_all(D)
    assert C['doorQueue']['violations'] >= 1 and C['ok'] is False


def test_check_bounds_gate_gap_between_dadui(built):    # review：西一入口兩個大隊之間不能空太久
    _, D = built
    D = _copy(D)
    for p in D['persons']:
        if p['dadui'] >= 5:
            for k in ('enter', 'gate'):
                p['t'][k] += 120
    C = check.check_all(D)
    assert C['continuity']['ok'] is False and C['ok'] is False


def test_check_detects_later_wait(built):              # 一路接續：頭一批以外的人在門前停超過 1 秒就算違反
    _, D = built
    D = _copy(D)
    p = next(q for q in D['persons'] if q['dadui'] == 5 and q['slot'] == 3)
    k = next(i for i, q in enumerate(p['path']) if abs(q[2] - p['t']['enter']) < 1e-6)
    q = p['path'][k]
    p['path'].insert(k + 1, [q[0], q[1], q[2] + 3.0])
    for r in p['path'][k + 2:]:
        r[2] += 3.0
    for key in ('enter', 'gate', 'arrive'):
        p['t'][key] += 3.0
    C = check.check_all(D)
    assert C['doorQueue']['laterWaiting'] >= 1 and C['ok'] is False

