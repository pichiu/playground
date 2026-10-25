import plan
import routes


def test_lane_offsets():
    assert routes.LANE_OFF == {'A': 0.12, 'B': -0.12}


def test_direct_route_shape(base):                       # 座位 → 樓梯 → B2 自己那條線的起點
    G = routes.Geometry(base)
    P = plan.build_plan(base)['people']
    for p in (P[0], P[-1]):
        pts = G.entry_route(p)
        k = G.stair_top_index(pts)
        assert k is not None and pts[-1] == G.line_poly(p['gateLane']).p[0]
        assert abs(G.B1.proj(pts[k])[1] - G.LANE_OFF[p['lane']]) < 1e-6
        assert pts[0] == (p['rest']['X'], p['rest']['Y'])


def test_no_assembly_geometry():
    assert not hasattr(routes, 'ZONES') and not hasattr(routes.Geometry, 'depart_route')


def test_stair_and_gate_map(base):
    G = routes.Geometry(base)
    m = G.stair_map()
    assert {'stair', 'stairBand', 'stairTreads', 'b1Corridor', 'b2Corridor'} <= set(m)
    assert len(G.gate_map()['doors']) == routes.GATE_DOORS == 4


def test_gate_lanes_map(base):                  # 下樓後到門前就是六路：圖面畫出六條線，從樓梯平台到隊頭，再接整排平移線穿過西一入口
    import build
    G = routes.Geometry(base)
    lanes = G.gate_lanes_map(build._lanes_after_queue(G))
    assert len(lanes) == 6
    M = build.march_of(G)
    for j, flat in enumerate(lanes):
        pts = list(zip(flat[::2], flat[1::2]))
        end = M.lane_xy(M.s_at_tau(M.tau_gate[j] + build.GATE_DRAW_AFTER), j)
        assert max(abs(a - round(b, 3)) for a, b in zip(pts[-1], end)) < 1e-6
        assert tuple(round(v, 3) for v in G.line_poly(j).p[-1]) in pts
        mid = [G.B2.proj(q) for q in pts if 1.5 < G.B2.proj(q)[0] < 3.5]
        assert mid and all(abs(o - (0.2 - 0.08 * j)) < 1e-3 for _, o, _ in mid)
    first = [tuple(G.ST_LANE[routes.LANE_OFF['A' if j < 3 else 'B']].at(G.ST_LANE[routes.LANE_OFF['A' if j < 3 else 'B']].L - 0.05)) for j in range(6)]
    assert all(abs(lanes[j][0] - round(first[j][0], 3)) < 1e-6 for j in range(6))
