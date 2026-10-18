"""藍衣全部 B2 集結版:由舊版動畫資料(座位/場地幾何)重算休息區座位、路徑與時間。

用法: python3 build.py old_data.json out_data.json out_plan.json
"""
import json, math, sys, collections
import numpy as np
from geo import Poly, pairs

OLD, OUT, PLAN = sys.argv[1:4]
D = json.load(open(OLD))
V = D['meta']['speedUnitPerSec']          # 1.1 單位/秒
GAP_SEAT = 0.28                           # 同列相鄰兩人離座間隔
GAP_ROW = 1.5                             # 同鏈前一列最後一人離座 → 下一列第一人
T0 = 6.73                                 # 第一人離座
GATE_GAP, LANE_STAGGER, DADUI_GAP = 0.4, 0.17, 2.5
M = D['map']
B1 = Poly(pairs(M['b1Corridor'])); B2 = Poly(pairs(M['b2Corridor'])); ST = Poly(pairs(M['stair']))
OLDP = {p['id']: p for p in D['persons']}
OLDF = {f['lie']: f for f in D['files']}
LIE_N = {f['lie']: f['n'] for f in D['files']}

def dadui_of(lie): return (lie - 1) // 6 + 1
def costume_of(lie): return '白' if (lie - 1) % 6 < 3 else '藍'
def lane_of(lie): return (lie - 1) % 6          # 6口 由北數第幾路 = 場內隊形左右

