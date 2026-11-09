"""版本 3 排程：一個時鐘（樓梯口兩路、大隊交界對齊），拉式倒推離座時刻（spec §3.4），輸出 data.json 與 seats.csv。
隊頭之後一排六人並肩走 march.py 的中心線（整排轉彎，spec §3.4c），在沿牆迴廊停好等下一大隊排滿（迴廊候隊，spec §3.4d），到自己大隊列區南緣分出、梯次進列。

用法: python3 build.py base.json plan.json ../data.json ../seats.csv [--no-avoid]
"""
import bisect
import collections
import csv
import json
import math
import sys

import march
import plan
import routes

V = 1.1                 # 單位/秒
HEADWAY = 0.2           # 樓梯／走廊同一路相鄰兩人（一個接一個緊跟；下樓分成三條線後每條線約 0.6 秒一位）
STAGGER = 0.17          # 兩路錯開
T0 = 6.73               # 第一人離座
DADUI_GAP = 0.8         # 大隊交界的對齊空檔：前一大隊隊尾先過西一入口線的轉入點
SLOW_STEP, SLOW_MIN, AVOID_ROUNDS = 0.05, 0.7, 30   # 避撞：進列時橫走那一段每次放慢 0.05 倍步速，最低 0.7 倍
RANK_GAP = 0.2          # 每個大隊排滿門前隊伍後，一排緊跟一排離開隊頭（0.2 秒 × 1.1 = 0.22 單位 ≈ 1.7 m）；0.13 秒會和「橫走一欄 0.12 秒」同步而在欄間空隙相撞
SLOW = 0.075 / RANK_GAP # 門前隊伍往前補一格的速度（單位/秒）：前後間距 QUEUE_STEP 0.075、每 RANK_GAP 秒補一格
STAGE_D = 0.17          # 迴廊候隊：大隊在沿牆迴廊停好時的排距（最多 34 排放進北轉前 5.7 單位）
STAGE_PAUSE = 1.0       # 迴廊候隊：前一大隊停好、下一大隊在門前隊伍排滿之後，稍停這麼久前一大隊才繼續走
FILL_PAUSE = 1.0        # 大隊 1 把門前隊伍排滿後，稍停這麼久才開始推進
GATE_DRAW_AFTER = 1.0   # 圖面六條線畫到穿過西一入口之後這麼久（秒）
WAIT_MIN = 0.01         # 路徑上同一點停不到這麼久就不留停留點
WEST_SAFE = 0.036       # 往西進列者的走法離其他人至少這麼遠才算可行（碰撞點距 0.03 加餘量）
WEST_WAITS = [k * 0.05 for k in range(61)]   # 往西進列者在自己那一列轉角可以先等多久再橫越（秒，由短到長試）
LANE_K = {'A': 0, 'B': 1}
DIRECT_LABEL = '門前隊伍（B2）'


def cum(pts):
    out = [0.0]
    for a, b in zip(pts, pts[1:]):
        out.append(out[-1] + math.dist(a, b))
    return out


def timed(pts, t0):
    out = [(pts[0][0], pts[0][1], t0)]
    t = t0
    for a, b in zip(pts, pts[1:]):
        dd = math.dist(a, b)
        if dd < 1e-9:
            continue
        t += dd / V
        out.append((b[0], b[1], t))
    return out


def march_of(G):
    """整排並肩的中心線與時間剖面（所有排共用，只差 t.enter）。"""
    if not hasattr(G, 'march'):
        G.march = march.March(G, G.D, routes.QUEUE_HEAD)
    return G.march


def split_points(G, people):
    """每個大隊在哪裡分出（中心線弧長 s）：北行直線上，整排走到該大隊最南一列之南 SPLIT_AHEAD 處。"""
    M = march_of(G)
    out = {}
    for d in sorted({p['dadui'] for p in people}):
        ps = [p for p in people if p['dadui'] == d]
        out[d] = M.split_s(max(p['field']['Y'] for p in ps))
    return out


def prepare(G, people):
    """每人的路線與距離（不含時間）：to 從座位到自己那條線的起點（d_top 是其中到樓梯口的路程）。"""
    R = {}
    for p in people:
        to = G.entry_route(p)
        c = cum(to)
        R[p['id']] = dict(to=to, L_to=c[-1], d_top=c[G.stair_top_index(to)])
    return R


def aligned_clock(items, key_lane, key_seq, key_group, stagger_of, group_gap=0.0, extra=None):
    """連續時鐘，各路在「群」（大隊）交界對齊：群 g 在所有路同時起拍 = 各路上一群最後一拍（含錯開）的最大值 + HEADWAY + group_gap。
    回傳相對時刻（第一群第一拍 = 0）與各群起拍時刻。"""
    lanes = sorted({it[key_lane] for it in items})
    groups = sorted({it[key_group] for it in items})
    by = collections.defaultdict(list)
    for it in items:
        by[(it[key_group], it[key_lane])].append(it)
    rel, t_group, prev_end = {}, {}, None
    for g in groups:
        t0 = 0.0 if prev_end is None else prev_end + HEADWAY + group_gap + (extra or {}).get(g, 0.0)
        t_group[g] = t0
        ends = []
        for L in lanes:
            ps = sorted(by.get((g, L), []), key=lambda it: it[key_seq])
            for n, it in enumerate(ps):
                rel[it['id']] = t0 + HEADWAY * n + stagger_of(it)
            if ps:
                ends.append(t0 + HEADWAY * (len(ps) - 1) + stagger_of(ps[-1]))
        prev_end = max(ends)
    return rel, t_group


def head_rank(ranks, t):
    """此刻排在隊頭的是第幾排（連續值）：第 k 排在 ranks[k] 離開隊頭，後面一排用 RANK_GAP 秒慢慢補上一格。"""
    if not ranks or t < ranks[0]:
        return 0.0
    k = bisect.bisect_right(ranks, t) - 1
    return k + min(1.0, (t - ranks[k]) / RANK_GAP)


def slot_s(line, r, ranks, t):
    """第 r 排在自己那條線上的位置（弧長）：隊頭往後 (r − 隊頭排號) 格，一格 QUEUE_STEP。"""
    return line.L - routes.QUEUE_STEP * (r - head_rank(ranks, t))


def rank_numbers(people):
    """排號：每個大隊從新的一排開始，大隊內第 slot 位就在第 slot 排；大隊人數少的那幾條線，大隊尾巴的幾排是空位。
    （不讓下一大隊往前補：下一大隊的場內路線會穿過上一大隊還沒站定的位置。）"""
    n = collections.Counter((p['dadui'], p['gateLane']) for p in people)
    start, off = {}, 0
    for d in sorted({p['dadui'] for p in people}):
        start[d] = off
        off += max(c for (dd, _), c in n.items() if dd == d)
    return {p['id']: start[p['dadui']] + p['slot'] for p in people}


