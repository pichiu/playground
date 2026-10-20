import math
import plan
import routes


def test_zone_regions_disjoint(base):
    G = routes.Geometry(base)
    G.regions()   # 內部 assert：同一走廊上的集結區不重疊
    assert 'P7' not in G.ZONES and G.ZONES['P6']['head'] <= 12.75 and G.ZONES['P6']['step'] < 0


def test_white3_tail_downstream_of_140(base):
    G = routes.Geometry(base)
    P = plan.build_plan(base)['people']
    w3 = [p for p in P if p['block'] == '白3']
    n_lane = {L: sum(1 for q in w3 if q['lane'] == L) for L in 'ABC'}          # 30/29/29
    tail = min(G.slot_u(p, n_lane[p['lane']] - 1) for p in w3)
    entry140_u = G.B1.proj(tuple(plan.entry_point(base, '140')))[0]        # ≈ 10.96
    assert tail - 0.1 >= entry140_u


def test_routes_start_and_end(base):
    G = routes.Geometry(base)
    P = plan.build_plan(base)['people']
    for p in P[::37]:
        pts = G.arrival_route(p, 0)
        assert tuple(pts[0]) == (p['rest']['X'], p['rest']['Y'])
        assert tuple(pts[1]) == tuple(p['aisle']) and tuple(pts[len(p['approach'])]) == tuple(p['entry'])
        if p['assembly'] == 'FEEDER':
            assert math.dist(pts[-1], G.GATE_PTS[p['gateLane']]) < 1e-6 and G.depart_route(p, 0) == []
        else:
            assert math.dist(pts[-1], G.slot_xy(p, 0)) < 1e-6
            dep = G.depart_route(p, 0)
            end = G.gate_join(p['gateLane'], -0.04 - 0.08 * (5 - p['gateLane']))[-1] if p['assembly'] in plan.LIFO_ZONES else G.GATE_PTS[p['gateLane']]
            assert math.dist(dep[0], G.slot_xy(p, 0)) < 1e-6 and math.dist(dep[-1], end) < 1e-6


def test_stair_slots_fit_white2(base):
    G = routes.Geometry(base)
    assert all(len(G.STAIR_SLOTS[j]) >= 33 for j in range(3))


def test_lane_offsets_and_stair_top(base):
    G = routes.Geometry(base)
    assert G.LANE_OFF == {'A': 0.12, 'B': 0.0, 'C': -0.12}
    P = plan.build_plan(base)['people']
    feeder = next(p for p in P if p['assembly'] == 'FEEDER')
    pts = G.arrival_route(feeder, 0)
    k = G.stair_top_index(pts)
    assert k is not None and 2 < k < len(pts) - 1
    assert math.dist(pts[k], G.B1.off(routes.STAIR_U_B1, G.LANE_OFF[feeder['lane']])) < 1e-6   # 2c：B1 走道上到樓梯口都走自己那一路，不側移
    blue = next(p for p in P if p['block'] == '藍9' and p['lane'] == 'A')
    assert G.stair_top_index(G.arrival_route(blue, 0)) is not None


def _cross(a, b):
    def c(o, p, q):
        return (p[0] - o[0]) * (q[1] - o[1]) - (p[1] - o[1]) * (q[0] - o[0])
    return any((c(s2[0], s2[1], s1[0]) > 0) != (c(s2[0], s2[1], s1[1]) > 0) and (c(s1[0], s1[1], s2[0]) > 0) != (c(s1[0], s1[1], s2[1]) > 0)
               for s1 in zip(a, a[1:]) for s2 in zip(b, b[1:]))


def test_dead_end_lanes_mirrored_and_gate_routes_do_not_cross(base):
    """藍2–9 從死巷反向走回 6口：最靠場側（−0.04）的是最先轉進場的 j=5（A 路），三路的回程與進區路徑兩兩不交叉。"""
    G = routes.Geometry(base)
    P = plan.build_plan(base)['people']
    for blk, first in (('藍4', True), ('藍5', False), ('藍2', True), ('藍9', False)):
        heads = {L: next(p for p in P if p['block'] == blk and p['lane'] == L) for L in 'ABC'}
        offs = {L: round(G.slot_offset(heads[L]), 3) for L in 'ABC'}
        assert offs == ({'A': -0.04, 'B': -0.12, 'C': -0.2} if first else {'A': 0.2, 'B': 0.12, 'C': 0.04}), (blk, offs)
        assert [heads[L]['gateLane'] for L in 'ABC'] == [5, 4, 3]
        dep = {L: G.depart_route(heads[L], 0) for L in 'ABC'}
        arr = {L: G.arrival_route(heads[L], 0) for L in 'ABC'}
        for a, b in (('A', 'B'), ('A', 'C'), ('B', 'C')):
            assert not _cross(dep[a], dep[b]), (blk, a, b, '回 6口 交叉')
            k = min(len(arr[a]), len(arr[b]))
            assert not _cross(arr[a][-k // 2:], arr[b][-k // 2:]), (blk, a, b, '進區交叉')
        # j=3 的回程經過 GATE_PTS[3]（從外側走到線上再橫越），j=5 從線上場側那一點直接進場，不回頭
        assert math.dist(dep['C'][-1], G.GATE_PTS[3]) < 1e-6 and math.dist(dep['C'][-2], G.B2.off(G.B2.proj(G.GATE_PTS[3])[0], -0.2)) < 0.02
        assert math.dist(dep['A'][-1], G.B2.off(G.B2.proj(G.GATE_PTS[5])[0], -0.04)) < 0.02