# ---------- 集結區 ----------
# kind: LIFO = B2 死巷(先到站最裡面);FIFO = 頭朝 6口/樓梯,先到站最前面
ZONES = {
    'P1':    dict(label='1',        floor='B2', kind='FIFO', corr='B2', head=4.15,  step=-0.073),
    'P2':    dict(label='藍 2·3',   floor='B2', kind='LIFO', corr='B2', head=5.0,   step=0.075),
    'P3':    dict(label='藍 4·5',   floor='B2', kind='LIFO', corr='B2', head=8.2,   step=0.075),
    'P4':    dict(label='藍 6·7',   floor='B2', kind='LIFO', corr='B2', head=11.0,  step=0.075),
    'P5':    dict(label='藍 8·9',   floor='B2', kind='LIFO', corr='B2', head=14.5,  step=0.075),
    'STAIR': dict(label='白 2',     floor='B1', kind='FIFO', corr='STAIR'),
    'P6':    dict(label='白 3',     floor='B1', kind='FIFO', corr='B1', head=12.37, step=-0.062),
    'P7':    dict(label='白 4·5',   floor='B1', kind='FIFO', corr='B1', head=10.45, step=-0.062),
    'P8':    dict(label='白 6·7',   floor='B1', kind='FIFO', corr='B1', head=8.30,  step=-0.062),
    'P9':    dict(label='白 8·9',   floor='B1', kind='FIFO', corr='B1', head=5.75,  step=-0.062),
}
def zone_of(lie):
    d, c = dadui_of(lie), costume_of(lie)
    if d == 1: return 'P1'
    if c == '藍': return 'P%d' % (1 + (d // 2))           # 2,3→P2 4,5→P3 6,7→P4 8,9→P5
    return {2: 'STAIR', 3: 'P6', 4: 'P7', 5: 'P7', 6: 'P8', 7: 'P8', 8: 'P9', 9: 'P9'}[d]
def first_in_zone(lie):            # 同區兩個大隊時,較早進場者站靠內側(往 6口 不穿越)
    d = dadui_of(lie)
    return d == 1 or d == 2 or d == 3 and costume_of(lie) == '白' or (d % 2 == 0)
def slot_offset(lie):
    z, j, first = zone_of(lie), lane_of(lie), first_in_zone(lie)
    if z == 'P1': return 0.2 - 0.08 * j
    if ZONES[z]['corr'] == 'B2':       # 藍:6口 南三路 3,4,5;內側(+)為場內側
        k = j - 3
        return (0.04 + 0.08 * k) if first else (-0.2 + 0.08 * k)
    k = j                              # 白:6口 北三路 0,1,2;B1 + 為看台側,接樓梯北路
    return (0.2 - 0.08 * k) if first else (-0.04 - 0.08 * k)

# 樓梯集結(白 2):沿用舊版 6白 在樓梯上的格位
STAIR_SLOTS = {}
for lie_old, j in ((31, 0), (32, 1), (33, 2)):
    ps = sorted([p for p in D['persons'] if p['lie'] == lie_old], key=lambda p: p['gateIdx'])
    pts = []
    for p in ps:
        pts.append([q for q in p['path'] if abs(q[2] - p['t']['assembly']) < 1e-6][0][:2])
    STAIR_SLOTS[j] = pts
def slot_xy(lie, i):
    z = zone_of(lie); Z = ZONES[z]
    if z == 'STAIR':
        pts = STAIR_SLOTS[lane_of(lie)]
        if i < len(pts): return tuple(pts[i])
        a, b = pts[-2], pts[-1]
        return (b[0] + (b[0] - a[0]) * (i - len(pts) + 1), b[1] + (b[1] - a[1]) * (i - len(pts) + 1))
    poly = B1 if Z['corr'] == 'B1' else B2
    return poly.off(Z['head'] + Z['step'] * i, slot_offset(lie))
def slot_u(lie, i):
    Z = ZONES[zone_of(lie)]
    return Z['head'] + Z['step'] * i

# ---------- 路線 ----------
CHAIN_OFF = {('A', '藍'): 0.2, ('A', '白'): 0.12, ('B', '藍'): 0.04, ('B', '白'): -0.04, ('C', '藍'): -0.12, ('C', '白'): -0.2}
CORR_LANE = {k: round((0.2 - v) / 0.08) for k, v in CHAIN_OFF.items()}
STAIR_OFF = {'A': 0.12, 'B': 0.0, 'C': -0.12}
STAIR_U_B1, B2_U_START = 13.15, 1.0
GATE_PTS = {}
for p in D['persons']:
    if p['dadui'] == 1:
        GATE_PTS[p['laneIdx']] = [q for q in p['path'] if abs(q[2] - p['t']['gate']) < 1e-6][0][:2]

def lane_run(poly, u0, u1, off, step=0.35):
    n = max(1, int(abs(u1 - u0) / step))
    return [poly.off(u0 + (u1 - u0) * k / n, off) for k in range(1, n + 1)]

def white_route(j, u_from, off_from):
    """B1 位置 → 樓梯(第 j 路,北=0)→ B2 內側 → 6口 第 j 路"""
    pts = []
    so = 0.12 - 0.12 * j
    if u_from is not None:
        pts += lane_run(B1, u_from, STAIR_U_B1 - 0.25, off_from)
        pts.append(B1.off(STAIR_U_B1, 0.2 - 0.08 * j))
    pts += [ST.off(0.05, so), ST.off(ST.L - 0.05, so)]
    o = 0.2 - 0.08 * j
    pts += lane_run(B2, B2_U_START, 4.2, o)
    pts.append(tuple(GATE_PTS[j]))
    return pts

# ---------- 休息區鏈 ----------
def chain_seq():
    seqs = {}
    for ch in 'ABC':
        ps = sorted([p for p in D['persons'] if p['chain'] == ch], key=lambda p: p['t']['leave'])
        seqs[ch] = [dict(sec=p['rest']['sec'], pai=p['rest']['pai'], no=p['rest']['no'], X=p['rest']['X'], Y=p['rest']['Y'],
                         block=p['block'], exitSide=p['exitSide'], exitWave=p['exitWave'],
                         aisle=p['path'][1][:2], entry=p['path'][2][:2]) for p in ps]
    seatxy = {(s['sec'], s['pai'], s['no']): s for s in D['restSeats']}
    extra = {'A': [('142', 1, n) for n in range(16, 11, -1)],
             'B': [('144', 1, n) for n in range(15, 7, -1)],
             'C': [('145', 1, n) for n in range(16, 24)]}
    for ch, keys in extra.items():
        last = seqs[ch][-1]
        for k in keys:
            s = seatxy[k]
            assert s['who'] is None, k
            seqs[ch].append(dict(last, sec=k[0], pai=k[1], no=k[2], X=s['X'], Y=s['Y'], extra=True))
    return seqs
SEQ = chain_seq()
CAP = {ch: len(v) for ch, v in SEQ.items()}

# ---------- 列 → 鏈(依優先序,DP 平衡) ----------
PH1 = [46, 47, 48, 52, 53, 54, 34, 35, 36, 40, 41, 42, 22, 23, 24, 28, 29, 30, 10, 11, 12, 16, 17, 18, 4, 5, 6, 1, 2, 3]
PH2 = [7, 8, 9, 13, 14, 15, 19, 20, 21, 25, 26, 27, 31, 32, 33, 37, 38, 39, 43, 44, 45, 49, 50, 51]
ORDER = PH1 + PH2
# 鏈 A 尾段在 143/142R(走道口約 u=6.0,在白 8·9 區南邊):白 8·9 只能坐鏈 B/C 尾段的 144/145
NOT_A = {43, 44, 45, 49, 50, 51}
assert sorted(ORDER) == list(range(1, 55))

def partition():
    capA, capB, capC = CAP['A'], CAP['B'], CAP['C']
    INF = 1e18
    dp = np.full((capA + 1, capB + 1), INF); dp[0, 0] = 0
    choice = []
    cum = 0
    A_idx = np.arange(capA + 1)[:, None]; B_idx = np.arange(capB + 1)[None, :]
    for r, lie in enumerate(ORDER):
        n = LIE_N[lie]; w = (len(ORDER) - r) ** 1.5
        C_load = cum - A_idx - B_idx
        cand = np.full((3, capA + 1, capB + 1), INF)
        # A
        cand[0, n:, :] = dp[:-n, :] + w * (A_idx[:-n] * GAP_SEAT)
        if lie in NOT_A: cand[0] = INF
        cand[1, :, n:] = dp[:, :-n] + w * (B_idx[:, :-n] * GAP_SEAT)
        okC = (C_load + n <= capC) & (C_load >= 0)
        cand[2] = np.where(okC, dp + w * (np.maximum(C_load, 0) * GAP_SEAT), INF)
        ch = np.argmin(cand, axis=0); dp = np.min(cand, axis=0)
        choice.append(ch.astype(np.int8))
        cum += n
    # 結束狀態:C = cum - A - B ≤ capC
    Cl = cum - A_idx - B_idx
    base = {ch: sum(1 for x in SEQ[ch] if not x.get('extra')) for ch in 'ABC'}
    over = np.maximum(A_idx - base['A'], 0) + np.maximum(B_idx - base['B'], 0) + np.maximum(Cl - base['C'], 0)
    final = np.where((Cl >= 0) & (Cl <= capC), dp + 1e7 * over, INF)
    a, b = np.unravel_index(np.argmin(final), final.shape)
    assert final[a, b] < INF, '容量不可行'
    assign = {}
    for r in range(len(ORDER) - 1, -1, -1):
        lie = ORDER[r]; n = LIE_N[lie]; c = int(choice[r][a, b])
        assign[lie] = 'ABC'[c]
        if c == 0: a -= n
        elif c == 1: b -= n
    return assign
ASSIGN = partition()
CHAIN_ROWS = {ch: [lie for lie in ORDER if ASSIGN[lie] == ch] for ch in 'ABC'}

# 座位分配:每鏈依序填;列內離座順序 LIFO 區排 1 先(頭→尾),其餘排大先(尾→頭)
def pai_order(lie):
    pais = sorted([p['pai'] for p in D['persons'] if p['lie'] == lie])
    return pais if ZONES[zone_of(lie)]['kind'] == 'LIFO' else pais[::-1]
SEAT_OF = {}      # id -> seat dict
ROW_SEGS = collections.defaultdict(list)
for ch in 'ABC':
    k = 0
    for lie in CHAIN_ROWS[ch]:
        for q, pai in enumerate(pai_order(lie)):
            s = SEQ[ch][k]; k += 1
            SEAT_OF['%d-%d' % (lie, pai)] = dict(s, chain=ch, qi=q)
    assert k <= CAP[ch]
    print('鏈', ch, '使用', k, '/', CAP[ch], '列', CHAIN_ROWS[ch])

# ---------- 抵達路徑 ----------
def arrival_route(pid, lie, i):
    """座位 → 集結格位 的路點(不含時間),以及走廊經過紀錄 legs=[(corr,u0,u1,dist0)]"""
    s = SEAT_OF[pid]; ch = s['chain']; cos = costume_of(lie); z = zone_of(lie); Z = ZONES[z]
    pts = [(s['X'], s['Y']), tuple(s['aisle'])]
    u_in = B1.proj(s['entry'])[0]
    off = CHAIN_OFF[(ch, cos)]
    pts.append(B1.off(u_in, off))
    legs = []
    tgt = slot_xy(lie, i)
    if Z['corr'] == 'B2':
        legs.append(('B1', u_in, STAIR_U_B1))
        pts += lane_run(B1, u_in, STAIR_U_B1 - 0.25, off)
        so = STAIR_OFF[ch]
        pts += [B1.off(STAIR_U_B1, off), ST.off(0.05, so), ST.off(ST.L - 0.05, so)]
        legs.append(('STAIR', 0, 1))
        if Z['kind'] == 'FIFO':                     # 大隊 1:從尾端(樓梯側)進,沿自己那路往前
            ut = 1.45
            legs.append(('B2', B2_U_START, ut))
            pts += lane_run(B2, B2_U_START, ut, off)
            pts.append(B2.off(ut + 0.2, slot_offset(lie)))
            pts += lane_run(B2, ut + 0.2, slot_u(lie, i), slot_offset(lie))
        else:                                       # 死巷:在區頭前換到自己那路,往裡走
            ut = Z['head'] - 0.3
            legs.append(('B2', B2_U_START, ut))
            pts += lane_run(B2, B2_U_START, ut, off)
            pts.append(B2.off(Z['head'] - 0.1, slot_offset(lie)))
            pts += lane_run(B2, Z['head'] - 0.1, slot_u(lie, i), slot_offset(lie))
    elif z == 'STAIR':
        legs.append(('B1', u_in, STAIR_U_B1))
        pts += lane_run(B1, u_in, STAIR_U_B1 - 0.35, off)
        j = lane_of(lie)
        pts.append(B1.off(STAIR_U_B1, 0.2 - 0.08 * j))
        pts.append(STAIR_SLOTS[j][-1])
    else:                                           # B1 白:在區尾外換路,沿自己那路往樓梯方向
        tail = Z['head'] + Z['step'] * 35
        ut = max(tail - 0.15, 0.3)
        if u_in < ut:
            legs.append(('B1', u_in, ut))
            pts += lane_run(B1, u_in, ut, off)
            pts.append(B1.off(ut + 0.15, slot_offset(lie)))
            pts += lane_run(B1, ut + 0.15, slot_u(lie, i), slot_offset(lie))
        else:
            legs.append(('B1', u_in, u_in))
            pts.append(B1.off(u_in + 0.1, slot_offset(lie)))
            pts += lane_run(B1, u_in + 0.1, slot_u(lie, i), slot_offset(lie))
    pts.append(tgt)
    return pts, legs

def timed(pts, t0):
    out = [(pts[0][0], pts[0][1], t0)]; t = t0
    for a, b in zip(pts, pts[1:]):
        dd = math.dist(a, b)
        if dd < 1e-6: continue
        t += dd / V; out.append((b[0], b[1], t))
    return out

def time_at_leg(path_len_before, u0, u1, u, t_leave):
    return t_leave + (path_len_before + abs(u - u0)) / V

# 每人的抵達路線(座位、格位固定;時間只差離座時刻)
PERSON = {}
for lie in range(1, 55):
    for i, pai in enumerate(sorted([p['pai'] for p in D['persons'] if p['lie'] == lie], reverse=True)):
        pid = '%d-%d' % (lie, pai)      # i = 格位序 = 6口 路內順序(排大的在最前)
        pts, legs = arrival_route(pid, lie, i)
        # legs 起點距離
        cum = [0.0]
        for a, b in zip(pts, pts[1:]): cum.append(cum[-1] + math.dist(a, b))
        PERSON[pid] = dict(lie=lie, pai=pai, slot=i, pts=pts, legs=legs, L=cum[-1],
                           d_entry=cum[2])

def leg_times(pid, t_leave):
    """回傳每段走廊的 (corr,u0,u1,t0,t1);用直線距離近似"""
    P = PERSON[pid]; out = []
    d = P['d_entry']
    for corr, u0, u1 in P['legs']:
        if corr == 'STAIR':
            L = ST.L
        else:
            L = abs(u1 - u0)
        out.append((corr, u0, u1, t_leave + d / V, t_leave + (d + L) / V)); d += L
    return out

# 各區域(走廊上被站定者佔用的範圍)
def region(z):
    Z = ZONES[z]
    if z == 'STAIR': return [('STAIR', 0, 1), ('B1', STAIR_U_B1 - 0.3, STAIR_U_B1)]
    nmax = max(LIE_N[l] for l in range(1, 55) if zone_of(l) == z)
    a, b = Z['head'], Z['head'] + Z['step'] * (nmax - 1)
    return [(Z['corr'], min(a, b) - 0.1, max(a, b) + 0.1)]
REGION = {z: region(z) for z in ZONES}

def exit_time(lt, reg):
    """路人 legs 時間 lt 穿過 reg 的最晚離開時間(未經過回 None)"""
    best = None
    for corr, a, b in reg:
        for c, u0, u1, t0, t1 in lt:
            if c != corr: continue
            if corr == 'STAIR':
                best = max(best or 0, t1); continue
            lo, hi = min(u0, u1), max(u0, u1)
            if hi < a or lo > b or hi - lo < 1e-9: continue
            uexit = b if u1 > u0 else a
            uexit = min(max(uexit, lo), hi)
            te = t0 + (t1 - t0) * abs(uexit - u0) / (abs(u1 - u0))
            best = max(best or 0, te)
    return best

# ---------- 離座時間(含等候放行) ----------
def schedule():
    delay = collections.defaultdict(float)     # 列的額外延後
    rows_p = collections.defaultdict(list)
    for pid, P in PERSON.items(): rows_p[P['lie']].append(pid)
    for it in range(500):
        start = {}
        for ch in 'ABC':
            t = T0
            for lie in CHAIN_ROWS[ch]:
                t = t + delay[lie]
                start[lie] = t
                t = t + GAP_SEAT * (LIE_N[lie] - 1) + GAP_ROW
        leave = {pid: start[P['lie']] + GAP_SEAT * SEAT_OF[pid]['qi'] for pid, P in PERSON.items()}
        LT = {pid: leg_times(pid, leave[pid]) for pid in PERSON}
        need = {}
        for z in ZONES:
            m = 0
            for pid, lt in LT.items():
                if zone_of(PERSON[pid]['lie']) == z: continue
                e = exit_time(lt, REGION[z])
                if e is not None: m = max(m, e)
            need[z] = m
        changed = False
        for lie in ORDER:
            z = zone_of(lie)
            arr = min(LT[pid][-1][4] for pid in rows_p[lie])
            if need[z] + 0.5 > arr + 1e-6:
                delay[lie] += need[z] + 0.5 - arr
                changed = True
                break                       # 依優先序逐列修正
        if not changed:
            print('排程迭代', it, '延後', {l: round(v, 1) for l, v in delay.items() if v})
            return start, leave
    raise SystemExit('離座排程未收斂')
START, LEAVE = schedule()

# ---------- 進場 ----------
ARR = {}
for pid, P in PERSON.items():
    ARR[pid] = timed(P['pts'], LEAVE[pid])

def depart_route(pid):
    P = PERSON[pid]; lie = P['lie']; z = zone_of(lie); Z = ZONES[z]; j = lane_of(lie); i = P['slot']
    s0 = slot_xy(lie, i)
    if z == 'P1':
        return [s0, tuple(GATE_PTS[j])]
    if Z['corr'] == 'B2':
        o = slot_offset(lie)
        return [s0] + lane_run(B2, slot_u(lie, i), 4.95, o) + [tuple(GATE_PTS[j])]
    if z == 'STAIR':
        pts = STAIR_SLOTS[j]
        return [s0] + [tuple(pts[0])] + white_route(j, None, None)[2:]
    return [s0] + white_route(j, slot_u(lie, i), slot_offset(lie))

DEP = {pid: depart_route(pid) for pid in PERSON}
def plen(pts): return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))
T_DADUI = {}
GATE_T = {}
prev_end = None
for d in range(1, 10):
    pids = [pid for pid in PERSON if dadui_of(PERSON[pid]['lie']) == d]
    need = 0
    for pid in pids:
        P = PERSON[pid]
        rel = GATE_GAP * P['slot'] + LANE_STAGGER * lane_of(P['lie'])
        need = max(need, ARR[pid][-1][2] + 0.6 + plen(DEP[pid]) / V - rel)
    T = need if prev_end is None else max(need, prev_end + DADUI_GAP)
    T_DADUI[d] = T
    for pid in pids:
        P = PERSON[pid]
        GATE_T[pid] = T + GATE_GAP * P['slot'] + LANE_STAGGER * lane_of(P['lie'])
    prev_end = max(GATE_T[pid] for pid in pids)

