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


def test_first_batch_then_continuous(base):            # 大隊 1 頭一批六條線切齊（同 2c 節奏）；之後每條線一路接續、不分大隊停
    people, (S, clocks) = _sched(base)
    first = [p for p in people if p['dadui'] == 1 and p['slot'] < build.FIRST_BATCH]
    T = min(S[p['id']]['gate'] - build.ENTRY_HEADWAY * p['slot'] - build.STAGGER * p['gateLane'] for p in first)
    assert all(abs(S[p['id']]['gate'] - (T + build.ENTRY_HEADWAY * p['slot'] + build.STAGGER * p['gateLane'])) < 1e-6 for p in first)
    import collections
    lines = collections.defaultdict(list)
    for p in people:
        lines[p['gateLane']].append(S[p['id']]['gate'])
    for g in lines.values():
        g.sort()
        assert min(b - a for a, b in zip(g, g[1:])) >= build.ENTRY_HEADWAY - 1e-9 and max(b - a for a, b in zip(g, g[1:])) < 12
    later = [S[p['id']]['enter'] - S[p['id']]['assembly'] for p in people if p not in first]
    assert max(later) < 1.0                                # 頭一批以外到門前就接著走
    w = [S[p['id']]['enter'] - S[p['id']]['assembly'] for p in first]
    assert 1 < max(w) < 15 and build.FIRST_BATCH == 10


def test_every_dadui_has_a_walk_through(base):          # review：每個大隊都有人邊到邊走（T_k 不會晚到全大隊都要等）
    people, (S, clocks) = _sched(base)
    for d in range(1, 10):
        assert any(S[p['id']]['enter'] - S[p['id']]['assembly'] < 0.01 for p in people if p['dadui'] == d), d


def test_queue_spot_has_room(base):                      # review：門前位置不能排到樓梯平台後面
    import pytest
    G = routes.Geometry(base)
    with pytest.raises(ValueError):
        G.queue_u({'slot': 60, 'gateLane': 0})
