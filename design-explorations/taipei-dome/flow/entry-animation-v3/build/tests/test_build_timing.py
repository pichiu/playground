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
    assert all(v['leave'] < v['stair'] < v['assembly'] <= v['enter'] < v['gate'] for v in S.values())


def test_stair_beats_and_dadui_alignment(base):
    people, (S, clocks) = _sched(base)
    for L in 'AB':
        for d in range(1, 10):
            ts = [S[p['id']]['stair'] for p in people if p['lane'] == L and p['dadui'] == d]
            assert all(abs(b - a - 0.4) < 1e-6 for a, b in zip(ts, ts[1:]))
    ends = {d: max(S[p['id']]['stair'] for p in people if p['dadui'] == d) for d in range(1, 9)}
    starts = {d: min(S[p['id']]['stair'] for p in people if p['dadui'] == d) for d in range(2, 10)}
    assert all(abs(starts[d + 1] - ends[d] - 1.2) < 1e-6 for d in range(1, 9))


def test_lane_b_staggered(base):
    people, (S, clocks) = _sched(base)
    a = next(p for p in people if p['lane'] == 'A' and p['laneIdx'] == 0)
    b = next(p for p in people if p['lane'] == 'B' and p['laneIdx'] == 0)
    assert abs(S[b['id']]['stair'] - S[a['id']]['stair'] - 0.17) < 1e-6


def test_total_length_band(base):
    people, (S, clocks) = _sched(base)
    assert 15 < clocks['tGateStart'] < 60 and 330 < max(v['gate'] for v in S.values()) < 370


def test_shift_moves_whole_timeline(base):
    G = routes.Geometry(base)
    people = plan.build_plan(base)['people']
    R = build.prepare(G, people)
    S0, _ = build.schedule(G, people, R)
    pid = people[5]['id']
    S1, _ = build.schedule(G, people, R, {pid: 0.1})
    assert all(abs(S1[pid][k] - S0[pid][k] - 0.1) < 1e-9 for k in S0[pid])


def test_door_queue_gate_clock(base):                # 門前集合、大隊一起進場：同一大隊每條線 0.4 秒一位、六條線錯開 0.17 秒（同 2c）
    people, (S, clocks) = _sched(base)
    for d in range(1, 10):
        ps = [p for p in people if p['dadui'] == d]
        T = min(S[p['id']]['gate'] - build.ENTRY_HEADWAY * p['slot'] - build.STAGGER * p['gateLane'] for p in ps)
        assert all(abs(S[p['id']]['gate'] - (T + build.ENTRY_HEADWAY * p['slot'] + build.STAGGER * p['gateLane'])) < 1e-6 for p in ps)
    assert build.ENTRY_HEADWAY == 0.4


def test_door_queue_waits_and_no_starving(base):        # 先到的在門前等，最後幾位邊到邊走：沒有人得在到門前之前就出發
    people, (S, clocks) = _sched(base)
    w = [S[p['id']]['enter'] - S[p['id']]['assembly'] for p in people]
    assert min(w) > -1e-9 and 15 < max(w) < 40
    assert sum(1 for x in w if x < 0.05) >= 9           # 每大隊至少有一位不必停
