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
            assert math.dist(dep[0], G.slot_xy(p, 0)) < 1e-6 and math.dist(dep[-1], G.GATE_PTS[p['gateLane']]) < 1e-6


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