def schedule(G, people, R=None):
    """排程（見 _schedule_once）。北行段「第 10 排切齊、到齊才一起起步」讓每排間隔拉長、進場變慢，門前隊伍消化得比下樓慢：
    某個大隊下樓時，門前隊伍裡自己那一格還在側移完成點（routes.QUEUE_MIN_U）之前（隊伍太長），就把這個大隊（與之後的大隊）的樓梯時鐘往後挪，
    挪到每人走到自己那條線時那一格都已經在線上為止。一次只挪最前面那個有問題的大隊，重算到沒有問題。"""
    R = R or prepare(G, people)
    extra = {}
    for _ in range(40):
        out, clocks = _schedule_once(G, people, R, extra)
        late = {}
        for p in people:
            j, r, t_e = p['gateLane'], clocks['rankOf'][p['id']], out[p['id']]['entry']
            line, s_min = G.line_poly(j), G.line_min_s(j) + 0.01
            if slot_s(line, r, clocks['ranks'], t_e) >= s_min:
                continue
            t = t_e
            while slot_s(line, r, clocks['ranks'], t) < s_min and t < t_e + 600:
                t += 0.05
            late[p['dadui']] = max(late.get(p['dadui'], 0.0), t - t_e)
        if not late:
            clocks['stairDelay'] = {d: round(v, 3) for d, v in extra.items()}
            plans = plan_west(G, people, out, clocks)  # 往西進列的人最後排（不影響別人）
            clocks['westPlan'] = {pid: pl for pid, (pl, _) in plans.items()}
            for pid, (_, w0) in plans.items():
                out[pid]['westWait'] = w0
            return out, clocks
        d = min(late)
        extra[d] = extra.get(d, 0.0) + late[d] + 0.05
    raise SystemExit(f'門前隊伍一直放不下：{late}')


