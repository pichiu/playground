"""2c 排位規則：樓梯序、七出口巢狀指派、出口 FIFO 配座（spec §3.1–3.4）。

用法: python3 plan.py base.json plan.json
"""
import collections
import json
import sys

# ---------- 樓梯序與路別（spec §3.1） ----------
BLOCKS = [f'藍{k}' for k in range(9, 0, -1)] + [f'白{k}' for k in range(1, 10)]
LANES = 'ABC'
LANE_COL = {'白': {'A': -5, 'B': -4, 'C': -3}, '藍': {'A': 0, 'B': -1, 'C': -2}}   # 列 = 6k + 偏移

# ---------- 出口（spec §3.2） ----------
EXITS = ['139', '140', '141', '142', '143', '144', '145']
EXIT_RANK = {e: i for i, e in enumerate(EXITS)}

# ---------- 出口 → 路 固定指派（spec §3.3） ----------
ASSIGN = {
    'A': [('139', '藍9', '藍3'), ('140', '藍2', '白7'), ('141', '白8', '白9')],
    'B': [('141', '藍9', '藍3'), ('142', '藍2', '白3'), ('143', '白4', '白9')],
    'C': [('142', '藍9', '藍7'), ('144', '藍6', '藍1'), ('145', '白1', '白9')],
}

# ---------- 集結區（spec §3.5） ----------
ZONE_OF = {}
for _b in BLOCKS:
    _c, _k = _b[0], int(_b[1:])
    if _c == '藍':
        ZONE_OF[_b] = 'P1' if _k == 1 else 'P%d' % (1 + _k // 2)       # 2,3→P2 4,5→P3 6,7→P4 8,9→P5
    else:
        ZONE_OF[_b] = {1: 'P1', 2: 'STAIR', 3: 'P6'}.get(_k, 'FEEDER')
LIFO_ZONES = {'P2', 'P3', 'P4', 'P5'}


def block_parts(block):
    return block[0], int(block[1:])


def column_of(block, lane):
    costume, k = block_parts(block)
    return 6 * k + LANE_COL[costume][lane]


def exit_of(block, lane):
    bi = BLOCKS.index(block)
    for exit_key, b_from, b_to in ASSIGN[lane]:
        if BLOCKS.index(b_from) <= bi <= BLOCKS.index(b_to):
            return exit_key
    raise KeyError((block, lane))


def _people_index(base):
    return {p['id']: p for p in base['persons']}


def lane_sequence(base, lane):
    """依樓梯序展開路 lane 的全部人員；欄內順序：死巷區排 1 先，其餘排大先。"""
    who = _people_index(base)
    pais_of = collections.defaultdict(list)          # 列 13–21 的排不是從 1 起算，取實際排號
    for p in base['persons']:
        pais_of[p['lie']].append(p['pai'])
    out = []
    for block in BLOCKS:
        lie = column_of(block, lane)
        costume, k = block_parts(block)
        pais = sorted(pais_of[lie])
        if ZONE_OF[block] not in LIFO_ZONES:
            pais.reverse()
        for pai in pais:
            pid = f'{lie}-{pai}'
            src = who[pid]
            out.append(dict(id=pid, lie=lie, pai=pai, dadui=k, costume=costume, a=src['a'],
                            block=block, lane=lane, laneIdx=len(out), exit=exit_of(block, lane),
                            assembly=ZONE_OF[block]))
    return out


def check_nesting(seqs):
    """每個樓梯序號三路出口必須嚴格由近到遠（A < B < C）。回傳違反清單。"""
    n = min(len(seqs[L]) for L in LANES)
    bad = []
    for i in range(n):
        ranks = [EXIT_RANK[seqs[L][i]['exit']] for L in LANES]
        if not (ranks[0] < ranks[1] < ranks[2]):
            bad.append(dict(idx=i, exits={L: seqs[L][i]['exit'] for L in LANES}))
    return bad
