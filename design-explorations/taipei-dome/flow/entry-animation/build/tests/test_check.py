import json
import subprocess
import sys

import pytest

import check


@pytest.fixture(scope='session')
def built(pipeline):
    return pipeline


def test_check_all_green(built):
    tmp, D = built
    C = check.check_all(D)
    assert C['ok'], json.dumps({k: v for k, v in C.items() if k != 'capacity'}, ensure_ascii=False)[:3000]
    assert C['collisions']['standing'] == 0 == C['collisions']['walking'] and C['nesting']['violations'] == 0
    assert all(0.25 <= v['minGap'] and v['maxGapWithin'] <= 0.55 for v in C['continuity']['gate'].values())
    assert C['seats']['unique'] == 1609 and C['seats']['illegal'] == 0 and C['seats']['orderViolations'] == 0
    assert C['staging']['ok'] and all(v['used'] <= v['capacity'] and v['fieldsOk'] for v in C['capacity'].values())
    assert C['assignment']['upstreamViolations'] == 0 == C['assignment']['distinctStairViolations'] == C['assignment']['splitColumns']
    assert C['assignment']['segments'] == {'A': 3, 'B': 3, 'C': 3}
    assert C['seats']['wrongSection'] == 0 == C['seats']['orderCoverage']
    assert C['routes']['departureCrossings'] == 0 == C['routes']['arrivalCrossings']
    assert C['capacity']['139'] == dict(used=199, capacity=206, fieldsOk=True)
    assert D['meta']['checks']['ok'] is True and D['meta']['checks']['nesting'] == C['nesting'] and D['meta']['checks']['assignment'] == C['assignment']


def test_check_cli_exit_code(built):
    tmp, _ = built
    r = subprocess.run([sys.executable, 'check.py', str(tmp / 'data.json')], capture_output=True, text=True, cwd=check.__file__.rsplit('/', 1)[0])
    assert r.returncode == 0, r.stdout + r.stderr
    assert '通過' in r.stdout


def test_check_detects_tampering(built):
    _, D = built
    D = json.loads(json.dumps(D))
    a = next(p for p in D['persons'] if p['lane'] == 'A' and p['laneIdx'] == 0)
    c = next(p for p in D['persons'] if p['lane'] == 'C' and p['laneIdx'] == 0)
    a['exit'], c['exit'] = c['exit'], a['exit']
    C = check.check_all(D)
    assert C['nesting']['violations'] > 0 and C['ok'] is False


def _copy(D):
    return json.loads(json.dumps(D))


def test_check_recomputes_capacity_not_trusting_fields(built):
    _, D = built
    D = _copy(D)
    e = next(e for e in D['exits'] if e['key'] == '140')
    e['used'], e['capacity'] = 1, 9999
    C = check.check_all(D)
    assert C['capacity']['140']['used'] == 282 and C['capacity']['140']['capacity'] == 291   # 由 persons / restSeats 重算
    assert C['capacity']['140']['fieldsOk'] is False and C['ok'] is False


def test_check_detects_same_stair_supply(built):
    # B 路序號 0 的出口 141 → 140：巢狀 139 < 140 < 142 仍成立，但 139 與 140 是同一座階梯
    _, D = built
    D = _copy(D)
    b = next(p for p in D['persons'] if p['lane'] == 'B' and p['laneIdx'] == 0)
    assert b['exit'] == '141'
    b['exit'] = '140'
    C = check.check_all(D)
    assert C['nesting']['violations'] == 0 and C['assignment']['distinctStairViolations'] == 1 and C['ok'] is False


def test_check_detects_downstream_switch_and_split_column(built):
    # A 路最後一位（白9，141）改回 139：巢狀仍成立，但換口往下游，而且那一列被拆成兩個出口
    _, D = built
    D = _copy(D)
    a = max((p for p in D['persons'] if p['lane'] == 'A'), key=lambda p: p['laneIdx'])
    assert a['exit'] == '141'
    a['exit'] = '139'
    C = check.check_all(D)
    assert C['assignment']['upstreamViolations'] == 1 and C['assignment']['splitColumns'] == 1
    assert C['seats']['wrongSection'] == 1 and C['ok'] is False


def test_check_detects_order_list_tampering(built):
    _, D = built
    D = _copy(D)
    e = next(e for e in D['exits'] if e['key'] == '145')
    e['order'] = e['order'][:-1]
    C = check.check_all(D)
    assert C['seats']['orderCoverage'] == 1 and C['ok'] is False


def test_check_detects_lane_crossing_at_gate(built):
    # 把藍4 A 路頭一位回 6口 的路段推到走廊外側（−0.30），最後一段斜進自己的場內線就會穿過 B、C 兩路 → 幾何交叉
    from geo import Poly, pairs
    _, D = built
    D = _copy(D)
    B2 = Poly(pairs(D['map']['b2Corridor']))
    a = next(p for p in D['persons'] if p['costume'] == '藍' and p['dadui'] == 4 and p['lane'] == 'A' and p['slot'] == 0)
    for q in a['path']:
        if a['t']['enter'] <= q[2] < a['t']['gate'] - 0.3:
            q[0], q[1] = B2.off(B2.proj(q[:2])[0], -0.30)
    C = check.check_all(D)
    assert C['routes']['departureCrossings'] >= 2 and C['ok'] is False
