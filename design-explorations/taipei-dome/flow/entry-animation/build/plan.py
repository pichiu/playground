"""2c 排位規則：樓梯序、七出口巢狀指派、出口 FIFO 配座（spec §3.1–3.4）。

用法: python3 plan.py base.json plan.json
"""
import collections
import json
import sys

# ---------- 樓梯序與路別（spec §3.1） ----------
BLOCKS = [f'藍{k}' for k in range(9, 0, -1)] + [f'白{k}' for k in range(1, 10)]
LANES = 'ABC'
# 列 = 6k + 偏移。A 路最靠看台側＝B2 上最靠場側，到西一入口必須對到「以自己的行進方向最先轉進場」的那條線（六條場內線沿走廊排開）：
# 從樓梯側走向西一入口的（白衣、藍1 在 P1）是 j=0/3 → 列 6k−5／6k−2；從死巷反向走回西一入口的（藍2–9）是 j=5 → 列 6k，否則三路在西一入口前左右對調。
LANE_COL = {'白': {'A': -5, 'B': -4, 'C': -3}, '藍': {'A': -2, 'B': -1, 'C': 0}, '藍LIFO': {'A': 0, 'B': -1, 'C': -2}}

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
    key = '藍LIFO' if (costume == '藍' and ZONE_OF[block] in LIFO_ZONES) else costume
    return 6 * k + LANE_COL[key][lane]


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


# ---------- 出口定義與座位（spec §3.2、§3.4） ----------
EXIT_DEF = {
    '139': dict(sec='139', side='N', v1block='139',  fill='desc', stairLabel='139｜140 階梯南半'),
    '140': dict(sec='140', side='S', v1block='140L', fill='asc',  stairLabel='139｜140 階梯北半'),
    '141': dict(sec='141', side='S', v1block='141L', fill='asc',  stairLabel='140｜141 階梯'),
    '142': dict(sec='142', side='S', v1block='142L', fill='asc',  stairLabel='141｜142 階梯'),
    '143': dict(sec='143', side='S', v1block='143',  fill='asc',  stairLabel='142｜143 階梯'),
    '144': dict(sec='144', side='N', v1block='144M', fill='desc', stairLabel='144｜145 階梯南半'),
    '145': dict(sec='145', side='S', v1block='145',  fill='asc',  stairLabel='144｜145 階梯北半'),
}
UNUSED_KINDS = {'blocked', 'work'}
STAIR_OF = {e: d['stairLabel'].split(' ')[0] for e, d in EXIT_DEF.items()}   # 出口所在的階梯：139/140 同一座、144/145 同一座


def seat_usable(seat):
    if seat['kind'] in UNUSED_KINDS:
        return False
    if seat['sec'] == '139' and seat['no'] <= 5:          # 139 的 1–5 號沿現況不用
        return False
    return True


def usable_seats(base, exit_key):
    """由上排往下、每排由出口側往中央排好的可用席。"""
    d = EXIT_DEF[exit_key]
    seats = [s for s in base['restSeats'] if s['sec'] == d['sec'] and seat_usable(s)]
    sign = 1 if d['fill'] == 'asc' else -1
    seats.sort(key=lambda s: (-s['pai'], sign * s['no']))
    return [dict(sec=s['sec'], pai=s['pai'], no=s['no'], X=s['X'], Y=s['Y']) for s in seats]


def _v1_block_people(base, exit_key):
    blk = EXIT_DEF[exit_key]['v1block']
    return [p for p in base['persons'] if p['block'] == blk]


CORRIDOR_EDGE = 0.25      # B1 走廊看台側邊緣的偏移（三路在 +0.12 / 0 / −0.12）
_B1 = {}


def _b1(base):
    key = id(base)
    if key not in _B1:
        from geo import Poly, pairs
        _B1[key] = Poly(pairs(base['map']['b1Corridor']))
    return _B1[key]


def approach(base, exit_key, pai):
    """該排從走道口到 B1 走廊接入點的折線（含兩端）：取版本 1 同區塊、同排任一人的 path[1…第一個落在走廊上的點]。
    143 的 11–14 排與 141L 少數排在上階梯前還有一段斜走，所以不能只取 path[2]。"""
    B1 = _b1(base)
    for p in _v1_block_people(base, exit_key):
        if p['rest']['pai'] != pai:
            continue
        pts = [(q[0], q[1]) for q in p['path']]
        k = next(i for i in range(2, len(pts)) if B1.proj(pts[i])[2] < 0.25)
        # 版本 1 的 path[k] 是當時那條鏈的匯入點（偏移 ±0.2 不等），不是走廊邊；2c 改成同一 u 的看台側走廊邊（+0.25），
        # 之後再由 routes 斜向前方併入自己那一路，避免折返
        u = B1.proj(pts[k])[0]
        return pts[1:k] + [B1.off(u, CORRIDOR_EDGE)]
    raise KeyError(f'版本 1 沒有 {exit_key} 第 {pai} 排的走道口')


