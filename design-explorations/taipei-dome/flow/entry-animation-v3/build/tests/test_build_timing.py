import build
import plan
import routes


_CACHE = {}


def _sched(base):                                       # 排程約 100 秒（逐排排往西走法、樓梯延後要重算幾輪）：同一份 base 只算一次
    if id(base) not in _CACHE:
        G = routes.Geometry(base)
        people = plan.build_plan(base)['people']
        R = build.prepare(G, people)
        _CACHE[id(base)] = (people, build.schedule(G, people, R))
    return _CACHE[id(base)]


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
    delay = clocks['stairDelay']                      # 等門前隊伍有空位而延後的秒數（北行段到齊才起步、進場變慢）
    assert all(abs(starts[d + 1] - ends[d] - build.HEADWAY - build.DADUI_GAP - delay.get(d + 1, 0.0)) < 1e-6 for d in range(1, 9))
    assert all(0 <= v < 40 for v in delay.values())


def test_lane_b_staggered(base):
    people, (S, clocks) = _sched(base)
    a = next(p for p in people if p['lane'] == 'A' and p['laneIdx'] == 0)
    b = next(p for p in people if p['lane'] == 'B' and p['laneIdx'] == 0)
    assert abs(S[b['id']]['stair'] - S[a['id']]['stair'] - 0.17) < 1e-6


def test_total_length_band(base):
    people, (S, clocks) = _sched(base)
    assert 15 < clocks['tGateStart'] < 60 and 300 < max(v['gate'] for v in S.values()) < 400   # 第 10 排切齊、整塊走、前面停後面也停：全長約 350 秒


def test_ranks_fill_then_continuous(base):             # 每個大隊排滿門前隊伍才出發；之後一排六人一起離開隊頭，排與排至少 RANK_GAP
    people, (S, clocks) = _sched(base)
    rank = clocks['rankOf']
    ranks = clocks['ranks']
    G = routes.Geometry(base)
    M = build.march_of(G)
    # 整排並肩：所有排同一個速度剖面，穿過西一入口牆線的時刻 = t.enter + 該線的 τ
    last = max(p['dadui'] for p in people)
    frozen = lambda p: sum(min(b, S[p['id']]['gate']) - a for a, b in S[p['id']].get('waits', []) if a < S[p['id']]['gate'])   # 最後一個大隊過門前可能跟著前面停
    assert all(abs(S[p['id']]['enter'] - ranks[rank[p['id']]]) < 1e-9 for p in people)
    assert all(abs(S[p['id']]['gate'] - S[p['id']]['enter'] - M.tau_gate[p['gateLane']] - (frozen(p) if p['dadui'] == last else 0.0)) < 1e-9 for p in people)
    held = lambda v: sum(e - a for _, a, e, _k in v['tl']['stops'] if a < v['split'])   # 分出前停的時間：迴廊候隊＋前面停後面也停
    assert all(abs(S[p['id']]['split'] - S[p['id']]['enter'] - held(S[p['id']]) - M.tau_at_s(clocks['split'][p['dadui']])) < 1e-9 for p in people)
    assert min(b - a for a, b in zip(ranks, ranks[1:])) >= build.RANK_GAP - 1e-9
    for d in range(1, 10):                              # 每個大隊排滿門前隊伍才出發
        ps = [p for p in people if p['dadui'] == d]
        assert max(S[p['id']]['assembly'] for p in ps) + build.FILL_PAUSE <= min(S[p['id']]['enter'] for p in ps) + 1e-9


def test_corridor_staging(base):                       # 迴廊候隊：大隊 1–8 在沿牆迴廊停到下一大隊排滿，迴廊一次一個大隊；大隊 9 不停
    people, (S, clocks) = _sched(base)
    for d in range(1, 10):
        ps = [p for p in people if p['dadui'] == d]
        if d == 9:
            assert not any('holdStart' in S[p['id']] for p in ps)
            continue
        nxt = [p for p in people if p['dadui'] == d + 1]
        assert all(S[p['id']]['holdEnd'] > S[p['id']]['holdStart'] for p in ps)
        assert min(S[p['id']]['holdEnd'] for p in ps) >= max(S[p['id']]['assembly'] for p in nxt) + build.STAGE_PAUSE - 1e-9
        if d + 1 < 9:
            assert min(S[p['id']]['holdStart'] for p in nxt) >= max(S[p['id']]['holdEnd'] for p in ps) - 1e-9


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
