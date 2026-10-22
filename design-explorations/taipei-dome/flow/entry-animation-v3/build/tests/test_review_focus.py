"""Review Focus（plan）資料層：142 共用的 FIFO、換口落在大隊中間、交界空檔、交錯。"""
import csv


def test_seats_csv(root):
    rows = list(csv.DictReader(open(root / 'seats.csv', encoding='utf-8')))
    assert len(rows) == 1609 and len({(r['休息區'], r['休息排'], r['座號']) for r in rows}) == 1609
    assert {r['集結區'] for r in rows} == {'不集結，直接進場'} and {r['樓梯路'] for r in rows} == {'A', 'B'}
    used = {}
    for r in rows:
        used[(r['出口'], r['樓梯路'])] = used.get((r['出口'], r['樓梯路']), 0) + 1
    assert used == {('139', 'A'): 206, ('140', 'A'): 291, ('141', 'A'): 259, ('142', 'A'): 53,
                    ('142', 'B'): 202, ('143', 'B'): 185, ('144', 'B'): 198, ('145', 'B'): 215}


def test_142_gap_between_lanes(pipeline):              # Review Focus 1：142 先 B 後 A，中間有一段沒人走
    _, D = pipeline
    q = sorted((p for p in D['persons'] if p['exit'] == '142'), key=lambda p: p['exitSeq'])
    b_last = max(p['t']['leave'] for p in q if p['lane'] == 'B')
    a_first = min(p['t']['leave'] for p in q if p['lane'] == 'A')
    assert a_first - b_last > 60


def test_split_columns_are_mid_dadui(pipeline):        # Review Focus 2：換口落在大隊中間，各列的出口仍單調換到上游
    _, D = pipeline
    import plan
    for lie in D['meta']['checks']['assignment']['splitLies']:
        ps = sorted((p for p in D['persons'] if p['lie'] == lie), key=lambda p: p['t']['enter'])
        ranks = [plan.EXIT_RANK[p['exit']] for p in ps]
        assert ranks == sorted(ranks) and len(set(ranks)) == 2