# ---------- 組 path ----------
persons = []
for op in D['persons']:
    pid = op['id']; P = PERSON[pid]; lie = P['lie']; s = SEAT_OF[pid]
    arr = ARR[pid]
    t_as = arr[-1][2]
    g = GATE_T[pid]; dep = DEP[pid]
    dep_t = g - plen(dep) / V
    path = list(arr)
    path.append((arr[-1][0], arr[-1][1], dep_t))
    path += timed(dep, dep_t)[1:]
    # 6口 之後:沿用舊版場內幾何,等速重新計時
    post = [q for q in op['path'] if q[2] > op['t']['gate'] + 1e-6]
    t = path[-1][2]; last = path[-1]
    for x, y, _ in post:
        t += math.dist((last[0], last[1]), (x, y)) / V; path.append((x, y, t)); last = (x, y)
    path = [[round(x, 3), round(y, 3), round(tt, 2)] for x, y, tt in path]
    # 去除時間重複的點
    clean = [path[0]]
    for q in path[1:]:
        if q[:2] == clean[-1][:2] and abs(q[2] - clean[-1][2]) < 1e-9: continue
        clean.append(q)
    z = zone_of(lie)
    np_ = dict(op)
    np_.update(dict(
        zu='B2' if ZONES[z]['corr'] == 'B2' else 'B1',
        qi=s['qi'], gateIdx=P['slot'], laneIdx=lane_of(lie),
        walkLane='ABC'.index(s['chain']), corrLane=CORR_LANE[(s['chain'], costume_of(lie))],
        rest=dict(sec=s['sec'], pai=s['pai'], no=s['no'], X=s['X'], Y=s['Y']),
        block=s['block'], chain=s['chain'], exitWave=s['exitWave'], exitSide=s['exitSide'],
        assembly=z, gate='GATE6',
        t=dict(leave=round(LEAVE[pid], 2), assembly=round(t_as, 2), enter=round(dep_t, 2),
               gate=round(g, 2), arrive=clean[-1][2]),
        path=clean))
    persons.append(np_)