def _schedule_once(G, people, R, extra):
    """兩個時鐘（spec §3.4、§3.4c）：
    1. 樓梯口時刻 S（兩路、大隊交界對齊）；下樓後以步速走到自己那條線的起點（t.entry）。
    2. 門前隊伍：六條線同一個排號的人是一排（rank_numbers：每個大隊從新的一排開始），一排一起離開隊頭（t.enter），
       之後整排並肩沿 march 中心線走（t.gate = 穿過全壘打牆的時刻、t.split = 在自己大隊列區南緣分出）。
       每個大隊全員排進隊伍後 FILL_PAUSE 秒第一排出發，之後一排緊跟一排（RANK_GAP）；隊伍前後間距 QUEUE_STEP。
    3. 迴廊候隊（spec §3.4d）：大隊 d 走到沿牆迴廊停好（第 i 排停在北轉前 i × STAGE_D）；大隊 d + 1 在門前隊伍排滿後 STAGE_PAUSE 秒，
       大隊 d 再出發，每一排等前一排走開 RANK_GAP 才跟上；大隊 d + 1 第一排跟在大隊 d 最後一排之後至少 RANK_GAP（迴廊同一時間只放一個大隊）。
       停的起訖記在 t.holdStart / t.holdEnd；最後一個大隊不停。
       每人下樓後以步速追上自己的位置（t.assembly），之後跟著隊伍走。"""
    rel, _ = aligned_clock(people, 'lane', 'dadIdx', 'dadui', lambda it: STAGGER * LANE_K[it['lane']], group_gap=DADUI_GAP, extra=extra)
    T_S0 = max(T0 + R[p['id']]['d_top'] / V - rel[p['id']] for p in people)
    stair = {p['id']: T_S0 + rel[p['id']] for p in people}
    entry = {p['id']: stair[p['id']] + (R[p['id']]['L_to'] - R[p['id']]['d_top']) / V for p in people}
    rank_of = rank_numbers(people)
    n_rank = 1 + max(rank_of.values())
    reach = [0.0] * n_rank                            # 這一排每個人都走得到隊頭的最早時刻
    for p in people:
        line, r = G.line_poly(p['gateLane']), rank_of[p['id']]
        reach[r] = max(reach[r], entry[p['id']] + line.L / V)
    # 每個大隊全員排進門前隊伍後 FILL_PAUSE 秒，第一排出發，之後一排緊跟一排（RANK_GAP）
    def caught(p, ranks):                             # 步速追上自己的位置：走的弧長 = 隊伍裡那一格的弧長
        line, r, t_e = G.line_poly(p['gateLane']), rank_of[p['id']], entry[p['id']]
        if slot_s(line, r, ranks, t_e) <= 0:
            return t_e                                # 隊伍排到線的起點後面（太長），check.py 會抓出來
        lo, hi = t_e, t_e + 60
        for _ in range(60):
            mid = (lo + hi) / 2
            if (mid - t_e) * V < slot_s(line, r, ranks, mid):
                lo = mid
            else:
                hi = mid
        return hi
    M = march_of(G)
    split = split_points(G, people)
    s_stage_end = M.sp0                               # 迴廊候隊：沿牆迴廊的北端（北轉弧開始）
    tau_end = M.tau_at_s(s_stage_end)
    by_rank = collections.defaultdict(list)
    for p in people:
        by_rank[rank_of[p['id']]].append(p)
    daduis = sorted({p['dadui'] for p in people})
    wins = collections.defaultdict(list)              # 大隊 → 該大隊各排在切齊線上「前面停」的時段 (開始, 結束)，依排序
    tl = {}                                           # 每人 t.enter 之後的時間軸（timeline）

    def run_rank(r, t0, hold=None):
        """第 r 排在 t0 離開隊頭（hold：迴廊停的 (τ, 再出發的時刻)）：算每人的時間軸，並把這一排在切齊線上停的時段加進 wins。
        前面停後面也停：同一大隊前面幾排（最後一個大隊另外加上前一大隊）有人在切齊線上等對齊時，這一排還沒走到自己那一列的人原地停住。"""
        ps = by_rank[r]
        d = ps[0]['dadui']
        ws = sorted(wins[d])                          # 同一大隊前面幾排：一直適用
        wp = sorted(wins.get(d - 1, []))              # 前一大隊：離開迴廊之後（最後一個大隊離開隊頭之後）才適用，免得前一大隊尾巴停住時被追上
        for p in ps:
            tl[p['id']] = timeline(M, p, split[d], t0, hold, ws, wp)
        arr = [tl[p['id']]['tWait'] for p in ps if tl[p['id']]['tWait'] is not None]
        if arr:
            wins[d].append((min(arr), max(arr)))
            for p in ps:
                if tl[p['id']]['tWait'] is not None:
                    tl[p['id']]['release'] = max(arr)

    def real_at(pid, tau):
        """這個人在走路時間 τ（相對 t.enter，不含停）那一刻的實際時刻。"""
        x = tl[pid]
        return x['t0'] + tau + sum(e - s for ts, s, e, _ in x['stops'] if ts < tau - 1e-12)

    stage = {}                                        # 排號 → (停在哪個 s, 從那裡再出發的時刻)
    staged_ranks = {}                                 # 大隊 → 它在迴廊停的那些排號
    ranks = []
    for d_prev, d in zip([None] + daduis, daduis):
        ps = [p for p in people if p['dadui'] == d]
        fill = max(caught(p, ranks) for p in ps)
        r0, r1 = min(rank_of[p['id']] for p in ps), max(rank_of[p['id']] for p in ps)
        lo = 0.0
        if d_prev in staged_ranks:
            # 迴廊候隊：前一大隊在迴廊停好、這一大隊在門前隊伍排滿，兩個都到齊後前一大隊整塊出發（每排間隔 RANK_GAP，緊密前進）；
            # 之後前面停後面也停（run_rank）。這一大隊第一排要等前一大隊最後一排走過迴廊北端 0.3 秒以上才走到那裡
            rs = staged_ranks[d_prev]
            staged = max(ranks[r] + M.tau_at_s(stage[r][0]) for r in rs)
            rel = max(staged, fill) + STAGE_PAUSE
            prev, target = None, rel
            for i, r in enumerate(rs):
                s_r = stage[r][0]
                target += RANK_GAP if i else 0.0
                go = max(ranks[r] + M.tau_at_s(s_r), target - (tau_end - M.tau_at_s(s_r)))
                if prev is not None:
                    go = max(go, prev[1] + RANK_GAP - (M.tau_at_s(prev[0]) - M.tau_at_s(s_r)))
                stage[r] = (s_r, go)
                prev = (s_r, go)
                run_rank(r, ranks[r], (M.tau_at_s(s_r), go))
            last = by_rank[rs[-1]][0]['id']
            lo = max(prev[1] - M.tau_at_s(prev[0]) + RANK_GAP, real_at(last, tau_end + 0.3) - tau_end)
        for r in range(r0, r1 + 1):
            behind = ranks[-1] + RANK_GAP if ranks else 0.0
            if d == daduis[-1] and ranks and by_rank[r - 1][0]['id'] in tl:   # 前一排途中停過：等它實際走開 RANK_GAP 的距離
                behind = max(behind, real_at(by_rank[r - 1][0]['id'], RANK_GAP))
            g0 = max(reach[r], behind, max(fill + FILL_PAUSE, lo) if r == r0 else 0.0)
            if d == daduis[-1]:                       # 最後一個大隊不停：前面停的時候，隊頭這一排也等
                ws = sorted(wins[d] + wins.get(d - 1, []))
                moved = True
                while moved:                          # 出發後 RANK_GAP 內就會遇到停（或正在停）：等那次停結束再離開隊頭，
                    moved = False                     # 免得停在隊頭前一步、下一排補到隊頭時靠太近
                    for a, b in ws:
                        if a - RANK_GAP - 1e-9 <= g0 < b:
                            g0, moved = b, True
            ranks.append(g0)
            if d == daduis[-1]:
                run_rank(r, g0)
        if d != daduis[-1]:                           # 最後一個大隊後面沒有人要等，不停
            staged_ranks[d] = list(range(r0, r1 + 1))
            if s_stage_end - (r1 - r0) * STAGE_D < M.s_walk:
                raise SystemExit(f'大隊 {d} 有 {r1 - r0 + 1} 排，沿牆迴廊放不下（最後一排會停在西一入口的轉彎裡）')
            for r in staged_ranks[d]:
                stage[r] = (s_stage_end - (r - r0) * STAGE_D, None)
    out = {}
    for p in people:
        pid, r = p['id'], rank_of[p['id']]
        x = tl[pid]
        tau_split = M.tau_at_s(split[p['dadui']])
        out[pid] = dict(leave=stair[pid] - R[pid]['d_top'] / V, stair=stair[pid], entry=entry[pid], assembly=caught(p, ranks), enter=ranks[r],
                        gate=real_at(pid, M.tau_gate[p['gateLane']]), split=real_at(pid, tau_split), tl=x)
        hs = [(s, e) for _, s, e, k in x['stops'] if k == 'hold']
        if hs:
            out[pid]['holdStart'], out[pid]['holdEnd'] = hs[0][0], hs[-1][1]
        out[pid]['waits'] = [(s, e) for _, s, e, k in x['stops'] if k == 'freeze']
        if x['tWait'] is not None:                    # 座位在第 10 排以東：在切齊線上等同一排到齊（最後到的那位不必停）
            out[pid]['alignStart'], out[pid]['alignEnd'] = x['tWait'], x['release']
    if any(abs(out[p['id']]['enter'] - tl[p['id']]['t0']) > 1e-9 for p in people):
        raise SystemExit('排程內部不一致：離開隊頭的時刻和時間軸不同')
    blk = {d: merge_windows(list(wins.get(d, [])) + list(wins.get(d - 1, []))) for d in daduis}
    for p in people:
        out[p['id']]['tl']['W'] = blk[p['dadui']]
    return out, dict(tStairStart=T_S0, tGateStart=min(v['gate'] for v in out.values()), ranks=ranks, rankOf=rank_of, split=split, stage=stage,
                     wins={d: list(v) for d, v in wins.items()})


def merge_windows(ws):
    """停的時段取聯集、排好。"""
    out = []
    for a, b in sorted(ws):
        if out and a <= out[-1][1] + 1e-9:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


class BlockClock:
    """大隊的「走路時鐘」：實際時刻扣掉這個大隊（與前一大隊）停的時段。往西進列的人和往北走的人都跟著停，
    所以在這個時鐘上大家都不停，往西的走法在這個時鐘上排（march.west_plan_obs），再換回實際時刻、插入停。"""

    def __init__(self, W):
        self.W = W
        self.cum = [0.0]
        for a, b in W:
            self.cum.append(self.cum[-1] + b - a)

    def b(self, t):
        k = bisect.bisect_right([a for a, _ in self.W], t)
        frozen = self.cum[k - 1] if k else 0.0
        if k:
            a, e = self.W[k - 1]
            frozen += min(t, e) - a if t < e else 0.0
            frozen = self.cum[k - 1] + (min(t, e) - a) if t < e else self.cum[k]
        return t - frozen

    def t(self, bb):
        """走路時鐘 bb 對應的實際時刻（停的時段裡取結束那一刻：之後就開始走）。"""
        t = bb
        for (a, e), c in zip(self.W, self.cum):
            if a - c <= bb + 1e-12:
                t = bb + c + (e - a) if a - c < bb - 1e-12 else bb + c
            else:
                break
        return t


