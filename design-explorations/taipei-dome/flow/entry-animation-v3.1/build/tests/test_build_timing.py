import build
import plan
import routes


def _sched(base):
    G = routes.Geometry(base)
    people = plan.build_plan(base)['people']
    R = build.prepare(G, people)
    return people, build.schedule(G, people, R)


def test_first_leave_is_t0_and_order(base):
    people, (S, clocks) = _sched(base)
    assert abs(min(v['leave'] for v in S.values()) - build.T0) < 1e-6
    assert all(v['leave'] < v['stair'] < v['assembly'] <= v['enter'] + 1e-9 and v['enter'] < v['gate'] for v in S.values())


def test_stair_beats_and_dadui_alignment(base):
    people, (S, clocks) = _sched(base)
    for L in 'AB':
        for d in range(1, 10):
            ts = [S[p['id']]['stair'] for p in people if p['lane'] == L and p['dadui'] == d]
            assert all(abs(b - a - build.HEADWAY) < 1e-6 for a, b in zip(ts, ts[1:]))
    ends = {d: max(S[p['id']]['stair'] for p in people if p['dadui'] == d) for d in range(1, 9)}
    starts = {d: min(S[p['id']]['stair'] for p in people if p['dadui'] == d) for d in range(2, 10)}
    assert all(abs(starts[d + 1] - ends[d] - build.HEADWAY - build.DADUI_GAP) < 1e-6 for d in range(1, 9))


def test_lane_b_staggered(base):
    people, (S, clocks) = _sched(base)
    a = next(p for p in people if p['lane'] == 'A' and p['laneIdx'] == 0)
    b = next(p for p in people if p['lane'] == 'B' and p['laneIdx'] == 0)
    assert abs(S[b['id']]['stair'] - S[a['id']]['stair'] - 0.17) < 1e-6


def test_total_length_band(base):                       # 11/9：九個大隊全部站定才放行，第一位過西一入口在最後一位站定之後（動畫節奏，不是現場時間）
    people, (S, clocks) = _sched(base)
    last_in = max(v['assembly'] for v in S.values())
    assert last_in < clocks['tGateStart'] < last_in + 5 and max(v['gate'] for v in S.values()) < last_in + 80


def test_release_after_all_nine(base):                  # 11/9：九個大隊全部站定後才開始放行；大隊 1→9 連續，下一大隊第一排緊跟上一大隊最後一排
    people, (S, clocks) = _sched(base)
    last_in = max(v['assembly'] for v in S.values())
    assert min(v['enter'] for v in S.values()) >= last_in + build.FILL_PAUSE - 1e-9
    th = clocks['tauHead']
    ref = lambda p: S[p['id']]['enter'] + th[1] - th[p['dadui']]
    for d in range(1, 9):
        a = max(ref(p) for p in people if p['dadui'] == d)
        b = min(ref(p) for p in people if p['dadui'] == d + 1)
        assert abs(b - a - build.RANK_GAP) < 1e-6


def test_ranks_fill_then_continuous(base):             # 每個大隊在集合位置站齊才放行；之後一排六人一起離開隊頭，排與排（換算到大隊 1 隊頭）至少 RANK_GAP
    people, (S, clocks) = _sched(base)
    rank = clocks['rankOf']
    ranks = clocks['ranks']
    G = routes.Geometry(base)
    M = build.march_of(G)
    th = clocks['tauHead']
    # 整排並肩：所有排同一個速度剖面，穿過西一入口牆線的時刻 = t.enter + 該線的 τ − 自己大隊隊頭的 τ；沒有迴廊候隊
    assert all(abs(S[p['id']]['enter'] - ranks[rank[p['id']]]) < 1e-9 and abs(S[p['id']]['gate'] - S[p['id']]['enter'] - M.tau_gate[p['gateLane']] + th[p['dadui']]) < 1e-9 for p in people)
    assert all(abs(S[p['id']]['split'] - S[p['id']]['enter'] - M.tau_at_s(clocks['split'][p['dadui']]) + th[p['dadui']]) < 1e-9 for p in people)
    assert not any('holdStart' in v for v in S.values())
    ref = sorted(ranks[r] + th[1] - th[next(p['dadui'] for p in people if rank[p['id']] == r)] for r in ranks)
    assert min(b - a for a, b in zip(ref, ref[1:])) >= build.RANK_GAP - 1e-9
    for d in range(1, 10):                              # 每個大隊站齊才放行
        ps = [p for p in people if p['dadui'] == d]
        assert max(S[p['id']]['assembly'] for p in ps) + build.FILL_PAUSE <= min(S[p['id']]['enter'] for p in ps) + 1e-9


def test_stage_layout_order_and_fit(base):             # 九個集合位置：大隊 1 最靠西一入口（s 最大）、依序往深處、不重疊、都在入口帶之外與圖面盡頭之內
    G = routes.Geometry(base)
    people = plan.build_plan(base)['people']
    lay = build.stage_layout(G, people)
    M = build.march_of(G)
    h = lay['head']
    tails = {d: h[d] - (lay['r1'][d] - lay['r0'][d]) * routes.STAGE_STEP for d in h}
    assert all(tails[d] > h[d + 1] for d in range(1, 9)) and lay['gap'] >= routes.STAGE_GAP_MIN
    assert h[1] < M.s_gate_arc and tails[9] >= M.s_of_u(routes.STAGE_TAIL_U) - 1e-6


def test_free_flow_to_slot(base):                       # 到集合位置前不停（樓梯上不等）：站定時刻 = 離座 + 路程 / 步速
    G = routes.Geometry(base)
    people = plan.build_plan(base)['people']
    R = build.prepare(G, people)
    S, _ = build.schedule(G, people, R)
    assert all(abs(S[p['id']]['assembly'] - S[p['id']]['leave'] - R[p['id']]['L_to'] / build.V) < 1e-9 for p in people)


def test_rank_numbers_restart_per_dadui(base):          # 每個大隊從新的一排開始（下一大隊不往前補）
    people = plan.build_plan(base)['people']
    rank = build.rank_numbers(people)
    for d in range(2, 10):
        assert min(rank[p['id']] for p in people if p['dadui'] == d) > max(rank[p['id']] for p in people if p['dadui'] == d - 1)
    assert all(rank[p['id']] - min(rank[q['id']] for q in people if q['dadui'] == p['dadui']) == p['slot'] for p in people)