TEND = max(p['t']['arrive'] for p in persons)
print('全長', round(TEND, 2), '秒;大隊起點', {d: round(t, 1) for d, t in T_DADUI.items()})

# ---------- 列資料 ----------
SIDE_LABEL = {}
for f in D['files']:
    for b in f['blocks']: SIDE_LABEL[b['block']] = b['exitSideLabel']
files = []
for lie in range(1, 55):
    ps = sorted([p for p in persons if p['lie'] == lie], key=lambda p: p['qi'])
    blocks = []
    for p in ps:
        if not blocks or blocks[-1]['block'] != p['block']:
            blocks.append(dict(block=p['block'], chain=p['chain'], first=p, n=0, exitWave=p['exitWave'], exitSide=p['exitSide'],
                               exitSideLabel=SIDE_LABEL[p['block']]))
        blocks[-1]['n'] += 1; blocks[-1]['last'] = p
    bl = [dict(block=b['block'], chain=b['chain'],
               **{'from': '%s區%d排%d號' % (b['first']['rest']['sec'], b['first']['rest']['pai'], b['first']['rest']['no'])},
               to='%s區%d排%d號' % (b['last']['rest']['sec'], b['last']['rest']['pai'], b['last']['rest']['no']),
               n=b['n'], exitWave=b['exitWave'], exitSide=b['exitSide'], exitSideLabel=b['exitSideLabel'],
               chainIdx=CHAIN_ROWS[b['chain']].index(lie)) for b in blocks]
    z = zone_of(lie)
    lifo = ZONES[z]['kind'] == 'LIFO'
    files.append(dict(lie=lie, dadui=dadui_of(lie), costume=costume_of(lie), zu=ps[0]['zu'], n=len(ps),
                      order=[p['id'] for p in ps],
                      direction='離座 頭→尾(排1→排大);進場 排大→1(由排 1 端進列)' if lifo else '離座 尾→頭(排大→1);進場 排大→1(由排 1 端進列)',
                      blocks=bl, assembly=z, entryLane=costume_of(lie), entryIdx=lane_of(lie),
                      stairLane=ps[0]['walkLane'], walkLane=ps[0]['walkLane'], corrLane=ps[0]['corrLane'],
                      entryDadui=dadui_of(lie), tDaduiStart=round(T_DADUI[dadui_of(lie)], 2),
                      tGate=round(min(p['t']['gate'] for p in ps), 2), tLeave=round(min(p['t']['leave'] for p in ps), 2),
                      tAssembly=round(max(p['t']['assembly'] for p in ps), 2), tEnter=round(min(p['t']['enter'] for p in ps), 2),
                      tArrive=round(max(p['t']['arrive'] for p in ps), 2)))

