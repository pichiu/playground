"""整排並肩（wheel turn）的中心線、六條平移線與分出點。"""
import math

import build
import check
import march
import plan
import routes


def _m(base):
    G = routes.Geometry(base)
    return G, build.march_of(G)


def test_starts_at_stage_deep_end(base):              # 版本 3.1：中心線起點（s = 0）在集合區最深處；六路在 B2 偏移 −0.2 + 0.08j（面向西一入口時 lane 0 在左＝走廊外側）
    G, M = _m(base)
    for j in range(6):
        u, o, _ = G.B2.proj(M.lane_xy(0.0, j))
        assert abs(u - routes.STAGE_START_U) < 0.02 and abs(o - routes.stage_off(j)) < 0.01


def test_lane0_always_left(base):                       # lane 0 永遠在行進方向左側：集合區在走廊外側、門洞裡在北、北行時在西
    G, M = _m(base)
    for s in M.ss[::50]:
        x, y, tx, ty, _ = M.C.at(s)
        offs = [(q[0] - x) * ty - (q[1] - y) * tx for q in (M.lane_xy(s, j) for j in range(6))]
        assert all(a > b for a, b in zip(offs, offs[1:]))
    s_g = M.s_at_tau(sum(M.tau_gate) / 6)               # 門洞（往東）：lane 0 在北（y 小）
    assert M.lane_xy(s_g, 0)[1] < M.lane_xy(s_g, 5)[1]
    s_n = next(s for s in M.ss if M.C.at(s)[3] < -0.999 and M.C.at(s)[1] < 5)
    assert M.lane_xy(s_n, 0)[0] < M.lane_xy(s_n, 5)[0]  # 北行：lane 0 在西


def test_spacing_profile(base):                         # 隊伍、門洞、沿牆 0.08；北轉時漸變；北行 0.1316（座位列距）
    G, M = _m(base)
    assert M.sp(0) == march.SP_QUEUE and M.sp(M.s_walk + 1.0) == march.SP_QUEUE and M.sp(M.C.L) == march.SP_SEAT
    assert M.sp0 < M.sp1 and all(M.sp(a) <= M.sp(b) + 1e-12 for a, b in zip(M.ss, M.ss[1:]))


def test_wheel_turns(base):                             # 外圈不超過步速、內圈半徑 ≥ 0.08、內圈不倒退；直線段六人都是步速
    G, M = _m(base)
    W = check.wheel({'map': {'march': march.export(M, {1: M.C.L}, {1: 0.0})}})
    assert W['violations'] == 0 and W['maxSpeed'] <= build.V + check.SPEED_EPS and W['minInnerR'] >= march.INNER_MIN and W['minInnerSpeed'] > 0
    assert W['turns'] >= 5
    straight = [k for k in range(1, len(M.ss)) if M.C.at(M.ss[k - 1])[4] == 0 == M.C.at(M.ss[k])[4] and M.sp(M.ss[k - 1]) == M.sp(M.ss[k])]
    k = straight[len(straight) // 2]
    dt = M.tau[k] - M.tau[k - 1]
    assert all(abs(math.dist(M.lane_xy(M.ss[k - 1], j), M.lane_xy(M.ss[k], j)) / dt - build.V) < 1e-6 for j in range(6))


def test_gate_crossing_in_band(base):                  # 六條線都只在西一入口門洞穿過全壘打牆
    G, M = _m(base)
    t1 = M.tau_at_s(M.s_gate_arc)
    assert all(0 < t - t1 < 3 for t in M.tau_gate)
    assert M.tau_gate == sorted(M.tau_gate)             # 牆線在門洞是斜的：北側的 lane 0 先穿過（右轉進門後整排已轉正）


def test_splits_south_of_rows(base):                    # 每個大隊在自己列區南緣分出；後面的大隊分得早（更南），不會經過前面大隊的列
    G, M = _m(base)
    people = plan.build_plan(base)['people']
    sp = build.split_points(G, people)
    ys = {}
    for d, s in sp.items():
        y_south = max(p['field']['Y'] for p in people if p['dadui'] == d)
        x_front = min(p['field']['X'] for p in people if p['dadui'] == d)
        ys[d] = min(M.lane_xy(s, j)[1] for j in range(6))
        if M.C.at(s)[3] >= -0.2:                        # 沿牆段就分出（大隊 9）：六人都還在所有座位的西側
            assert all(M.lane_xy(s, j)[0] < x_front - march.GAP_H for j in range(6))
        else:                                           # 北行段分出：在最南一列之南、正北、六路在欄間空隙
            assert all(M.lane_xy(s, j)[1] > y_south + march.GAP_H - 1e-9 for j in range(6))
            assert abs(M.C.at(s)[2]) < 1e-9
            for j in range(6):
                k = (M.lane_xy(s, j)[0] - march.SEAT_X0) / march.SP_SEAT
                assert abs(k - math.floor(k) - 0.5) < 1e-6
    assert all(ys[d] < ys[d + 1] for d in range(1, 9))
    assert all(sp[d] > sp[d + 1] for d in range(1, 9))


def test_lane_to_row(base):                             # lane j → 列 6k−5+j：lane 0 對到大隊第一列（Y 最小）
    people = plan.build_plan(base)['people']
    for p in people:
        assert p['lie'] == 6 * (p['dadui'] - 1) + p['gateLane'] + 1
    for d in range(1, 10):
        ys = [min(p['field']['Y'] for p in people if p['dadui'] == d and p['gateLane'] == j) for j in range(6)]
        assert ys == sorted(ys)
