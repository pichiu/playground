"""版本 3 排位規則：兩路交錯、出口坐滿就換、出口 FIFO 配座（spec §3.1–3.3）。

用法: python3 plan.py base.json plan.json
"""
import collections
import json
import sys

# ---------- 兩路（spec §3.1） ----------
LANES = 'AB'
LANE_COSTUME = {'A': '白', 'B': '藍'}
LANE_J = {'A': (0, 1, 2), 'B': (3, 4, 5)}      # 西一入口線 j：白衣 6k−5…6k−3、藍衣 6k−2…6k

# ---------- 出口（spec §3.2） ----------
EXITS = ['139', '140', '141', '142', '143', '144', '145']
EXIT_RANK = {e: i for i, e in enumerate(EXITS)}
EXIT_ORDER = {'A': ['139', '140', '141', '142'], 'B': ['142', '143', '144', '145']}


def _people_index(base):
    return {p['id']: p for p in base['persons']}


def lane_sequence(base, lane):
    """路 lane 的全部人員，依大隊 1→9；每大隊三列交錯（j 小的先，一輪各取一人，排完的列跳過），每列排大的先。"""
    by_lie = collections.defaultdict(list)
    for p in base['persons']:
        by_lie[p['lie']].append(p)
    out = []
    for k in range(1, 10):
        cols = [sorted(by_lie[6 * k - 5 + j], key=lambda p: -p['pai']) for j in LANE_J[lane]]
        n = 0
        for i in range(max(map(len, cols))):
            for col in cols:
                if i < len(col):
                    src = col[i]
                    out.append(dict(id=src['id'], lie=src['lie'], pai=src['pai'], dadui=k, costume=LANE_COSTUME[lane], a=src['a'],
                                    lane=lane, laneIdx=len(out), dadIdx=n, gateLane=(src['lie'] - 1) % 6, slot=i, assembly='FEEDER'))
                    n += 1
    return out


def stair_key(p):
    """計畫樓梯時刻的順序：大隊、該大隊該路內序號、路（A 早 0.17 秒）。"""
    return (p['dadui'], p['dadIdx'], LANES.index(p['lane']))


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
        # 版本 1 的 path[k] 是當時那條鏈的匯入點（偏移 ±0.2 不等），不是走廊邊；改成同一 u 的看台側走廊邊（+0.25），
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


def assign_exits(base, seqs):
    """出口坐滿就換（spec §3.2）。142 兩路共用：先保留 A 路需要的席數，其餘給 B。"""
    cap = {e: len(usable_seats(base, e)) for e in EXITS}
    shared = set(EXIT_ORDER['A']) & set(EXIT_ORDER['B'])
    need_a = len(seqs['A']) - sum(cap[e] for e in EXIT_ORDER['A'] if e not in shared)
    left = {L: {e: cap[e] for e in EXIT_ORDER[L]} for L in LANES}
    for e in shared:
        left['A'][e], left['B'][e] = max(0, need_a), cap[e] - max(0, need_a)
    for L in LANES:
        order = EXIT_ORDER[L]
        oi = 0
        for p in seqs[L]:
            while oi < len(order) and left[L][order[oi]] == 0:
                oi += 1
            if oi == len(order):
                short = len(seqs[L]) - p['laneIdx']
                raise SystemExit(f'路 {L} 缺 {short} 席')
            p['exit'] = order[oi]
            left[L][order[oi]] -= 1


def nesting_violations(people):
    """依計畫樓梯時刻合併兩路；兩路都已開始後，任何時刻 A 的出口要比 B 近（rank 小），且不在同一座階梯。"""
    cur, bad, same = {}, [], []
    for p in sorted(people, key=stair_key):
        cur[p['lane']] = p['exit']
        if len(cur) < len(LANES):
            continue
        a, b = cur['A'], cur['B']
        if EXIT_RANK[a] >= EXIT_RANK[b]:
            bad.append(dict(id=p['id'], exits=[a, b]))
        elif STAIR_OF[a] == STAIR_OF[b]:
            same.append(dict(id=p['id'], stairs=[STAIR_OF[a], STAIR_OF[b]]))
    return bad, same


def assign_seats(base, people):
    """每出口依計畫樓梯時刻成一條 FIFO → 由上排往下配座；補齊場內定位與西一入口序號。"""
    who = _people_index(base)
    by_exit = collections.defaultdict(list)
    for p in people:
        by_exit[p['exit']].append(p)
    for e, group in by_exit.items():
        seats = usable_seats(base, e)
        if len(group) > len(seats):
            raise SystemExit(f'出口 {e} 需要 {len(group)} 席，只有 {len(seats)} 席')
        group.sort(key=stair_key)
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
    for j in range(6):
        line = sorted((p for p in people if p['gateLane'] == j), key=lambda p: (p['dadui'], -p['pai']))
        for g, p in enumerate(line):
            p['gateIdx'] = g


def _where(p):
    return dict(dadui=p['dadui'], lie=p['lie'], pai=p['pai'])


def build_plan(base):
    seqs = {L: lane_sequence(base, L) for L in LANES}
    assign_exits(base, seqs)
    people = [p for L in LANES for p in seqs[L]]
    bad, same = nesting_violations(people)
    if bad or same:
        raise SystemExit(f'巢狀被破壞：{len(bad)} 個時刻出口順序錯、{len(same)} 個時刻同一座階梯，例如 {(bad + same)[:3]}')
    assign_seats(base, people)
    groups = []
    for k in range(1, 10):
        for L in LANES:
            members = [p for p in seqs[L] if p['dadui'] == k]
            exits = []
            for p in members:
                if not exits or exits[-1]['exit'] != p['exit']:
                    exits.append(dict(exit=p['exit'], n=0))
                exits[-1]['n'] += 1
            groups.append(dict(key=LANE_COSTUME[L] + str(k), costume=LANE_COSTUME[L], dadui=k, lane=L, population=len(members),
                               columns=[6 * k - 5 + j for j in LANE_J[L]], exits=exits))
    lanes_out = {}
    for L in LANES:
        segs = []
        for p in seqs[L]:
            if not segs or segs[-1]['exit'] != p['exit']:
                segs.append(dict(exit=p['exit'], fromIdx=p['laneIdx'], from_=p))
            segs[-1]['toIdx'], segs[-1]['to_'] = p['laneIdx'], p
        lanes_out[L] = dict(total=len(seqs[L]), segments=[dict(exit=s['exit'], fromIdx=s['fromIdx'], toIdx=s['toIdx'], n=s['toIdx'] - s['fromIdx'] + 1,
                                                               **{'from': _where(s['from_']), 'to': _where(s['to_'])}) for s in segs])
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
    return dict(groups=groups, lanes=lanes_out, exits=exits, people=people)


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    base_path, out_path = sys.argv[1:3]
    base = json.load(open(base_path, encoding='utf-8'))
    planj = build_plan(base)
    json.dump(planj, open(out_path, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    used = {e: v['used'] for e, v in planj['exits'].items()}
    print('plan.json 寫出：', len(planj['people']), '人；出口用量', used)
