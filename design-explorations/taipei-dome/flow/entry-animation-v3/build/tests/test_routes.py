import plan
import routes


def test_lane_offsets():
    assert routes.LANE_OFF == {'A': 0.12, 'B': -0.12}


def test_direct_route_shape(base):
    G = routes.Geometry(base)
    P = plan.build_plan(base)['people']
    for p in (P[0], P[-1]):
        pts = G.arrival_route(p)
        k = G.stair_top_index(pts)
        assert k is not None and pts[-1] == G.GATE_PTS[p['gateLane']]
        assert abs(G.B1.proj(pts[k])[1] - G.LANE_OFF[p['lane']]) < 1e-6
        assert pts[0] == (p['rest']['X'], p['rest']['Y'])


def test_no_assembly_geometry():
    assert not hasattr(routes, 'ZONES') and not hasattr(routes.Geometry, 'depart_route')


def test_stair_and_gate_map(base):
    G = routes.Geometry(base)
    m = G.stair_map()
    assert {'stair', 'stairBand', 'stairTreads', 'b1Corridor', 'b2Corridor'} <= set(m)
    assert len(G.gate_map()['doors']) == routes.GATE_DOORS == 4
