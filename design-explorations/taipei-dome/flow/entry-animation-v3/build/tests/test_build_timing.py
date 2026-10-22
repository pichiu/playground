import build
import plan
import routes


def _sched(base):
    G = routes.Geometry(base)
    people = plan.build_plan(base)['people']
    R = build.prepare(G, people)
    return people, build.schedule(G, people, R)


def test_first_leave_is_t0_and_no_wait(base):
    people, (S, clocks) = _sched(base)
    assert abs(min(v['leave'] for v in S.values()) - build.T0) < 1e-6
    assert all(v['assembly'] == v['enter'] < v['gate'] for v in S.values())
    assert all(v['leave'] < v['enter'] for v in S.values())


def test_stair_beats_and_dadui_alignment(base):
    people, (S, clocks) = _sched(base)
    for L in 'AB':
        for d in range(1, 10):
            ts = [S[p['id']]['enter'] for p in people if p['lane'] == L and p['dadui'] == d]
            assert all(abs(b - a - 0.4) < 1e-6 for a, b in zip(ts, ts[1:]))
    ends = {d: max(S[p['id']]['enter'] for p in people if p['dadui'] == d) for d in range(1, 9)}
    starts = {d: min(S[p['id']]['enter'] for p in people if p['dadui'] == d) for d in range(2, 10)}
    assert all(abs(starts[d + 1] - ends[d] - 1.2) < 1e-6 for d in range(1, 9))


def test_lane_b_staggered(base):
    people, (S, clocks) = _sched(base)
    a = next(p for p in people if p['lane'] == 'A' and p['laneIdx'] == 0)
    b = next(p for p in people if p['lane'] == 'B' and p['laneIdx'] == 0)
    assert abs(S[b['id']]['enter'] - S[a['id']]['enter'] - 0.17) < 1e-6


def test_total_length_band(base):
    people, (S, clocks) = _sched(base)
    assert 15 < clocks['tGateStart'] < 22 and 330 < max(v['gate'] for v in S.values()) < 360


def test_shift_moves_whole_timeline(base):
    G = routes.Geometry(base)
    people = plan.build_plan(base)['people']
    R = build.prepare(G, people)
    S0, _ = build.schedule(G, people, R)
    pid = people[5]['id']
    S1, _ = build.schedule(G, people, R, {pid: 0.1})
    assert all(abs(S1[pid][k] - S0[pid][k] - 0.1) < 1e-9 for k in S0[pid])


def test_ranks_abreast_at_door(base):                 # 入口前六條線齊頭：同一排（同大隊、各列第 slot 位）同時到門前那條線
    people, (S, clocks) = _sched(base)
    import collections
    rank = collections.defaultdict(list)
    for p in people:
        rank[(p['dadui'], p['slot'])].append(S[p['id']]['door'])
    assert all(max(v) - min(v) < 1e-6 for v in rank.values())
    assert max(len(v) for v in rank.values()) == 6


def test_rank_slowdown_bounded(base):                 # 只放慢、不停：最前面的人最多慢約一秒多
    G = routes.Geometry(base)
    people = plan.build_plan(base)['people']
    R = build.prepare(G, people)
    S, _ = build.schedule(G, people, R)
    slow = [S[p['id']]['door'] - S[p['id']]['enter'] - (R[p['id']]['d_door'] - R[p['id']]['d_top']) / build.V for p in people]
    assert min(slow) > -1e-6 and max(slow) <= build.RANK_SLOW_MAX