def timeline(M, p, s_split, t0, hold, ws, wp=()):
    """一個人 t.enter 之後的時間軸：走路時間 τ（相對 t.enter，不含停）與實際時刻的對應。
    stops = [(τ, 開始, 結束, 種類)]：'hold' 迴廊停、'freeze' 前面停後面也停（走到自己那一列的轉向點之前；座位在第 10 排以東的人
    到走到切齊線為止）。ws：同一大隊前面幾排停的時段；wp：前一大隊停的時段，只在迴廊停完之後適用。
    tTurn：走到轉向點的實際時刻；tWait：座位在第 10 排以東的人走到切齊線的時刻（其他人 None）。"""
    seat = (p['field']['X'], p['field']['Y'])
    j = p['gateLane']
    (ax, yt), _ = M.turn_point(j, seat)
    tau_split = M.tau_at_s(s_split)
    y_split = M.lane_xy(s_split, j)[1]
    tau_turn = tau_split + (y_split - yt) / V
    kind = M.kind(j, seat)
    tau_wait = tau_turn + (march.ALIGN_X - ax) / V if kind == 'align' else None
    st = dict(t=t0, tau=0.0, stops=[])

    def stop(tau, a, b, k):
        if b - a < 1e-9:
            return
        if st['stops'] and abs(st['stops'][-1][0] - tau) < 1e-12 and abs(st['stops'][-1][2] - a) < 1e-9:
            t_, a_, _, k_ = st['stops'][-1]
            st['stops'][-1] = (t_, a_, b, k_)        # 接著上一段停（迴廊停完緊接著前面停）
        else:
            st['stops'].append((tau, a, b, k))

    def move_to(tau_target, wl):
        while st['tau'] < tau_target - 1e-12:
            dt = tau_target - st['tau']
            w = next(((a, b) for a, b in wl if b > st['t'] + 1e-9 and a < st['t'] + dt - 1e-9), None)
            if w is None:
                st['t'] += dt
                st['tau'] = tau_target
                return
            if w[0] > st['t']:
                st['tau'] += w[0] - st['t']
                st['t'] = w[0]
            stop(st['tau'], st['t'], w[1], 'freeze')
            st['t'] = w[1]

    if hold:
        tau_h, go = hold
        move_to(tau_h, ws)
        b = max(go, st['t'])
        stop(tau_h, st['t'], b, 'hold')
        st['t'] = b
    both = sorted(list(ws) + list(wp))
    move_to(tau_turn, both)
    t_turn = st['t']
    t_wait = None
    if tau_wait is not None:
        move_to(tau_wait, both)
        t_wait = st['t']
    return dict(t0=t0, stops=st['stops'], sSplit=s_split, tauSplit=tau_split, tauTurn=tau_turn, tTurn=t_turn, kind=kind, corner=(ax, yt),
                tauWait=tau_wait, tWait=t_wait, release=None)


def person_path(G, p, r, t, ranks, rank, plan=None):
    """座位 → 自己那條線的起點 → 步速追上隊伍 → 跟著隊伍（慢行或站住）到隊頭
    → 一排六人並肩沿 march 中心線（整排轉進西一入口、沿牆、北轉、沿第 5–10 排地標直線北行）→ 在自己大隊列區南緣分出
    → 沿自己那一路走到自己那一列 → 座位（步速）。t.enter 之後依時間軸 t['tl'] 插入停：迴廊停、前面停後面也停、切齊線上等到齊、往西者在轉角等。"""
    line = G.line_poly(p['gateLane'])
    path = list(timed(r['to'], t['leave']))
    s_join = (t['assembly'] - t['entry']) * V
    path += [(x, y, t['entry'] + s / V) for x, y, s in _line_pts(line, 0.0, s_join)][1:]
    # 隊伍裡：排號改變的時刻（離開隊頭、補上一格）是折點，速度不變的折點省略
    knots = [t['assembly']] + sorted({k for g in ranks[:rank] for k in (g, g + RANK_GAP) if t['assembly'] + 1e-9 < k < t['enter'] - 1e-9}) + [t['enter']]
    su = [(k, slot_s(line, rank, ranks, k)) for k in knots]
    su[0], su[-1] = (t['assembly'], s_join), (t['enter'], line.L)
    keep = [su[0]]
    for i in range(1, len(su) - 1):
        (t0, s0), (t1, s1), (t2, s2) = keep[-1], su[i], su[i + 1]
        if abs((s1 - s0) / max(t1 - t0, 1e-9) - (s2 - s1) / max(t2 - t1, 1e-9)) > 1e-6:
            keep.append(su[i])
    keep.append(su[-1])
    for (t0, s0), (t1, s1) in zip(keep, keep[1:]):
        pts = _line_pts(line, s0, s1)
        for x, y, s in pts[1:]:
            path.append((x, y, t0 + (t1 - t0) * ((s - s0) / (s1 - s0) if s1 - s0 > 1e-9 else 1.0)))
    path += after_enter(G, p, t['tl'], plan, t.get('westWait', 0.0))[1:]
    rounded = [[round(x, 3), round(y, 3), round(z, 3)] for x, y, z in path]
    clean = [rounded[0]]
    for q in rounded[1:]:
        if q[:2] == clean[-1][:2] and q[2] - clean[-1][2] < WAIT_MIN:
            if len(clean) >= 2 and clean[-2][:2] == clean[-1][:2]:
                clean[-1] = [clean[-1][0], clean[-1][1], q[2]]   # 接在一段停後面的短停：併進那一段停（刪掉會讓下一段變慢）
                continue
            if q[2] < t['enter'] - 1e-9 or q[2] - clean[-1][2] < 0.0015:
                continue                              # 進場前的短停、四捨五入造成的重複點：省略
        if q[2] <= clean[-1][2] and q[:2] != clean[-1][:2]:
            q = [q[0], q[1], round(clean[-1][2] + 0.001, 3)]
        clean.append(q)
    return clean


