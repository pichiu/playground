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


def test_starts_at_queue_head(base):                    # t.enter 那一刻六人就在門前隊伍隊頭：t.enter 以前的位置不動
    G, M = _m(base)
    for j in range(6):
        assert math.dist(M.lane_xy(0.0, j), G.line_poly(j).p[-1]) < 1e-9


def test_lane0_always_left(base):                       # lane 0 永遠在行進方向左側：隊伍裡在東、門洞裡在北、北行時在西
    G, M = _m(base)
    for s in M.ss[::50]:
        x, y, tx, ty, _ = M.C.at(s)
        offs = [(q[0] - x) * ty - (q[1] - y) * tx for q in (M.lane_xy(s, j) for j in range(6))]
        assert all(a > b for a, b in zip(offs, offs[1:]))
    q = [G.line_poly(j).p[-1] for j in range(6)]
    assert q[0][0] > q[5][0]                            # 隊伍（面南）：lane 0 在東
    s_n = next(s for s in M.ss if M.C.at(s)[3] < -0.999 and M.C.at(s)[1] < 5)
    assert M.lane_xy(s_n, 0)[0] < M.lane_xy(s_n, 5)[0]  # 北行：lane 0 在西


def test_spacing_profile(base):                         # 隊伍、門洞、沿牆 0.08；北轉時漸變；北行 0.1316（座位列距）
    G, M = _m(base)
    assert M.sp(0) == march.SP_QUEUE and M.sp(M.s_walk + 1.0) == march.SP_QUEUE and M.sp(M.C.L) == march.SP_SEAT
    assert M.sp0 < M.sp1 and all(M.sp(a) <= M.sp(b) + 1e-12 for a, b in zip(M.ss, M.ss[1:]))


