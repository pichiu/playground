import plan


def test_lane_sequence_interleaves_three_columns(base):
    A = plan.lane_sequence(base, 'A')
    assert len(A) == 809 and len(plan.lane_sequence(base, 'B')) == 800
    assert [p['lie'] for p in A[:6]] == [1, 2, 3, 1, 2, 3]
    assert all(p['costume'] == '白' for p in A) and [p['laneIdx'] for p in A] == list(range(809))
    d1 = [p for p in A if p['dadui'] == 1]
    assert len(d1) == 87 and [p['dadIdx'] for p in d1] == list(range(87))
    assert all(p['costume'] == '藍' and p['gateLane'] in (3, 4, 5) for p in plan.lane_sequence(base, 'B'))


def test_interleave_skips_exhausted_column(base):     # Review Focus 3
    for L in 'AB':
        seq = plan.lane_sequence(base, L)
        for lie in {p['lie'] for p in seq}:
            pais = [p['pai'] for p in seq if p['lie'] == lie]
            assert pais == sorted(pais, reverse=True)
            assert [p['slot'] for p in seq if p['lie'] == lie] == list(range(len(pais)))
        for d in range(1, 10):
            ds = [p for p in seq if p['dadui'] == d]
            for i, (a, b) in enumerate(zip(ds, ds[1:])):          # 相鄰兩人同一列，只會發生在其他兩列都已排完之後
                if a['lie'] == b['lie']:
                    assert all(p['lie'] == a['lie'] for p in ds[i + 1:])


def test_exit_fill_counts(base):
    P = plan.build_plan(base)
    used = {(e, L): sum(1 for p in P['people'] if p['exit'] == e and p['lane'] == L) for e in plan.EXITS for L in 'AB'}
    assert {k: v for k, v in used.items() if v} == {('139', 'A'): 224, ('140', 'A'): 291, ('141', 'A'): 259, ('142', 'A'): 35,
                                                     ('142', 'B'): 220, ('143', 'B'): 185, ('144', 'B'): 126, ('145', 'B'): 269}


def test_nesting_and_distinct_stairs(base):
    P = plan.build_plan(base)
    bad, same = plan.nesting_violations(P['people'])
    assert bad == [] and same == []


def test_nesting_detects_swap(base):
    P = plan.build_plan(base)['people']
    a = next(p for p in P if p['lane'] == 'A' and p['laneIdx'] == 0)
    b = next(p for p in P if p['lane'] == 'B' and p['laneIdx'] == 0)
    a['exit'], b['exit'] = b['exit'], a['exit']
    bad, _ = plan.nesting_violations(P)
    assert bad


def test_split_columns_reported(base):
    P = plan.build_plan(base)
    split = {lie for lie in range(1, 55) if len({p['exit'] for p in P['people'] if p['lie'] == lie}) > 1}
    assert len(split) == 18
    assert P['lanes']['A']['segments'][0]['exit'] == '139' and len(P['lanes']['A']['segments']) == 4 == len(P['lanes']['B']['segments'])
    g = [g for g in P['groups'] if len(g['exits']) > 1]
    assert len(g) == 6 and all(sum(e['n'] for e in x['exits']) == x['population'] for x in g)


def test_shared_exit_shortfall_is_reported(base):      # review：142 不夠 A 路用時要直接報缺額，不能讓 B 路剩餘席變負數
    import copy
    import pytest
    b = copy.deepcopy(base)
    b['restSeats'] = [s for s in b['restSeats'] if s['sec'] != '141']   # 沒有 141 → A 路要用超過 142 全部的席
    with pytest.raises(SystemExit, match='路 A 缺 39 席'):
        plan.build_plan(b)
