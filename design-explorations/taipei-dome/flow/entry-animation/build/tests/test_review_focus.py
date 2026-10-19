"""Review Focus 1–3（plan 的 Review Focus 節）。"""
import json
import math
import subprocess
import sys

import pytest


@pytest.fixture(scope='session')
def data(pipeline):
    _, D = pipeline
    D = json.loads(json.dumps(D))
    D['P'] = {p['id']: p for p in D['persons']}
    D['exits_by_key'] = {e['key']: e for e in D['exits']}
    return D


def t_at(p, xy):
    """路徑上最接近 xy 的點的時刻。"""
    return min(p['path'], key=lambda q: (q[0] - xy[0]) ** 2 + (q[1] - xy[1]) ** 2)[2]


def pos_at(p, t):
    a = p['path']
    for q, r in zip(a, a[1:]):
        if q[2] <= t <= r[2]:
            f = 0 if r[2] == q[2] else (t - q[2]) / (r[2] - q[2])
            return (q[0] + (r[0] - q[0]) * f, q[1] + (r[1] - q[1]) * f)
    return a[-1][:2]


def test_no_row_overtake(data):   # Review Focus 1：下排第一位離開自己走道口上階梯時，上排最後一位已先離開其走道口，且已走開 ≥ 0.3 單位（不追撞、不插隊）
    P = data['P']
    for e in data['exits']:
        order = [P[i] for i in e['order']]
        for a, b in zip(order, order[1:]):
            if a['rest']['pai'] != b['rest']['pai']:
                tb = t_at(b, b['path'][1][:2])
                ta = t_at(a, a['path'][1][:2])
                assert tb - ta >= 0.2, (a['id'], b['id'], tb - ta)
                assert math.dist(pos_at(a, tb), b['path'][1][:2]) >= 0.3, (a['id'], b['id'])


def test_white3_tail_clear_before_white4(data):   # Review Focus 2：白4 A 第一位進走廊時，白3 A 最後一位已起步 0.2 秒以上
    P = data['P']
    w3A = max((p for p in P.values() if p['dadui'] == 3 and p['costume'] == '白' and p['lane'] == 'A'), key=lambda p: p['laneIdx'])
    w4A = min((p for p in P.values() if p['dadui'] == 4 and p['costume'] == '白' and p['lane'] == 'A'), key=lambda p: p['laneIdx'])
    assert t_at(w4A, data['exits_by_key']['140']['entry']) > w3A['t']['enter'] + 0.2


def test_p1_white_blue_clearance(data):   # Review Focus 3：白1 C 路進集結區 1 的最後三秒，與藍1 站定點距離 ≥ 0.05
    P = data['P']
    blue1 = [q[:2] for p in P.values() if p['dadui'] == 1 and p['costume'] == '藍' for q in p['path'] if abs(q[2] - p['t']['assembly']) < 1e-6]
    assert blue1
    for p in (p for p in P.values() if p['dadui'] == 1 and p['costume'] == '白' and p['lane'] == 'C'):
        for q in p['path']:
            if p['t']['assembly'] - 3 < q[2] < p['t']['assembly']:
                assert min(math.dist(q[:2], b) for b in blue1) >= 0.05, (p['id'], q)