def aisle_point(base, exit_key, pai):
    """該排在出口側的走道口。"""
    return approach(base, exit_key, pai)[0]


def entry_point(base, exit_key):
    """出口接入 B1 走廊的代表點：各排接入點的平均。"""
    pais = sorted({p['rest']['pai'] for p in _v1_block_people(base, exit_key)})
    pts = [approach(base, exit_key, pai)[-1] for pai in pais]
    return (sum(x for x, _ in pts) / len(pts), sum(y for _, y in pts) / len(pts))


def assign_seats(base, seqs):
    """三路合併 → 每出口依樓梯序號成一條 FIFO → 由上排往下配座；補齊西一入口路與序號、場內定位。"""
    who = _people_index(base)
    people = [dict(s) for L in LANES for s in seqs[L]]
    by_exit = collections.defaultdict(list)
    for p in people:
        by_exit[p['exit']].append(p)
    for e, group in by_exit.items():
        seats = usable_seats(base, e)
        if len(group) > len(seats):
            raise SystemExit(f'出口 {e} 需要 {len(group)} 席，只有 {len(seats)} 席')
        group.sort(key=lambda p: p['laneIdx'])
        for k, p in enumerate(group):
            seat = seats[k]
            app = approach(base, e, seat['pai'])
            p['exitSeq'] = k
            p['rest'] = seat
            p['approach'] = [list(q) for q in app]
            p['aisle'] = list(app[0])
            p['entry'] = list(app[-1])
    for p in people:
        src = who[p['id']]
        p['field'] = dict(X=src['field']['X'], Y=src['field']['Y'])
        p['gateLane'] = (p['lie'] - 1) % 6
    for j in range(6):
        lane_people = sorted((p for p in people if p['gateLane'] == j), key=lambda p: (p['dadui'], -p['pai']))
        for g, p in enumerate(lane_people):
            p['gateIdx'] = g
    return people


def build_plan(base):
    seqs = {L: lane_sequence(base, L) for L in LANES}
    bad = check_nesting(seqs)
    if bad:
        raise SystemExit(f'巢狀被破壞 {len(bad)} 個序號，例如 {bad[:3]}')
    people = assign_seats(base, seqs)
    blocks = []
    for block in BLOCKS:
        costume, k = block_parts(block)
        lanes = {}
        for L in LANES:
            members = [p for p in people if p['block'] == block and p['lane'] == L]
            lanes[L] = dict(lie=column_of(block, L), exit=members[0]['exit'], n=len(members))
        blocks.append(dict(key=block, costume=costume, dadui=k, population=sum(v['n'] for v in lanes.values()),
                           columns=[column_of(block, L) for L in LANES], assembly=ZONE_OF[block], lanes=lanes))
    lanes_out = {}
    for L in LANES:
        segs = []
        for exit_key, b_from, b_to in ASSIGN[L]:
            idx = [s['laneIdx'] for s in seqs[L] if BLOCKS.index(b_from) <= BLOCKS.index(s['block']) <= BLOCKS.index(b_to)]
            segs.append(dict(exit=exit_key, fromBlock=b_from, toBlock=b_to, n=len(idx), fromIdx=min(idx), toIdx=max(idx)))
        lanes_out[L] = dict(total=len(seqs[L]), segments=segs)
    exits = {}
    for e in EXITS:
        d = EXIT_DEF[e]
        group = sorted((p for p in people if p['exit'] == e), key=lambda p: p['exitSeq'])
        rows = []
        for p in group:
            if not rows or rows[-1]['pai'] != p['rest']['pai']:
                rows.append(dict(pai=p['rest']['pai'], seats=[], ids=[]))
            rows[-1]['seats'].append(p['rest']['no'])
            rows[-1]['ids'].append(p['id'])
        exits[e] = dict(sec=d['sec'], side=d['side'], stairLabel=d['stairLabel'], entry=list(entry_point(base, e)),
                        rank=EXIT_RANK[e], capacity=len(usable_seats(base, e)), used=len(group), rows=rows,
                        order=[p['id'] for p in group])
    return dict(blocks=blocks, lanes=lanes_out, exits=exits, people=people)


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    base_path, out_path = sys.argv[1:3]
    base = json.load(open(base_path, encoding='utf-8'))
    planj = build_plan(base)
    json.dump(planj, open(out_path, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    used = {e: v['used'] for e, v in planj['exits'].items()}
    print('plan.json 寫出：', len(planj['people']), '人；出口用量', used)
