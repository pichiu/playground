import plan


def seqs_of(base):
    seqs = {L: plan.lane_sequence(base, L) for L in 'ABC'}
    plan.assign_exits(base, seqs)
    return seqs


def test_lane_totals(base):
    seqs = seqs_of(base)
    assert [len(seqs[L]) for L in 'ABC'] == [534, 537, 538]
    assert [s['block'] for s in seqs['A'][:18]] == ['藍9'] * 18 and seqs['A'][18]['block'] == '藍8'   # A 路藍9 = 列 54（18 人）


def test_block_exits(base):
    seqs = seqs_of(base)

    def by(blk):
        return tuple(sorted({s['exit'] for L in 'ABC' for s in seqs[L] if s['block'] == blk}, key=plan.EXIT_RANK.get))

    assert by('藍9') == ('139', '141', '142') and by('藍4') == ('139', '141', '144')
    assert by('藍1') == ('140', '141', '142', '144', '145') and by('白2') == ('140', '142', '145')
    assert by('白5') == ('140', '143', '145') and by('白9') == ('140', '141', '143', '145')


def test_exit_quota_and_split_columns(base):
    seqs = seqs_of(base)
    assert plan.exit_quota(base, seqs) == {'A': {'139': 224, '140': 291, '141': 19}, 'B': {'141': 240, '142': 116, '143': 185},
                                           'C': {'142': 139, '144': 126, '145': 273}}
    split = [(L, blk) for L in 'ABC' for blk in plan.BLOCKS if len({s['exit'] for s in seqs[L] if s['block'] == blk}) > 1]
    assert split == [('A', '藍2'), ('A', '白9'), ('B', '藍1'), ('B', '白3'), ('C', '藍5'), ('C', '藍1')]
    for L in 'ABC':                                     # 一欄最多分兩個出口，前段在前一個出口
        for blk in plan.BLOCKS:
            es = [s['exit'] for s in seqs[L] if s['block'] == blk]
            assert len(set(es)) <= 2 and es == sorted(es, key=plan.EXIT_RANK.get)


def test_lane_shortfall_is_reported(base):
    import copy
    import pytest
    b = copy.deepcopy(base)
    b['restSeats'] = [s for s in b['restSeats'] if not (s['sec'] == '143' and s['pai'] == 1)]
    short = 181 - len(plan.usable_seats(b, '143'))
    with pytest.raises(SystemExit, match=f'路 B 缺 {short} 席'):
        plan.build_plan(b)


def test_nesting_clean(base):
    assert plan.check_nesting(seqs_of(base)) == []


def test_within_column_order(base):
    A = plan.lane_sequence(base, 'A')
    assert [s['pai'] for s in A if s['block'] == '藍9'][:3] == [1, 2, 3]        # 死巷：排 1 先
    assert [s['pai'] for s in A if s['block'] == '白1'][:3] == [28, 27, 26]     # FIFO：排大先
    top3 = sorted((p['pai'] for p in base['persons'] if p['lie'] == 4), reverse=True)[:3]   # 藍1 的 A 路 = 列 4
    assert [s['pai'] for s in A if s['block'] == '藍1'][:3] == top3                          # 藍1 進 P1（FIFO）：排大先


def test_exit_usage(base):
    from collections import Counter
    c = Counter(s['exit'] for seq in seqs_of(base).values() for s in seq)
    assert c == {'139': 224, '140': 291, '141': 259, '142': 255, '143': 181, '144': 126, '145': 273}


def test_blue_lane_mapping_by_approach_direction():
    """A 路（最靠場側）要對到以自己行進方向最先轉進場的那條線：從樓梯側走來（白、藍1）是 6k−5／6k−2，從死巷走回來（藍2–9）是 6k。"""
    assert [plan.column_of('白4', L) for L in 'ABC'] == [19, 20, 21]
    assert [plan.column_of('藍1', L) for L in 'ABC'] == [4, 5, 6]
    assert [plan.column_of('藍2', L) for L in 'ABC'] == [12, 11, 10]
    assert [plan.column_of('藍9', L) for L in 'ABC'] == [54, 53, 52]


def test_lane_idx_and_fields(base):
    A = plan.lane_sequence(base, 'A')
    assert [s['laneIdx'] for s in A] == list(range(len(A)))
    s = A[0]
    assert set(s) >= {'id', 'lie', 'pai', 'dadui', 'costume', 'block', 'lane', 'laneIdx', 'assembly'}   # exit 由 assign_exits 補上
    assert s['id'] == '54-1' and s['lie'] == 54 and s['costume'] == '藍' and s['dadui'] == 9 and s['assembly'] == 'P5'