def after_enter(G, p, tl, plan=None, west_wait=0.0, upto_corner=False):
    """t.enter 之後的路線（含 t.enter 那一點）：(x, y, 實際時刻)。基準路線用走路時間 τ（不含停）排好，再依時間軸插入停。
    upto_corner：只到轉向點（座位在第 10 排以東的人到切齊線）為止，給往西進列者排走法時當障礙物用。"""
    M = march_of(G)
    seat = (p['field']['X'], p['field']['Y'])
    j = p['gateLane']
    s_split = tl['sSplit']
    base = [(x, y, tau) for x, y, tau in M.lane_track(j, s_split)]
    _, _, tx, ty, _ = M.C.at(s_split)
    plan_pts = None if tl['kind'] != 'west' else (plan if plan is not None else march.west_plan(tl['corner'][0], tl['corner'][1], seat[0]))
    approach, depart = M.tail(base[-1][:2], (tx, ty), seat, plan=plan_pts)
    stops = [(a, b_, c, k) for a, b_, c, k in tl['stops']]
    tau, last = base[-1][2], base[-1]
    for q in approach:
        tau += math.dist(last[:2], q[:2]) / V
        base.append((q[0], q[1], tau))
        last = base[-1]
    if tl['kind'] == 'align' and tl['release'] is not None:
        stops.append((tau, tl['tWait'], tl['release'], 'align'))
    if tl['kind'] == 'west':
        pre = realize(tl['t0'], base, sorted(stops))
        if upto_corner:
            return pre
        return pre + west_depart(tl, base[-1][:2], depart, west_wait, seat)
    if not upto_corner:
        for q in depart:
            tau += math.dist(last[:2], q[:2]) / (V * (q[2] if len(q) > 2 else 1.0))
            base.append((q[0], q[1], tau))
            last = base[-1]
    return realize(tl['t0'], base, sorted(stops))


def west_depart(tl, corner, depart, w0, seat):
    """往西進列者轉角之後：在走路時鐘上先站 w0，照 depart 走（含速度倍數），再換回實際時刻；這段時間大隊停的時段他也停。"""
    BC = BlockClock(tl.get('W', []))
    b = BC.b(tl['tTurn']) + w0
    pts, last = [], corner
    bts = []
    for q in depart:
        b += math.dist(last, q[:2]) / (V * (q[2] if len(q) > 2 else 1.0))
        bts.append((q[0], q[1], b))
        last = q[:2]
    seq = [(corner[0], corner[1], BC.b(tl['tTurn']))] + [(corner[0], corner[1], BC.b(tl['tTurn']) + w0)] + bts
    out = []
    for (x0, y0, b0), (x1, y1, b1) in zip(seq, seq[1:]):
        t0, t1 = BC.t(b0), BC.t(b1)
        for a, e in tl.get('W', []):                 # 這一段裡大隊停的時段：在那一點站住
            if t0 - 1e-9 <= a < t1 - 1e-9:
                f = (BC.b(a) - b0) / (b1 - b0) if b1 > b0 else 0.0
                px, py = x0 + (x1 - x0) * f, y0 + (y1 - y0) * f
                out += [(px, py, a), (px, py, e)]
        out.append((x1, y1, t1))
    return out


def realize(t0, base, stops):
    """基準路線 [(x, y, τ)]（τ = 走路時間，不含停）加上停 [(τ, 開始, 結束, 種類)] → [(x, y, 實際時刻)]。"""
    out, shift, si = [], 0.0, 0
    prev = None
    for x, y, tau in base:
        while si < len(stops) and stops[si][0] <= tau + 1e-12:
            ts, a, b, _ = stops[si]
            if prev is None or tau - prev[2] < 1e-12:
                px, py = x, y
            else:
                f = (ts - prev[2]) / (tau - prev[2])
                px, py = prev[0] + (x - prev[0]) * f, prev[1] + (y - prev[1]) * f
            if abs(t0 + ts + shift - a) > 1e-6:
                raise SystemExit(f'時間軸不一致：τ {ts:.3f} 應在 {a:.3f}，算出 {t0 + ts + shift:.3f}')
            out += [(px, py, a), (px, py, b)]
            shift += b - a
            si += 1
        out.append((x, y, t0 + tau + shift))
        prev = (x, y, tau)
    if si < len(stops):
        ts, a, b, _ = stops[si]
        if abs(ts - prev[2]) < 1e-9:
            out.append((prev[0], prev[1], b))
    return out


def plan_west(G, people, sched, clocks):
    """往西進列的人最後排：其他人的時間軸都定了（往西的人不影響別人停不停），依走到轉角的先後，
    每人拿同一大隊其他人的實際軌跡當障礙物（還沒排的往西者只算到轉角為止），試在轉角先等 WEST_WAITS，
    找第一個離所有人都 ≥ WEST_SAFE 的走法（march.west_plan_obs）。回傳 {往西者: (走法, 先等幾秒)}。"""
    import numpy as np
    M = march_of(G)
    P = {p['id']: p for p in people}
    full, pre = {}, {}
    for p in people:
        tl = sched[p['id']]['tl']
        if tl['kind'] == 'west':
            pre[p['id']] = np.array(after_enter(G, p, tl, upto_corner=True))
        else:
            full[p['id']] = np.array(after_enter(G, p, tl))
    out = {}
    walkers = sorted((pid for pid in pre), key=lambda pid: sched[pid]['tl']['tTurn'])
    DT, HOR = 0.01, 4.5
    clk = {}
    for pid in walkers:
        p, tl = P[pid], sched[pid]['tl']
        (ax, yg), seat = tl['corner'], (P[pid]['field']['X'], P[pid]['field']['Y'])
        BC = clk.setdefault(p['dadui'], BlockClock(tl.get('W', [])))
        tc = tl['tTurn']
        x0, x1, y0, y1 = seat[0] - 0.15, ax + 0.15, yg - 0.2, yg + 0.15
        obs = []
        for qid, arr in list(full.items()) + [(k, v) for k, v in pre.items() if k != pid]:
            if P[qid]['dadui'] != p['dadui']:
                continue
            m = (arr[:, 2] >= tc - 0.5) & (arr[:, 2] <= tc + HOR + 3.5)
            if not m.any():
                if arr[-1, 2] < tc:              # 已經坐好：坐著的人當成一直在那裡
                    m = np.zeros(len(arr), bool)
                    m[-1] = True
                else:
                    continue
            sub = arr[max(0, np.argmax(m) - 1):]
            if sub[:, 0].max() < x0 or sub[:, 0].min() > x1 or sub[:, 1].max() < y0 or sub[:, 1].min() > y1:
                continue                              # 這段軌跡的外框和橫越範圍不重疊（只看轉折點會漏掉直直穿過範圍的路線）
            obs.append(arr)
        bc = BC.b(tc)                                 # 在大隊的走路時鐘上排：停的時段大家一起停，相對位置不變
        T = np.arange(0.0, HOR + 3.5, DT) + bc
        OX = np.full((len(obs), len(T)), np.nan)
        OY = np.full((len(obs), len(T)), np.nan)
        for k, arr in enumerate(obs):
            bt = np.array([BC.b(v) for v in arr[:, 2]])
            keep = np.r_[np.diff(bt) > 1e-9, True]    # 停的那段（走路時鐘不動）只留最後一點
            bt, ax_, ay_ = bt[keep], arr[keep, 0], arr[keep, 1]
            ok = T >= bt[0]
            OX[k, ok] = np.interp(T[ok], bt, ax_)
            OY[k, ok] = np.interp(T[ok], bt, ay_)
        best = None
        for w0 in WEST_WAITS:
            k1 = int(round(w0 / DT))
            if obs and k1 > 0:
                d_stand = np.nanmin(np.hypot(OX[:, :k1 + 1] - ax, OY[:, :k1 + 1] - yg)) if np.isfinite(OX[:, :k1 + 1]).any() else 9.0
                if d_stand < WEST_SAFE:
                    break                             # 在轉角等下去會被後面的人撞到：不能再等更久
            pl, sc = march.west_plan_obs(ax, yg, seat[0], seat[1], OX, OY, DT, w0)
            if best is None or sc > best[2]:
                best = (pl, w0, sc)
            if sc >= WEST_SAFE:
                best = (pl, w0, sc)
                break
        if best[2] < WEST_SAFE:
            print(f'  {pid} 找不到 ≥ {WEST_SAFE} 的往西走法，最差 {best[2]:.3f}（等 {best[1]:.2f} 秒）', file=sys.stderr)
        out[pid] = (best[0], best[1])
        tl2 = dict(tl)
        full[pid] = np.array(after_enter(G, p, tl2, best[0], best[1]))
        del pre[pid]
    return out


