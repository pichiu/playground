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


def test_total_length_band(base):
    people, (S, clocks) = _sched(base)
    assert 15 < clocks['tGateStart'] < 60 and 170 < max(v['gate'] for v in S.values()) < 210


def test_shift_moves_whole_timeline(base):
    G = routes.Geometry(base)
    people = plan.build_plan(base)['people']
    R = build.prepare(G, people)
    S0, _ = build.schedule(G, people, R)
    pid = people[5]['id']
    S1, _ = build.schedule(G, people, R, {pid: 0.1})
    assert all(abs(S1[pid][k] - S0[pid][k] - 0.1) < 1e-9 for k in S0[pid])


def test_ranks_fill_then_continuous(base):             # 大隊 1 排滿門前隊伍才出發；之後一排六人一起離開隊頭，排與排至少 RANK_GAP
    people, (S, clocks) = _sched(base)
    rank = clocks['rankOf']
    ranks = clocks['ranks']
    assert all(abs(S[p['id']]['enter'] - ranks[rank[p['id']]]) < 1e-9 and abs(S[p['id']]['gate'] - S[p['id']]['enter'] - build.TURN_T) < 1e-9 for p in people)
    assert min(b - a for a, b in zip(ranks, ranks[1:])) >= build.RANK_GAP - 1e-9
    assert max(S[p['id']]['assembly'] for p in people if p['dadui'] == 1) + build.FILL_PAUSE <= ranks[0] + 1e-9


def test_rank_numbers_restart_per_dadui(base):          # 每個大隊從新的一排開始（下一大隊不往前補）
    people = plan.build_plan(base)['people']
    rank = build.rank_numbers(people)
    for d in range(2, 10):
        assert min(rank[p['id']] for p in people if p['dadui'] == d) > max(rank[p['id']] for p in people if p['dadui'] == d - 1)
    assert all(rank[p['id']] - min(rank[q['id']] for q in people if q['dadui'] == p['dadui']) == p['slot'] for p in people)


def test_queue_never_overflows(base):                   # 門前隊伍不排回樓梯平台：每人追上隊伍的位置在側移完成之後
    G = routes.Geometry(base)
    people, (S, clocks) = _sched(base)
    for p in people:
        s_join = (S[p['id']]['assembly'] - S[p['id']]['entry']) * build.V
        assert s_join >= G.line_min_s(p['gateLane']) - 1e-9, p['id']
