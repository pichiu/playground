import plan


def seqs_of(base):
    return {L: plan.lane_sequence(base, L) for L in 'ABC'}


def test_lane_totals(base):
    seqs = seqs_of(base)
    assert [len(seqs[L]) for L in 'ABC'] == [535, 537, 537]
    assert [s['block'] for s in seqs['A'][:18]] == ['藍9'] * 18 and seqs['A'][18]['block'] == '藍8'


def test_block_exits(base):
    seqs = seqs_of(base)

    def by(blk):
        return tuple(sorted({s['exit'] for L in 'ABC' for s in seqs[L] if s['block'] == blk}, key=plan.EXIT_RANK.get))

    assert by('藍9') == ('139', '141', '142') and by('藍4') == ('139', '141', '144')
    assert by('藍1') == ('140', '142', '144') and by('白2') == ('140', '142', '145')
    assert by('白5') == ('140', '143', '145') and by('白9') == ('141', '143', '145')


def test_single_exit_per_column(base):
    seqs = seqs_of(base)
    for L in 'ABC':
        for blk in plan.BLOCKS:
            assert len({s['exit'] for s in seqs[L] if s['block'] == blk}) == 1


def test_nesting_clean(base):
    assert plan.check_nesting(seqs_of(base)) == []


def test_within_column_order(base):
    A = plan.lane_sequence(base, 'A')
    assert [s['pai'] for s in A if s['block'] == '藍9'][:3] == [1, 2, 3]        # 死巷：排 1 先
    assert [s['pai'] for s in A if s['block'] == '白1'][:3] == [28, 27, 26]     # FIFO：排大先
    top3 = sorted((p['pai'] for p in base['persons'] if p['lie'] == 6), reverse=True)[:3]   # 列 6 的排是 2–34
    assert [s['pai'] for s in A if s['block'] == '藍1'][:3] == top3                          # 藍1 進 P1（FIFO）：排大先


def test_exit_usage(base):
    from collections import Counter
    c = Counter(s['exit'] for L in 'ABC' for s in plan.lane_sequence(base, L))
    assert c == {'139': 199, '140': 283, '141': 256, '142': 234, '143': 179, '144': 190, '145': 268}


def test_lane_idx_and_fields(base):
    A = plan.lane_sequence(base, 'A')
    assert [s['laneIdx'] for s in A] == list(range(len(A)))
    s = A[0]
    assert set(s) >= {'id', 'lie', 'pai', 'dadui', 'costume', 'block', 'lane', 'laneIdx', 'exit', 'assembly'}
    assert s['id'] == '54-1' and s['lie'] == 54 and s['costume'] == '藍' and s['dadui'] == 9 and s['assembly'] == 'P5'