def _line_pts(line, s0, s1):
    """線上 s0 → s1 的點（含中間的折點），附弧長。"""
    inner = [(q[0], q[1], c) for q, c in zip(line.p, line.cum) if s0 + 1e-9 < c < s1 - 1e-9]
    a, b = line.at(s0), line.at(s1)
    return [(a[0], a[1], s0)] + inner + [(b[0], b[1], s1)]


def _ids_between(persons, L, i0, i1):
    return [q['id'] for q in sorted((q for q in persons if q['lane'] == L and i0 <= q['laneIdx'] <= i1), key=lambda q: q['laneIdx'])]


def assemble(base, planj, G, R, sched, clocks, checks=None, slow=None):
    people = planj['people']
    persons = []
    for p in people:
        r, t = R[p['id']], sched[p['id']]
        path = person_path(G, p, r, t, clocks['ranks'], clocks['rankOf'][p['id']], (clocks.get('westPlan') or {}).get(p['id']))
        tt = dict(leave=round(t['leave'], 3), stair=round(t['stair'], 3), entry=round(t['entry'], 3), assembly=round(t['assembly'], 3), enter=round(t['enter'], 3),
                  gate=round(t['gate'], 3), split=round(t['split'], 3), arrive=path[-1][2])
        if 'holdStart' in t:                           # 迴廊候隊：在沿牆迴廊停的起訖
            tt['holdStart'], tt['holdEnd'] = round(t['holdStart'], 3), round(t['holdEnd'], 3)
        ws = _path_waits(path, tt)                     # 其他停：前面停後面也停、往西者在轉角等（起訖，從路徑讀出）
        if ws:
            tt['waits'] = ws
        if 'alignStart' in t:                          # 座位在第 10 排那條線以東：在切齊線上等同一排到齊的起訖
            tt['alignStart'], tt['alignEnd'] = round(t['alignStart'], 3), round(t['alignEnd'], 3)
        persons.append(dict(id=p['id'], lie=p['lie'], pai=p['pai'], dadui=p['dadui'], costume=p['costume'], a=p['a'],
                            field=p['field'], rest=p['rest'], exit=p['exit'], exitSeq=p['exitSeq'], lane=p['lane'],
                            laneIdx=p['laneIdx'], gateLane=p['gateLane'], gateIdx=p['gateIdx'], slot=p['slot'], rank=clocks['rankOf'][p['id']],
                            assembly='DOOR', t=tt, path=path))
    P = {p['id']: p for p in persons}
    t_end = max(p['t']['arrive'] for p in persons)
    t_gate0 = min(p['t']['gate'] for p in persons)
    # exits：每段 = 某一路連續從這個出口出來的一串人
    exits = []
    for key in plan.EXITS:
        e = dict(planj['exits'][key])
        e['key'] = key
        e['entryU'] = round(G.B1.proj(tuple(e['entry']))[0], 3)
        segs = []
        for L in plan.LANES:
            for s in planj['lanes'][L]['segments']:
                if s['exit'] != key:
                    continue
                ids = _ids_between(persons, L, s['fromIdx'], s['toIdx'])
                segs.append(dict(lane=L, n=len(ids), firstId=ids[0], lastId=ids[-1], fromRow=P[ids[0]]['rest']['pai'], toRow=P[ids[-1]]['rest']['pai'],
                                 tFirstLeave=P[ids[0]]['t']['leave'], tLastLeave=P[ids[-1]]['t']['leave'], **{'from': s['from'], 'to': s['to']}))
        segs.sort(key=lambda s: s['tFirstLeave'])
        e['segments'] = segs
        exits.append(e)
    # groups：18 個（大隊 1 白、大隊 1 藍、…）
    groups = []
    for g in planj['groups']:
        members = [p for p in persons if p['costume'] == g['costume'] and p['dadui'] == g['dadui']]
        stair_t = [p['t']['stair'] for p in members]
        groups.append(dict(g, tStairFirst=min(stair_t), tStairLast=max(stair_t),
                           tGateFirst=min(p['t']['gate'] for p in members), tGateLast=max(p['t']['gate'] for p in members),
                           tAssembly=max(p['t']['assembly'] for p in members), tLeave=min(p['t']['leave'] for p in members), tEnter=min(p['t']['enter'] for p in members),
                           tArrive=max(p['t']['arrive'] for p in members)))
    # files（54 列）
    files = []
    for lie in range(1, 55):
        ps = sorted((p for p in persons if p['lie'] == lie), key=lambda p: p['gateIdx'])
        ex = []
        for p in sorted(ps, key=lambda p: p['laneIdx']):
            if p['exit'] not in ex:
                ex.append(p['exit'])
        files.append(dict(lie=lie, dadui=ps[0]['dadui'], costume=ps[0]['costume'], n=len(ps), lane=ps[0]['lane'], exits=ex,
                          assembly='DOOR', order=[p['id'] for p in ps],
                          tLeave=min(p['t']['leave'] for p in ps), tAssembly=max(p['t']['assembly'] for p in ps),
                          tEnter=min(p['t']['enter'] for p in ps), tGate=min(p['t']['gate'] for p in ps), tArrive=max(p['t']['arrive'] for p in ps)))
    # nodes：沒有集結區
    nodes = {}
    for k, n in base['nodes'].items():
        if k[0] == 'P' and k[1:].isdigit():
            continue
        n = dict(n)
        if k in ('STAIR_TOP', 'STAIR_BOT'):                     # 樓梯直段的頂與底（L 形轉角）
            q = G.STAIR_PTS[0 if k == 'STAIR_TOP' else 1]
            n['X'], n['Y'] = round(q[0], 3), round(q[1], 3)
        if k == 'GATE6':
            n['label'] = routes.GATE_LABEL
        if k == 'GATE6_IN':
            n['label'] = '西一入口(場內)'
        nodes[k] = n
    who_seat = {(p['rest']['sec'], p['rest']['pai'], p['rest']['no']): p['id'] for p in persons}
    rest = [dict(s, kind=plan.seat_kind(s), reserved=plan.seat_reserved(s), who=who_seat.get((s['sec'], s['pai'], s['no']))) for s in base['restSeats']]
    meta = dict(title='入經藏 西一＋桃竹 休息區→進場 動線資料（版本 3 兩路直進）', built='2026-10-23',
                mPerUnit=base['meta']['mPerUnit'], frame=base['meta']['frame'], population=len(persons), tEnd=t_end,
                speedUnitPerSec=V, headway=HEADWAY, laneStagger=STAGGER, rankGap=RANK_GAP, queueSpeed=round(SLOW, 4), turnT=round(max(G.march.tau_gate), 3), t0=T0, daduiGap=DADUI_GAP,
                tStairStart=round(clocks['tStairStart'], 3), tGateStart=round(t_gate0, 3), stairDelay={str(d): v for d, v in sorted((clocks.get('stairDelay') or {}).items())},
                rules=RULES, assumptions=ASSUMPTIONS, checks=checks or {})
    t_go = min(p['t']['enter'] for p in persons)
    phases = [dict(key='seated', label='休息區就座', t0=0, t1=T0),
              dict(key='descend', label='大隊 1 白藍兩路離座、下樓梯，排滿門前隊伍', t0=T0, t1=t_go),
              dict(key='enter', label='每個大隊排滿門前隊伍後一排緊跟一排進門，在沿牆迴廊停好，等下一大隊排滿再北行、梯次進列；樓梯不停', t0=t_go, t1=t_end)]
    return dict(meta=meta, phases=phases, nodes=nodes, map=dict(base['map'], **G.stair_map(), gate=G.gate_map(), gateLanes=G.gate_lanes_map(_lanes_after_queue(G)), march=march.export(G.march, clocks['split'])), restSeats=rest, exits=exits,
                lanes=planj['lanes'], groups=groups, files=files, persons=persons, others=base['others'])