def test_wheel_turns(base):                             # 外圈不超過步速、內圈半徑 ≥ 0.08、內圈不倒退；直線段六人都是步速
    G, M = _m(base)
    W = check.wheel({'map': {'march': march.export(M, {1: M.C.L})}})
    assert W['violations'] == 0 and W['maxSpeed'] <= build.V + check.SPEED_EPS and W['minInnerR'] >= march.INNER_MIN and W['minInnerSpeed'] > 0
    assert W['turns'] >= 5
    straight = [k for k in range(1, len(M.ss)) if M.C.at(M.ss[k - 1])[4] == 0 == M.C.at(M.ss[k])[4] and M.sp(M.ss[k - 1]) == M.sp(M.ss[k])]
    k = straight[len(straight) // 2]
    dt = M.tau[k] - M.tau[k - 1]
    assert all(abs(math.dist(M.lane_xy(M.ss[k - 1], j), M.lane_xy(M.ss[k], j)) / dt - build.V) < 1e-6 for j in range(6))


def test_gate_crossing_in_band(base):                  # 六條線都只在西一入口門洞穿過全壘打牆
    G, M = _m(base)
    assert all(0 < t < 3 for t in M.tau_gate)
    assert M.tau_gate == sorted(M.tau_gate)             # 左轉進門：內圈 lane 0 先穿過牆線


def test_splits_south_of_rows(base):                    # 每個大隊（含大隊 9）都在北行直線上、自己列區南緣分出；後面的大隊分得早（更南）
    G, M = _m(base)
    people = plan.build_plan(base)['people']
    sp = build.split_points(G, people)
    ys = {}
    for d, s in sp.items():
        y_south = max(p['field']['Y'] for p in people if p['dadui'] == d)
        ys[d] = min(M.lane_xy(s, j)[1] for j in range(6))
        x, y, tx, ty, _ = M.C.at(s)
        assert s >= M.sp1 - 1e-9 and abs(tx) < 1e-9 and ty < march.NORTH_TY      # 正北直線上（北轉弧之後）
        assert all(M.lane_xy(s, j)[1] > y_south + march.GAP_H - 1e-9 for j in range(6))
        for j in range(6):                                                         # 六路在第 5–10 排東側的欄間空隙
            k = (M.lane_xy(s, j)[0] - march.SEAT_X0) / march.SP_SEAT
            assert abs(k - (4.5 + j)) < 1e-6
    assert all(ys[d] < ys[d + 1] for d in range(1, 9))
    assert all(sp[d] > sp[d + 1] for d in range(1, 9))


def test_north_line_off_stage(base):                    # 北行直線上六路全程在地面：離舞台線稿 ≥ STAGE_MIN、不跨任何舞台線
    G, M = _m(base)
    for s in M.ss:
        if s < M.sp1:
            continue
        for j in range(6):
            assert M.stage_clear(M.lane_xy(s, j)) >= march.STAGE_MIN


def _plan_min(ax, yg, xs, pl):
    """west_plan 的走法在格點人流裡的最近距離（和 west_plan 用同一個模型重算）。"""
    lane = int(round((ax - march.NORTH_X) / march.SP_SEAT + 2.5))
    n = min(lane, int(round((ax - xs) / march.SP_SEAT - 0.5)))
    cols = [ax - k * march.SP_SEAT for k in range(n + 1)]
    pts, t, best = [(ax, yg, 1.0)] + list(pl), 0.0, 9.0
    for a, b in zip(pts, pts[1:]):
        t1 = t + math.dist(a[:2], b[:2]) / (march.V * b[2])
        best = min(best, march._seg_min(a[:2], t, b[:2], t1, cols, yg))
        t = t1
    return best


def test_west_plan_dodges_flow():                       # 往西進列：各路、各種橫越欄數都和人流保持 > 0.03（碰撞點距），且只在列間空隙裡偏移
    yg = 5.0
    for lane in range(6):
        ax = march.NORTH_X + (lane - 2.5) * march.SP_SEAT
        for cols in range(0, 9):
            xs = ax - (cols + 0.5) * march.SP_SEAT
            pl = march.west_plan(ax, yg, xs)
            assert pl[-1][:2] == (xs, yg)                                         # 終點在座位正南方的列間空隙
            assert all(abs(q[1] - yg) <= 0.03 + 1e-9 for q in pl)                 # 離座位列至少 GAP_H − 0.03
            assert all(a[0] > b[0] for a, b in zip([(ax, yg)] + pl, pl))          # 一路往西
            assert all(0.7 - 1e-9 <= q[2] <= 1.0 for q in pl)
            assert all(q[2] == 1.0 for a, q in zip([(ax, yg)] + pl, pl) if abs(q[1] - a[1]) > 1e-9)   # 斜的那段走步速
            assert _plan_min(ax, yg, xs, pl) > 0.035


def test_west_plan_needs_offsets():                     # 等速直走過 5 條有人流的空隙一定撞（這就是 west_plan 存在的理由）
    ax, yg = march.NORTH_X + 2.5 * march.SP_SEAT, 5.0
    xs = ax - 5.5 * march.SP_SEAT
    straight = [(xs, yg, f) for f in (1.0,)]
    assert _plan_min(ax, yg, xs, straight) < 0.03
    assert _plan_min(ax, yg, xs, march.west_plan(ax, yg, xs)) > 0.035


def test_tail_turns_at_own_row(base):                   # 分出後沿自己那一路往北，走到自己那一列才轉：東側右轉沿列、西側走列南邊半格的空隙
    G, M = _m(base)
    ax = march.NORTH_X + 0.5 * march.SP_SEAT                                     # 第 4 路（貼第 8 排）
    p0, north = (ax, 6.2), (0.0, -1.0)
    ys = 5.5
    east = M.tail(p0, north, (ax + 3.5 * march.SP_SEAT, ys))
    near = lambda q, r: math.dist(q[:2], r) < 1e-9
    assert abs(east[0][0] - ax) < 1e-9 and near(east[-1], (ax + 3.5 * march.SP_SEAT, ys))
    assert all(q[1] >= ys - 1e-9 for q in east)                                  # 不越過自己那一列往北
    west = M.tail(p0, north, (ax - 2.5 * march.SP_SEAT, ys))
    assert near(west[0], (ax, ys + march.GAP_H))                                 # 沿自己那一路走到列南邊半格才轉
    assert near(west[-1], (ax - 2.5 * march.SP_SEAT, ys)) and near(west[-2], (ax - 2.5 * march.SP_SEAT, ys + march.GAP_H))
    try:
        M.tail(p0, (1.0, 0.0), (ax, ys))
    except SystemExit:
        pass
    else:
        raise AssertionError('分出點不在北行直線上要停止建置')


def test_lane_to_row(base):                             # lane j → 列 6k−5+j：lane 0 對到大隊第一列（Y 最小）
    people = plan.build_plan(base)['people']
    for p in people:
        assert p['lie'] == 6 * (p['dadui'] - 1) + p['gateLane'] + 1
    for d in range(1, 10):
        ys = [min(p['field']['Y'] for p in people if p['dadui'] == d and p['gateLane'] == j) for j in range(6)]
        assert ys == sorted(ys)