# ---------- 輸出 ----------
nodes = json.loads(json.dumps(D['nodes']))
for k, Z in ZONES.items():
    if k in nodes:
        nodes[k]['label'] = Z['label']
        if Z['corr'] == 'B1':
            x, y = B1.at(Z['head']); nodes[k]['X'], nodes[k]['Y'] = round(x, 3), round(y, 3)
nodes['STAIR_TOP']['label'] = '樓梯(B1)'
rest = []
who = {(p['rest']['sec'], p['rest']['pai'], p['rest']['no']): p['id'] for p in persons}
for s in D['restSeats']:
    rest.append(dict(s, who=who.get((s['sec'], s['pai'], s['no']))))
last_leave = max(p['t']['leave'] for p in persons)
last_as = max(p['t']['assembly'] for p in persons)
meta = dict(D['meta'])
meta.update(title='入經藏 西一+桃竹 休息區→集結→進場 動畫資料(藍衣全部 B2 集結版)', built='2026-10-18',
            population=len(persons), tEnd=round(TEND, 2),
            waveStart={str(w): round(min(p['t']['leave'] for p in persons if p['exitWave'] == w), 2) for w in (1, 2, 3, 4)})
out = dict(meta=meta,
           phases=[dict(key='seated', label='休息區就座', t0=0, t1=6.0),
                   dict(key='exit', label='三條鏈各走一路拉出(藍衣與大隊 1 先、白衣後)', t0=6.0, t1=round(last_leave, 2)),
                   dict(key='assemble', label='藍衣下 B2、白衣留 B1 集結', t0=6.0, t1=round(last_as, 2)),
                   dict(key='enter', label='大隊 1→9 由 6口 六路進場 → 排 1 外側通道 → 身分證隊形', t0=round(T_DADUI[1], 2), t1=round(TEND, 2))],
           nodes=nodes, map=D['map'], restSeats=rest, files=files, persons=persons, others=D['others'])
json.dump(out, open(OUT, 'w'), ensure_ascii=False, separators=(',', ':'))
plan = dict(assign=ASSIGN, chainRows=CHAIN_ROWS, cap=CAP, tDadui=T_DADUI, tEnd=TEND,
            seats={pid: dict(sec=s['sec'], pai=s['pai'], no=s['no'], chain=s['chain'], qi=s['qi'], block=s['block'],
                             exitWave=s['exitWave'], extra=s.get('extra', False)) for pid, s in SEAT_OF.items()},
            zones={k: dict(label=v['label'], floor=v['floor'], kind=v['kind']) for k, v in ZONES.items()},
            rowStart={l: round(t, 2) for l, t in START.items()})
json.dump(plan, open(PLAN, 'w'), ensure_ascii=False, indent=1)