def _path_waits(path, tt):
    """路徑上 t.enter 之後站住的每一段（起、訖），扣掉迴廊候隊與切齊線上等對齊那兩段。"""
    known = []
    if 'holdStart' in tt:
        known.append((tt['holdStart'], tt['holdEnd']))
    if 'alignStart' in tt:
        known.append((tt['alignStart'], tt['alignEnd']))
    out = []
    for q0, q1 in zip(path, path[1:]):
        if q0[2] < tt['enter'] - 1e-9 or q0[:2] != q1[:2] or q1[2] - q0[2] < 0.0015:
            continue
        if any(abs(q0[2] - a) < 2e-3 and abs(q1[2] - b) < 2e-3 for a, b in known):
            continue
        if out and abs(out[-1][1] - q0[2]) < 1e-9:
            out[-1][1] = q1[2]
        else:
            out.append([q0[2], q1[2]])
    return out


def _lanes_after_queue(G):
    """圖面六條線在隊頭之後接著畫：整排平移線，到穿過西一入口之後 GATE_DRAW_AFTER 秒。"""
    M = march_of(G)
    return {j: [q[:2] for q in M.lane_track(j, M.s_at_tau(M.tau_gate[j] + GATE_DRAW_AFTER))[1:]] for j in range(6)}


RULES = [
    '兩路：A 路白衣靠看台側、B 路藍衣外側（B1 走廊、樓梯、B2 都一樣）；大隊 1→9 依序，兩路同時走',
    '每一路三列交錯排隊：每列排大的先，三列輪流各出一人（白衣列 6k−5→6k−4→6k−3，藍衣列 6k−2→6k−1→6k），排完的列跳過',
    '出口：白衣依序用 139 → 140 → 141 → 142，藍衣用 142 → 143 → 144 → 145；出口坐滿才換下一個，換口可以落在大隊中間',
    '142 兩路共用：藍衣大隊 1–3 先從上排出，白衣大隊 9 最後從下排出；任何時刻白衣用的出口都比藍衣近、且在不同階梯，所以走廊上不交叉',
    '每個出口是一條隊伍：由上排往下、每排由出口側往中央，先走的坐上面',
    '不進 B2 集結區、不在樓梯或 B1 走廊候隊：下樓後白衣散到北三條線、藍衣散到南三條線，在樓梯口到西一入口這段 B2 走廊（舞台後方）排成六條線的門前隊伍；每個大隊從新的一排開始，整個大隊排滿門前隊伍才出發，一排六人並肩、一排緊跟一排離開隊頭',
    '迴廊候隊：每個大隊進門後在沿全壘打牆內側的迴廊停好（隊頭停在北轉前，後面往回排），等下一個大隊在門前隊伍排滿，才繼續走、進列；下一個大隊緊跟在後進門，到迴廊停好；最後一個大隊不停',
    '整排轉彎：一排六人從隊頭到自己大隊的列區南緣全程並肩——左轉進西一入口、穿過門洞、右轉沿全壘打牆內側、左轉北行、沿第 5–10 排地標一條直線往北；轉彎時整排一起轉，內圈走小步、外圈走大步，轉過來仍是六人並肩；第 1 路（白衣列 6k−5）永遠在行進方向左側，北行時在西側（第 5 排地標旁）、進列時對到大隊第一列；不閃舞台、不上舞台階梯，六路都在地面',
    '走到自己那列再轉、第 10 排對齊：到了自己大隊列區南緣，每人沿自己那一路（兩欄之間的空隙）繼續往北，走到自己那一列才轉；座位在第 10 排以東的人往東走到第 10 排那條線停下，同一排這些人在線上對齊、都到了才一起起步往東到位，等的時候後面整個大隊（還沒走到自己那一列的人）跟著停，前面起步再一起走；座位在自己那一路與第 10 排之間的直接往東到位；座位在自己那一路西側的在那一列南邊半格的空隙往西、到座位正南方再往北半格進列（橫越還在往北走的人時，在空隙裡稍微偏移或放慢錯開）；北行時壓過的是後面大隊還空著的座位',
]
ASSUMPTIONS = [
    '1 單位 ≈ 7.6 m；步速 1.1 單位/秒；樓梯同一路相鄰兩人 0.2 秒（一個接一個緊跟）、兩路錯開 0.17 秒、大隊交界加 0.8 秒（之後的大隊再等門前隊伍有空位才下樓）；整個大隊緊密前進（每排間隔 0.2 秒），前面那一排在第 10 排那條線對齊時後面跟著停（每次約 1.2 秒）；門前隊伍前後間距 0.075 單位、排滿後 0.2 秒一排（排距約 1.7 m）；迴廊停好時排距約 1.3 m；皆為動畫節奏，不是現場秒數',
    '整排並肩的線距：門前隊伍、門洞與沿牆段 0.08 單位（牆和舞台南翼之間扣掉舞台淨距只剩約 0.45，放不下更寬的排），北轉時漸變為座位列距 0.13；轉彎內圈半徑至少 0.08、外圈走步速；只在西一入口門洞穿過全壘打牆；離舞台線稿至少 0.15 單位，不走上舞台階梯',
    '座位、看台幾何、走道口、西一入口與場內路徑沿用版本 1 的示意圖面；保留不坐：139 的 34 席給台東（第 1–10 排 1–3 號、第 11–12 排 4–5 號）、144 第 1–6 排 72 席',
    '樓梯照企劃圖 6白 的綠色 L 形：直段是樓梯（順著 B1 走廊往南直下），橫段是樓梯下的 B2 平台；西一入口 4 扇門、可 12 人並排；長度與寬度為示意',
    '碰撞檢查為圖面點距（0.03 單位），不是人體寬度或通道容量認證',
    '緩衝只有兩段：門前隊伍（一個大隊）與門後沿牆迴廊（一個大隊）；樓梯以上沒有候隊，任何一人延誤，後面整路跟著延誤；大隊有人沒到，門前隊伍與迴廊裡的前一大隊都等他',
]


