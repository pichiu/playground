import math
import plan


def people(base):
    return plan.build_plan(base)['people']


def test_capacity(base):
    assert [len(plan.usable_seats(base, e)) for e in plan.EXITS] == [224, 291, 259, 255, 185, 126, 273]


def test_seats_unique_and_legal(base):
    P = people(base)
    keys = {(p['rest']['sec'], p['rest']['pai'], p['rest']['no']) for p in P}
    assert len(P) == 1609 == len(keys)
    bad = {(s['sec'], s['pai'], s['no']) for s in base['restSeats'] if s['kind'] in ('blocked', 'work')}
    reserved = {(s['sec'], s['pai'], s['no']) for s in base['restSeats'] if plan.seat_reserved(s) and s['kind'] not in plan.UNUSED_KINDS}
    assert len(reserved) == 31 + 72 and not (keys & bad) and not (keys & reserved)
    assert all(p['rest']['sec'] == p['exit'] for p in P)


def test_exit_fifo_is_top_down(base):
    P = people(base)
    for e in plan.EXITS:
        q = sorted((p for p in P if p['exit'] == e), key=lambda p: p['exitSeq'])
        assert [p['exitSeq'] for p in q] == list(range(len(q)))
        pais = [p['rest']['pai'] for p in q]
        assert pais == sorted(pais, reverse=True)
        for pai in set(pais):
            nos = [p['rest']['no'] for p in q if p['rest']['pai'] == pai]
            assert nos == (sorted(nos) if plan.EXIT_DEF[e]['fill'] == 'asc' else sorted(nos, reverse=True))


def test_exit_seq_follows_stair_order(base):
    P = people(base)
    for e in plan.EXITS:
        q = sorted((p for p in P if p['exit'] == e), key=lambda p: p['exitSeq'])
        assert [plan.stair_key(p) for p in q] == sorted(plan.stair_key(p) for p in q)


def test_142_shared_fifo(base):                     # Review Focus 1
    P = plan.build_plan(base)
    q = sorted((p for p in P['people'] if p['exit'] == '142'), key=lambda p: p['exitSeq'])
    assert [p['lane'] for p in q] == ['B'] * 220 + ['A'] * 35
    assert {p['dadui'] for p in q[:220]} <= {1, 2, 3} and {p['dadui'] for p in q[220:]} == {9}
    assert P['exits']['142']['order'] == [p['id'] for p in q]


def test_points(base):
    assert math.dist(plan.entry_point(base, '139'), plan.entry_point(base, '140')) < 0.2
    P = people(base)
    assert all(len(p['aisle']) == 2 and len(p['entry']) == 2 for p in P)


def test_gate_idx(base):
    P = people(base)
    for j in range(6):
        g = sorted(p['gateIdx'] for p in P if p['gateLane'] == j)
        assert g == list(range(len(g)))
    first = min((p for p in P if p['gateLane'] == 0), key=lambda p: p['gateIdx'])
    assert (first['lie'], first['pai']) == (1, 28)
    assert all(p['gateLane'] == (p['lie'] - 1) % 6 for p in P)


def test_fields(base):
    p = people(base)[0]
    assert set(p) >= {'rest', 'aisle', 'entry', 'exitSeq', 'gateLane', 'gateIdx', 'field', 'a', 'dadIdx', 'slot'}
    assert set(p['rest']) == {'sec', 'pai', 'no', 'X', 'Y'} and set(p['field']) == {'X', 'Y'}
