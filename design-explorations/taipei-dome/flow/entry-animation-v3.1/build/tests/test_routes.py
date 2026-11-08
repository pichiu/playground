import plan
import routes


def test_lane_offsets():
    assert routes.LANE_OFF == {'A': 0.12, 'B': -0.12}


def test_entry_route_shape(base):                        # 座位 → 樓梯 → 通行帶 → 盡頭回頭：白衣在內圈，回頭後白衣 −0.04、藍衣 +0.04
    G = routes.Geometry(base)
    P = plan.build_plan(base)['people']
    for p in (P[0], P[-1]):
        pts = G.entry_route(p)
        k = G.stair_top_index(pts)
        assert k is not None and abs(G.B1.proj(pts[k])[1] - G.LANE_OFF[p['lane']]) < 1e-6
        assert pts[0] == (p['rest']['X'], p['rest']['Y'])
        u, o, _ = G.B2.proj(pts[-1])
        assert abs(o - (-0.04 if p['lane'] == 'A' else 0.04)) < 0.01 and abs(u - routes.UTURN_U) < 0.02
    for L in 'AB':                                       # 通行帶：入口帶到盡頭這一段在六路帶（±0.2）外
        mid = [G.B2.proj(q) for q in G.bypass(L) if routes.BYPASS_U <= G.B2.proj(q)[0] <= routes.UTURN_U]
        assert mid and all(abs(o - routes.BYPASS_OFF[L]) < 1e-3 for _, o, _ in mid)
    assert routes.UTURN_C - routes.BYPASS_OFF['A'] < routes.UTURN_C - routes.BYPASS_OFF['B']   # 白衣半徑小（內圈）


def test_no_assembly_geometry():
    assert not hasattr(routes, 'ZONES') and not hasattr(routes.Geometry, 'depart_route')


def test_stair_and_gate_map(base):
    G = routes.Geometry(base)
    m = G.stair_map()
    assert {'stair', 'stairBand', 'stairTreads', 'b1Corridor', 'b2Corridor'} <= set(m)
    assert len(G.gate_map()['doors']) == routes.GATE_DOORS == 4


def test_staging_map(base):                     # 圖面：九個集合位置、兩路、六路（散開 → 集合區 → 穿過西一入口之後 GATE_DRAW_AFTER 秒）
    import build
    G = routes.Geometry(base)
    people = plan.build_plan(base)['people']
    S, clocks = build.schedule(G, people)
    st = build.staging_map(G, clocks)
    assert [b['dadui'] for b in st['blocks']] == list(range(1, 10))
    assert all(a['uTail'] < b['uHead'] for a, b in zip(st['blocks'], st['blocks'][1:]))
    assert len(st['lanes']) == 6 and set(st['files']) == {'A', 'B'}
    M = build.march_of(G)
    for j, flat in enumerate(st['lanes']):
        end = M.lane_xy(M.s_at_tau(M.tau_gate[j] + build.GATE_DRAW_AFTER), j)
        assert max(abs(a - round(b, 3)) for a, b in zip(flat[-2:], end)) < 1e-6