def write_seats_csv(data, path):
    cols = ['位置編碼', '衣色', '大隊', '演繹列', '演繹位置', '休息區', '休息排', '座號', '出口', '出口帶隊序',
            '樓梯路', '樓梯序號', '欄內順序', '集結區', '西一入口路', '西一入口序號']
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(cols)
        for p in sorted(data['persons'], key=lambda p: (p['lie'], p['pai'])):
            w.writerow([p['id'], p['costume'], p['dadui'], p['lie'], p['pai'], p['rest']['sec'], p['rest']['pai'], p['rest']['no'],
                        p['exit'], p['exitSeq'] + 1, p['lane'], p['laneIdx'] + 1, p['slot'] + 1, DIRECT_LABEL,
                        p['gateLane'] + 1, p['gateIdx'] + 1])


def avoid(base, planj, G, R, sched, clocks):
    """碰撞避讓：整排並肩的部分（t.enter → t.split）所有排共用同一個速度剖面，不平移、不拆排；
    還有碰撞（都發生在分出後各人進列的那一段）時，把排號較晚的那一位（同一排取 lane 較大的）橫走那一段放慢 SLOW_STEP，
    最低 SLOW_MIN 倍步速，重算到沒有碰撞為止。不動任何人的 t.enter 以前，也不動排與排的時間。
    回傳最後的 sched、clocks、組好的 data、碰撞結果（main 直接沿用）與放慢的名單。"""
    from collide import collisions, seated_hits
    slow = {}
    for rnd in range(AVOID_ROUNDS + 1):
        data = assemble(base, planj, G, R, sched, clocks, slow=slow)
        st, wk = collisions(data['persons'], data['meta']['tEnd'])
        sh = seated_hits(data['persons'], data['meta']['tEnd'])
        print('  避撞第', rnd, '輪：穿過站定者', len(st), '互撞', len(wk), '穿過已坐好的人', len(sh), file=sys.stderr)
        if (not st and not wk and not sh) or rnd == AVOID_ROUNDS:
            break
        P = {p['id']: p for p in data['persons']}
        pick = set()
        for pair in list(wk) + [(k, v[1]) for k, v in st.items()] + [(k, v[1]) for k, v in sh.items()]:
            cand = [i for i in pair if i in P and _lateral(P[i])]           # 只有要橫走的人能放慢
            if cand:
                pick.add(max(cand, key=lambda i: (P[i]['rank'], P[i]['gateLane'])))
        moved = False
        for pid in pick:
            cur = slow.get(pid) or 1.0
            if cur - SLOW_STEP >= SLOW_MIN - 1e-9:
                slow[pid] = round(cur - SLOW_STEP, 3)
                moved = True
        if not moved:
            break
    return sched, clocks, data, (st, wk, sh), slow


def _lateral(p):
    """分出後有沒有往西橫走的一段（沿列間空隙）。"""
    a = [q for q in p['path'] if q[2] >= p['t']['split'] - 1e-6]
    return any(abs(q1[1] - q0[1]) < 1e-6 and q0[0] - q1[0] > 0.07 for q0, q1 in zip(a, a[1:]))


def main(argv):
    args = [a for a in argv if not a.startswith('--')]
    no_avoid = '--no-avoid' in argv
    if len(args) != 4:
        raise SystemExit(__doc__)
    base_path, plan_path, out_path, csv_path = args
    base = json.load(open(base_path, encoding='utf-8'))
    planj = json.load(open(plan_path, encoding='utf-8'))
    G = routes.Geometry(base)
    people = planj['people']
    R = prepare(G, people)
    sched, clocks = schedule(G, people, R)
    if no_avoid:
        data = assemble(base, planj, G, R, sched, clocks)
    else:
        import check
        sched, clocks, data, coll, slow = avoid(base, planj, G, R, sched, clocks)
        data['meta']['checks'] = check.check_all(data, coll)          # 碰撞已在 avoid 最後一輪算過；check.py CLI 會再獨立重算
    json.dump(data, open(out_path, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    write_seats_csv(data, csv_path)
    print('全長', data['meta']['tEnd'], '秒；樓梯時鐘起點', data['meta']['tStairStart'], '；第一位過西一入口', data['meta']['tGateStart'],
          '；檢核', '通過' if data['meta']['checks'].get('ok') else ('未跑' if no_avoid else '未通過'))


if __name__ == '__main__':
    main(sys.argv[1:])
