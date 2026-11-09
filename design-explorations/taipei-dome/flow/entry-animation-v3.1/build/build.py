"""版本 3.1 排程：樓梯口時鐘與版本 3 相同（兩路、大隊交界對齊、拉式倒推離座時刻），輸出 data.json 與 seats.csv。
下樓後白衣一路、藍衣一路沿 B2 通行帶走到自己那一排後方、轉 180°、散成六路，走到自己大隊的集合位置站定（中途不停、不等）；
每個大隊全員站定後依大隊 1→9 放行：集合位置隊頭一排六人並肩、一排緊跟一排，後面的排往前補；
沿 B2 往西一入口、右轉進門，之後與版本 3 相同（整排轉彎、北行、分出、梯次進列）。版本 3 的「迴廊候隊」拿掉（見 README）。

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
from geo import Poly, pairs

V = 1.1                 # 單位/秒
HEADWAY = 0.2           # 樓梯／走廊同一路相鄰兩人（一個接一個緊跟；下樓分成三條線後每條線約 0.6 秒一位）
STAGGER = 0.17          # 兩路錯開
T0 = 6.73               # 第一人離座
DADUI_GAP = 0.8         # 大隊交界的對齊空檔：前一大隊隊尾先過西一入口線的轉入點
SLOW_STEP, SLOW_MIN, AVOID_ROUNDS = 0.05, 0.7, 30   # 避撞：進列時橫走那一段每次放慢 0.05 倍步速，最低 0.7 倍
RANK_GAP = 0.2          # 放行時一排緊跟一排離開集合位置隊頭（0.2 秒 × 1.1 = 0.22 單位 ≈ 1.7 m）；0.13 秒會和「橫走一欄 0.12 秒」同步而在欄間空隙相撞
SLOW = routes.STAGE_STEP / RANK_GAP   # 集合位置裡往前補一格的速度（單位/秒）：前後間距 STAGE_STEP、每 RANK_GAP 秒補一格
FILL_PAUSE = 1.0        # 大隊全員在集合位置站定後，稍停這麼久才放行
GATE_DRAW_AFTER = 1.0   # 圖面六條線畫到穿過西一入口之後這麼久（秒）
WAIT_MIN = 0.01         # 路徑上同一點停不到這麼久就不留停留點
ALIGN_GAP = 0.07        # 第 9 排對齊時停住的人前後最少相距（沿路線，約 0.53 m）。大隊 9 第 6 路（列 54）第 10 排以東只有 9 人、隊頭要等約 1.16 秒，
                        # 間距要 < 0.078 才不會排到第 9 排的那一位（0.08 會擋到 54-9 約 0.02 秒）
LANE_K = {'A': 0, 'B': 1}
ASSUME_NO_PILLARS = {'L7', 'L8'}   # 11/9 企劃：先假設集合區裡沒有這兩根柱（版本 1 圖面的場邊柱，落在大隊 7、8 的集合位置）。圖面不畫；
                                   # 另存在 map.pillarsAssumedAbsent，check.py 照樣算「若有這兩根柱會碰到多少人」，標成假設、不算衝突
STAGE_LABEL = 'B2 集合區'


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
        G.march = march.March(G, G.D, routes.STAGE_START_U)
    return G.march


def split_points(G, people):
    """每個大隊在哪裡分出（中心線弧長 s）：北行直線上，整排走到該大隊最南一列之南 SPLIT_AHEAD 處。"""
    M = march_of(G)
    out = {}
    for d in sorted({p['dadui'] for p in people}):
        ps = [p for p in people if p['dadui'] == d]
        out[d] = M.split_s(max(p['field']['Y'] for p in ps))
    return out


def stage_layout(G, people):
    """各大隊的集合位置（放行中心線上的 s）：大隊 1 隊頭在 STAGE_HEAD_U、大隊 9 最深；第 d 大隊第 r 排站在 sHead(d) − STAGE_STEP·(r − r0)。
    相鄰兩大隊之間的空檔 = 把九個大隊均勻排滿 STAGE_HEAD_U → STAGE_TAIL_U 剩下的長度（至少 STAGE_GAP_MIN）。"""
    M = march_of(G)
    rank_of = rank_numbers(people)
    daduis = sorted({p['dadui'] for p in people})
    r0 = {d: min(rank_of[p['id']] for p in people if p['dadui'] == d) for d in daduis}
    r1 = {d: max(rank_of[p['id']] for p in people if p['dadui'] == d) for d in daduis}
    s_h1, s_end = M.s_of_u(routes.STAGE_HEAD_U), M.s_of_u(routes.STAGE_TAIL_U)
    body = sum((r1[d] - r0[d]) * routes.STAGE_STEP for d in daduis)
    gap = (s_h1 - s_end - body) / (len(daduis) - 1)
    if gap < routes.STAGE_GAP_MIN:
        raise SystemExit(f'集合區放不下九個大隊：大隊間空檔只剩 {gap:.3f}（< {routes.STAGE_GAP_MIN}）')
    head, tail, s = {}, {}, s_h1
    for d in daduis:
        head[d], tail[d] = s, s - (r1[d] - r0[d]) * routes.STAGE_STEP
        s = tail[d] - gap
    return dict(rankOf=rank_of, r0=r0, r1=r1, head=head, tail=tail, gap=gap)


def slot_s(lay, p):
    d = p['dadui']
    return lay['head'][d] - routes.STAGE_STEP * (lay['rankOf'][p['id']] - lay['r0'][d])


def turn_point(G, s_slot):
    """迴轉點（11/9）：散完六路的位置在自己那一排再深一排（s_fan），迴轉圓心再往深處 FAN_LEN（u_c）；超過 UTURN_U 就是集合區放不下迴轉，停止建置。"""
    M = march_of(G)
    s_fan = max(0.0, s_slot - routes.TURN_BACK)
    u_c = G.B2.proj(M.C.at(s_fan)[:2])[0] + routes.FAN_LEN
    if u_c > routes.UTURN_U + 1e-9:
        raise SystemExit(f'迴轉點 u {u_c:.3f} 超過 UTURN_U {routes.UTURN_U}：集合區最深處放不下迴轉')
    return s_fan, u_c


def prepare(G, people, lay=None):
    """每人的路線與距離（不含時間）：to 從座位到集合位置；d_top 到樓梯口、L_entry 到六路起點（s = 0）、L_to 到集合位置。"""
    M = march_of(G)
    lay = lay or stage_layout(G, people)
    R = {}
    for p in people:
        j = p['gateLane']
        s_slot = slot_s(lay, p)
        s_fan, u_c = turn_point(G, s_slot)
        pre = G.entry_route(p, u_c)
        lane = [q[:2] for q in M.lane_pts(j, s_fan, s_slot)]
        to = pre + lane
        c = cum(to)
        R[p['id']] = dict(to=to, L_to=c[-1], d_top=c[G.stair_top_index(to)], L_entry=c[len(pre)])
    return R


def aligned_clock(items, key_lane, key_seq, key_group, stagger_of, group_gap=0.0):
    """連續時鐘，各路在「群」（大隊）交界對齊：群 g 在所有路同時起拍 = 各路上一群最後一拍（含錯開）的最大值 + HEADWAY + group_gap。
    回傳相對時刻（第一群第一拍 = 0）與各群起拍時刻。"""
    lanes = sorted({it[key_lane] for it in items})
    groups = sorted({it[key_group] for it in items})
    by = collections.defaultdict(list)
    for it in items:
        by[(it[key_group], it[key_lane])].append(it)
    rel, t_group, prev_end = {}, {}, None
    for g in groups:
        t0 = 0.0 if prev_end is None else prev_end + HEADWAY + group_gap
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


def rank_numbers(people):
    """排號：每個大隊從新的一排開始，大隊內第 slot 位就在第 slot 排；大隊人數少的那幾條線，大隊尾巴的幾排是空位。"""
    n = collections.Counter((p['dadui'], p['gateLane']) for p in people)
    start, off = {}, 0
    for d in sorted({p['dadui'] for p in people}):
        start[d] = off
        off += max(c for (dd, _), c in n.items() if dd == d)
    return {p['id']: start[p['dadui']] + p['slot'] for p in people}


def schedule(G, people, R=None, lay=None):
    """1. 樓梯口時刻 S（兩路、大隊交界對齊，同版本 3）；離座 = S − 到樓梯口的路程 / V；之後以步速經通行帶、在自己那一排後方迴轉、散成六路，
       走到自己的集合位置（t.entry = 到六路起點、t.assembly = 站定）。中途不停：集合位置在自己到之前一定空著（先到的站前面）。
    2. 放行：九個大隊全部站定後 FILL_PAUSE 秒，依大隊 1→9 放行（11/9 改；原本是各大隊站齊就放），第一排離開隊頭（t.enter），之後一排緊跟一排（RANK_GAP），後面的排以 SLOW 往前補。
       不同大隊的隊頭在不同位置：以「經過大隊 1 隊頭（sHead(1)）的時刻」G 排序，下一個大隊第一排的 G 至少比上一個大隊最後一排晚 RANK_GAP。
    3. 隊頭之後整排沿中心線（右轉進西一入口 → 版本 3 的沿牆、北行）；t.gate = 穿過全壘打牆、t.split = 分出。沒有迴廊候隊。"""
    lay = lay or stage_layout(G, people)
    R = R or prepare(G, people, lay)
    M = march_of(G)
    rel, _ = aligned_clock(people, 'lane', 'dadIdx', 'dadui', lambda it: STAGGER * LANE_K[it['lane']], group_gap=DADUI_GAP)
    T_S0 = max(T0 + R[p['id']]['d_top'] / V - rel[p['id']] for p in people)
    stair = {p['id']: T_S0 + rel[p['id']] for p in people}
    leave = {pid: stair[pid] - R[pid]['d_top'] / V for pid in stair}
    entry = {pid: leave[pid] + R[pid]['L_entry'] / V for pid in stair}
    assembly = {pid: leave[pid] + R[pid]['L_to'] / V for pid in stair}
    rank_of = lay['rankOf']
    tau_h = {d: M.tau_at_s(s) for d, s in lay['head'].items()}
    tau_ref = tau_h[min(tau_h)]
    ranks = {}                                        # 排號 → 離開自己集合位置隊頭的時刻（t.enter）
    g_prev = None
    fill_all = max(assembly.values())                 # 11/9：九個大隊全部在集合位置站定，才從大隊 1 開始放行
    for d in sorted(lay['head']):
        shift = tau_ref - tau_h[d]                    # 隊頭 → 大隊 1 隊頭的時間
        g = fill_all + FILL_PAUSE + shift
        if g_prev is not None:
            g = max(g, g_prev + RANK_GAP)
        for r in range(lay['r0'][d], lay['r1'][d] + 1):
            ranks[r] = g - shift
            g_prev = g
            g += RANK_GAP
    split = split_points(G, people)
    out = {}
    for p in people:
        pid, d, j = p['id'], p['dadui'], p['gateLane']
        e = ranks[rank_of[pid]]
        out[pid] = dict(leave=leave[pid], stair=stair[pid], entry=entry[pid], assembly=assembly[pid], enter=e,
                        go=ranks[lay['r0'][d]], gate=e + M.tau_gate[j] - tau_h[d], split=e + M.tau_at_s(split[d]) - tau_h[d])
    return out, dict(tStairStart=T_S0, tGateStart=min(v['gate'] for v in out.values()), ranks=ranks, rankOf=rank_of, split=split, lay=lay, tauHead=tau_h)


def person_path(G, p, r, t, lay, s_split, f_lat=None):
    """名目路徑（未四捨五入；第 9 排對齊停住由 align_holds / apply_hold 另外套上，finish_path 收尾）：座位 → … → 樓梯 → 通行帶 → 自己那一排後方迴轉 → 散成六路 → 自己那一路 → 集合位置（全程步速）→ 站住
    → 放行後沿自己那一路以 SLOW 往前補到隊頭（第一排不用補）→ 一排六人並肩沿 march 中心線（右轉進西一入口、沿牆、北轉、沿第 4–9 排地標直線北行）
    → 在自己大隊列區南緣分出 → 沿自己那一路走到自己那一列 → 座位（步速；第 10 排起的經過第 9 排對齊點）。"""
    M = march_of(G)
    j, d = p['gateLane'], p['dadui']
    path = list(timed(r['to'], t['leave']))
    s_slot, s_head = slot_s(lay, p), lay['head'][d]
    if s_head - s_slot > 1e-9:                         # 往前補：大隊第一排離開（t.go）時起步、自己離開隊頭（t.enter）時到隊頭，等速
        q = path[-1]
        if t['go'] - q[2] >= WAIT_MIN:
            path.append((q[0], q[1], t['go']))
        lp = M.lane_pts(j, s_slot, s_head)
        for x, y, s in lp[1:]:
            path.append((x, y, t['go'] + (t['enter'] - t['go']) * (s - s_slot) / (s_head - s_slot)))
    else:
        q = path[-1]
        if t['enter'] - q[2] >= WAIT_MIN:
            path.append((q[0], q[1], t['enter']))
    tau0 = M.tau_at_s(s_head)
    path += [(x, y, t['enter'] + tau - tau0) for x, y, tau in M.lane_track(j, s_split, s_start=s_head)[1:]]
    _, _, tx, ty, _ = M.C.at(s_split)
    tt, last = path[-1][2], path[-1]
    for q in M.tail(last[:2], (tx, ty), (p['field']['X'], p['field']['Y']), f_lat):
        tt += math.dist(last[:2], q[:2]) / (V * (q[2] if len(q) > 2 else 1.0))
        path.append((q[0], q[1], tt))
        last = path[-1]
    return path


def _at_time(path, t):
    """名目路徑在 t 時刻的位置。"""
    k = max(0, min(len(path) - 2, bisect.bisect_right([q[2] for q in path], t) - 1))
    q0, q1 = path[k], path[k + 1]
    f = max(0.0, min(1.0, (t - q0[2]) / (q1[2] - q0[2]))) if q1[2] > q0[2] else 0.0
    return (q0[0] + (q1[0] - q0[0]) * f, q0[1] + (q1[1] - q0[1]) * f)


def _lerp(xs, ys, x):
    """xs 遞增；x 對應的 ys（線性內插，超出兩端取端點）。"""
    k = max(0, min(len(xs) - 2, bisect.bisect_right(xs, x) - 1))
    f = max(0.0, min(1.0, (x - xs[k]) / (xs[k + 1] - xs[k]))) if xs[k + 1] > xs[k] else 0.0
    return ys[k] + (ys[k + 1] - ys[k]) * f


ALIGN_DT = 0.01        # 第 9 排對齊的排隊模擬時間步（秒）


class _Walker:
    """一個人放行（t.enter）之後的名目路徑，與在自己那一路的共用座標 λ（沿自己那條平移線量；分出後接著沿自己的路線量）。
    u = 名目時間（相對 t.enter）；模擬中 u 只會以 ≤ 步速前進或停住。"""

    def __init__(self, p, post, e, lam):
        self.p, self.id, self.e, self.post = p, p['id'], e, post
        self.U = [q[2] - e for q in post]
        self.L = lam
        self.u = 0.0
        self.knots = []                                  # 受限的那幾步：(t, u)
        self.stop = p['field']['X'] > march.ALIGN_X + 1e-9    # 第 10 排以東：要在第 9 排對齊
        self.lam_line = None
        self.turn = self.end = None

    def lam(self, u):
        return _lerp(self.U, self.L, u)

    def u_at(self, lam):
        return _lerp(self.L, self.U, lam)


def _lane_lambda(M, j):
    """lane j 平移線的弧長 λ_j(s)（取樣點 M.ss）。"""
    out, prev = [0.0], M.lane_xy(M.ss[0], j)
    for s in M.ss[1:]:
        q = M.lane_xy(s, j)
        out.append(out[-1] + math.dist(prev, q))
        prev = q
    return out


def align_sim(G, people, paths, sched, tau_h):
    """第 9 排對齊（11/9 第二版）：每個大隊第 10 排以東的人，每一排（六列各一位、同一個 slot）都在第 9 排東側空隙（march.ALIGN_X）
    對齊：六人都走到那條線才一起過線，之後並排往東（同一速度剖面），各自走到自己的座位停；下一排至少晚 RANK_GAP 過線。
    第 1 列（最西、最北）的路最長，所以第 2–6 列每一排都在線前等它；等的人在自己那一路排隊（前後 ≥ ALIGN_GAP，沿路線），
    後面的人走到隊尾就停、前面走了就往前補（走走停停，不快過步速）。第 9 排與以內的人不對齊，被前面的隊伍擋到就在後面等，路通了直接到位。
    以 ALIGN_DT 時間步模擬全部六路（跨大隊：同一路前一個大隊的人在共用的平移線上也算）。放行照舊（下一大隊緊跟），
    所以第 2–6 列等的時間會往後傳到下一個大隊，回堵到西一入口之前（B2 走廊、門洞）也照樣走走停停（11/9 企劃同意）；
    t.gate、t.split 改成實際走到那一點的時刻。前後間距最多壓到名目間距：轉彎內圈的名目間距本來就小於 ALIGN_GAP。
    回傳 新路徑 {id: 未四捨五入的 (x, y, t)}、受限時段 {id: (第一次受限, 最後一次受限結束)}、各大隊各排過線時刻 {大隊: [T0, T1, …]}
    （第 10 排以東的人過線時刻就是自己那一排的 T：一排的人都停在線上，放行的那一刻一起過）。"""
    M = march_of(G)
    lamj = {j: _lane_lambda(M, j) for j in range(6)}
    W = {}
    for p in people:
        pid, t = p['id'], sched[p['id']]
        e, j, path = t['enter'], p['gateLane'], paths[pid]
        k0 = next(i for i, q in enumerate(path) if q[2] >= e - 1e-9)
        post = path[k0:]
        lam, prev = [], None
        for q in post:
            if q[2] <= t['split'] + 1e-9:
                lam.append(_lerp(M.ss, lamj[j], M.s_at_tau(q[2] - e + tau_h[p['dadui']])))
            else:
                lam.append(lam[-1] + math.dist(prev[:2], q[:2]))
            prev = q
        w = W[pid] = _Walker(p, post, e, lam)
        ks = next(i for i, q in enumerate(post) if q[2] >= t['split'] - 1e-9)
        x0 = post[ks][0]
        kt = next((i - 1 for i in range(ks + 1, len(post)) if abs(post[i][0] - x0) > 1e-6), len(post) - 1)
        w.turn, w.end = lam[kt], lam[-1]                  # 離開自己那條平移線（轉進列）的 λ、終點的 λ
        w.east = p['field']['X'] > x0                     # 座位在自己那一路東側（右轉沿列往東）
        if w.stop:
            fy = p['field']['Y']
            ka = next(i for i in range(ks, len(post)) if abs(post[i][0] - march.ALIGN_X) < 1e-6 and abs(post[i][1] - fy) < 1e-6)
            w.lam_line = lam[ka]
    rank_of = collections.defaultdict(list)                # (大隊, slot) → 這一排第 10 排以東的人
    for w in W.values():
        if w.stop:
            rank_of[(w.p['dadui'], w.p['slot'])].append(w)
    released, T = set(), collections.defaultdict(dict)

    def shared(m, k):
        """m（同一路前面的人）與 k 共用路線到哪個 λ：同一大隊、都往東進列（同一列）時共用到 k 的終點（k 的座位在 m 的路上；
        座位緊鄰自己那一路的人轉彎半徑較小，λ 差不到 0.01，當成同一條），否則共用到先轉進列的那一位轉彎處。"""
        if m.p['dadui'] == k.p['dadui'] and m.east and k.east:
            return min(m.end, k.end)
        return min(m.turn, k.turn)

    t = min(w.e for w in W.values())
    t_stop = max(w.e + w.U[-1] for w in W.values()) + 60.0
    active = {j: [] for j in range(6)}                     # 每一路已放行、還沒到位的人，依同一路的前後順序（gateIdx）
    pending = sorted(W.values(), key=lambda w: w.e)        # 依放行時刻啟動：後面的大隊從集合區更深處出發，可能比前一大隊最後幾位早放行
    nxt = 0
    while t < t_stop:
        for key, ws in rank_of.items():                      # 這一排的人都在線上，而且上一排已經過線 RANK_GAP 以上：一起過線
            if key in released:
                continue
            d, k = key
            if all(w.lam(w.u) >= w.lam_line - 1e-7 for w in ws) and (k == 0 or (k - 1 in T[d] and t >= T[d][k - 1] + RANK_GAP - 1e-9)):
                released.add(key)
                T[d][k] = t
        while nxt < len(pending) and pending[nxt].e < t + ALIGN_DT:
            w = pending[nxt]
            a = active[w.p['gateLane']]
            a.insert(bisect.bisect([m.p['gateIdx'] for m in a], w.p['gateIdx']), w)
            nxt += 1
        done = nxt == len(pending)
        for j in range(6):
            for i, w in enumerate(active[j]):
                if w.u >= w.U[-1]:
                    continue
                done = False
                want = min(w.U[-1], w.u + ALIGN_DT if t >= w.e else t + ALIGN_DT - w.e)
                lim = w.lam(want)
                if w.stop and (w.p['dadui'], w.p['slot']) not in released:
                    lim = min(lim, w.lam_line)
                for m in reversed(active[j][:i]):
                    lm = m.lam(m.u)
                    se = shared(m, w)
                    if lm < se + ALIGN_GAP:                     # 離前一位至少 ALIGN_GAP，但不要求比名目間距（落後 RANK_GAP 秒）還遠：轉彎內圈名目間距本來就小於 ALIGN_GAP
                        lim = min(lim, max(lm - ALIGN_GAP, w.lam(w.u_at(lm) - RANK_GAP + 1e-6)))
                    if lm > w.lam(w.u) + 3.0:
                        break
                cur = w.lam(w.u)
                u_new = want if w.lam(want) <= lim + 1e-12 else max(w.u, w.u_at(max(lim, cur)))
                if u_new < want - 1e-9:                      # 這一步受限：記下起訖（之後合併斜率相同的段）
                    if not w.knots or abs(w.knots[-1][0] - t) > 1e-9:
                        w.knots.append((t, w.u))
                    w.knots.append((t + ALIGN_DT, u_new))
                w.u = u_new
            active[j] = [w for w in active[j] if w.u < w.U[-1]]
        if done:
            break
        t = round(t + ALIGN_DT, 9)
    if len(released) != len(rank_of):
        raise SystemExit('第 9 排對齊模擬沒有讓每一排都過線（排程卡住）')
    out, win, split, gate = {}, {}, {}, {}
    t_of_u = lambda kn, u: next(t0 + (u - u0) * (t1 - t0) / (u1 - u0) for (t0, u0), (t1, u1) in zip(kn, kn[1:]) if u1 > u0 and u0 - 1e-12 <= u <= u1 + 1e-12)
    for w in W.values():
        pid, path = w.id, paths[w.id]
        k0 = next(i for i, q in enumerate(path) if q[2] >= w.e - 1e-9)
        knots = [(w.e, 0.0)] + w.knots
        if knots[-1][1] < w.U[-1]:
            knots.append((knots[-1][0] + w.U[-1] - knots[-1][1], w.U[-1]))
        kn = [knots[0]]                                       # 合併斜率相同的相鄰段
        for q in knots[1:]:
            if q[0] - kn[-1][0] < 1e-12:
                continue
            if len(kn) >= 2:
                s0 = (kn[-1][1] - kn[-2][1]) / (kn[-1][0] - kn[-2][0])
                s1 = (q[1] - kn[-1][1]) / (q[0] - kn[-1][0])
                if abs(s0 - s1) < 1e-9:
                    kn[-1] = q
                    continue
            kn.append(q)
        pts = list(path[:k0])
        xy = lambda u: _at_time([(q[0], q[1], uu) for q, uu in zip(w.post, w.U)], u)
        pts.append((*xy(0.0), w.e))
        for (t0, u0), (t1, u1) in zip(kn, kn[1:]):
            if u1 > u0:
                for q, uu in zip(w.post, w.U):
                    if u0 + 1e-12 < uu < u1 - 1e-12:
                        pts.append((q[0], q[1], t0 + (uu - u0) * (t1 - t0) / (u1 - u0)))
            pts.append((*xy(u1), t1))
        out[pid] = pts
        split[pid] = t_of_u(kn, sched[pid]['split'] - w.e)   # 分出、過西一入口：走到名目那一點的時刻（11/9：前面的隊伍回堵時，進門前也可能走走停停）
        gate[pid] = t_of_u(kn, sched[pid]['gate'] - w.e)
        if w.knots:
            win[pid] = (w.knots[0][0], w.knots[-1][0])
    return out, win, split, gate, {d: [T[d][k] for k in sorted(T[d])] for d in sorted(T)}


def finish_path(path):
    """四捨五入到 0.001、去掉停不到 WAIT_MIN 的停留點、時間嚴格遞增。"""
    rounded = [[round(x, 3), round(y, 3), round(z, 3)] for x, y, z in path]
    clean = [rounded[0]]
    for q in rounded[1:]:
        if q[:2] == clean[-1][:2] and q[2] - clean[-1][2] < WAIT_MIN:
            continue
        if q[2] <= clean[-1][2] and q[:2] != clean[-1][:2]:
            q = [q[0], q[1], round(clean[-1][2] + 0.001, 3)]
        clean.append(q)
    return clean


def _ids_between(persons, L, i0, i1):
    return [q['id'] for q in sorted((q for q in persons if q['lane'] == L and i0 <= q['laneIdx'] <= i1), key=lambda q: q['laneIdx'])]


def assemble(base, planj, G, R, sched, clocks, checks=None, slow=None):
    people = planj['people']
    persons = []
    raw = {p['id']: person_path(G, p, R[p['id']], sched[p['id']], clocks['lay'], clocks['split'][p['dadui']], (slow or {}).get(p['id'])) for p in people}
    paths, win, split_t, gate_t, ranks_t = align_sim(G, people, raw, sched, clocks['tauHead'])
    for p in people:
        t, hold = sched[p['id']], win.get(p['id'])
        path = finish_path(paths[p['id']])
        split = split_t[p['id']]
        tt = dict(leave=round(t['leave'], 3), stair=round(t['stair'], 3), entry=round(t['entry'], 3), assembly=round(t['assembly'], 3), go=round(t['go'], 3),
                  enter=round(t['enter'], 3), gate=round(gate_t[p['id']], 3), split=round(split, 3), arrive=path[-1][2])
        if hold:
            tt.update(holdStart=round(hold[0], 3), holdEnd=round(hold[1], 3))
        persons.append(dict(id=p['id'], lie=p['lie'], pai=p['pai'], dadui=p['dadui'], costume=p['costume'], a=p['a'],
                            field=p['field'], rest=p['rest'], exit=p['exit'], exitSeq=p['exitSeq'], lane=p['lane'],
                            laneIdx=p['laneIdx'], gateLane=p['gateLane'], gateIdx=p['gateIdx'], slot=p['slot'], rank=clocks['rankOf'][p['id']],
                            assembly='STAGE', stageRank=clocks['rankOf'][p['id']] - clocks['lay']['r0'][p['dadui']], t=tt, path=path))
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
                          assembly='STAGE', order=[p['id'] for p in ps],
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
    meta = dict(title='入經藏 西一＋桃竹 休息區→進場 動線資料（版本 3.1 B2 集合區）', built='2026-11-08',
                mPerUnit=base['meta']['mPerUnit'], frame=base['meta']['frame'], population=len(persons), tEnd=t_end,
                speedUnitPerSec=V, headway=HEADWAY, laneStagger=STAGGER, rankGap=RANK_GAP, queueSpeed=round(SLOW, 4), turnT=round(max(G.march.tau_gate), 3), t0=T0, daduiGap=DADUI_GAP,
                tStairStart=round(clocks['tStairStart'], 3), tGateStart=round(t_gate0, 3),
                rules=RULES, assumptions=ASSUMPTIONS, checks=checks or {})
    t_go = min(p['t']['enter'] for p in persons)
    phases = [dict(key='seated', label='休息區就座', t0=0, t1=T0),
              dict(key='descend', label='大隊 1 白藍兩路離座、下樓梯，經 B2 通行帶走到自己那一排後方迴轉、散成六路，到集合位置整隊', t0=T0, t1=t_go),
              dict(key='enter', label='依大隊 1→9 放行：集合位置隊頭一排六人並肩、一排緊跟一排，沿 B2 往西一入口、右轉進門、北行、梯次進列；後面的大隊照樣下樓、到自己的集合位置整隊', t0=t_go, t1=t_end)]
    st = staging_map(G, clocks)
    pillars = [c for c in base['map']['pillars'] if c['id'] not in ASSUME_NO_PILLARS]
    absent = [c for c in base['map']['pillars'] if c['id'] in ASSUME_NO_PILLARS]
    m = dict(base['map'], pillars=pillars, pillarsAssumedAbsent=absent, **G.stair_map(), gate=G.gate_map(), gateLanes=st.pop('lanes'), staging=st,
             march=march.export(G.march, clocks['split'], {d: clocks['tauHead'][d] for d in clocks['lay']['head']}),
             align=dict(pai=march.ALIGN_PAI, x=round(march.ALIGN_X, 4), gap=ALIGN_GAP, release={str(d): round(v[0], 3) for d, v in ranks_t.items()},
                        ranks={str(d): [round(x, 3) for x in v] for d, v in ranks_t.items()},
                        heads={str(d): sorted(p['id'] for p in people if p['dadui'] == d and p['slot'] == 0) for d in ranks_t}))
    return dict(meta=meta, phases=phases, nodes=nodes, map=m, restSeats=rest, exits=exits,
                lanes=planj['lanes'], groups=groups, files=files, persons=persons, others=base['others'])


def staging_map(G, clocks):
    """圖面：集合區（六路帶）、通行帶（假設，帶外）、九個大隊的集合位置（隊頭、隊尾、六路各自的頭尾點、標籤點）、
    兩路的走法（平台 → 通行帶 → 迴轉）與六路（散開 → 集合區 → 西一入口之後 GATE_DRAW_AFTER 秒）。"""
    M = march_of(G)
    lay = clocks['lay']
    flat = lambda pts: [round(v, 3) for q in pts for v in q[:2]]
    s_h1 = lay['head'][min(lay['head'])]
    B2d = Poly(pairs(G.stair_map()['b2Corridor']))            # data.json 的 b2Corridor 是截過的（從樓梯平台那一排開始）：u 一律用它量
    du = G.B2.proj(B2d.p[0])[0]
    ud = lambda u: round(u - du, 3)
    blocks = []
    for d in sorted(lay['head']):
        sh, st = lay['head'][d], lay['tail'][d]
        uh, ut = (round(B2d.proj(M.C.at(s)[:2])[0], 3) for s in (sh, st))
        blocks.append(dict(dadui=d, uHead=uh, uTail=ut, ranks=lay['r1'][d] - lay['r0'][d] + 1,
                           heads=[flat([M.lane_xy(sh, j)]) for j in range(6)],
                           poly=flat(G.stage_band(ut + du + 0.02, uh + du - 0.02, -0.25, 0.25, 0.15)),
                           center=flat([G.B2.off((uh + ut) / 2 + du, 0)]),            # 集合位置中心（標籤的錨點）
                           label=flat([G.B2.off((uh + ut) / 2 + du, 0.42)])))         # 場側一點：標籤往這個方向推開
    # 11/9：每人在自己那一排附近迴轉。圖面的兩路畫到最深的迴轉點（最深那個大隊的最後一排）；uturn 是大隊 1 第一排的迴轉圓心（3D 章節取景用）
    u_deep = turn_point(G, lay['tail'][max(lay['tail'])])[1]
    u_first = turn_point(G, s_h1)[1]
    files = {}
    for L in plan.LANES:
        lp = G.ST_LANE[G.LANE_OFF[L]]
        files[L] = flat([lp.at(lp.L - 0.05)] + G.bypass(L, u_deep) + G.uturn(L, u_deep))
    lanes = []
    for j in range(6):
        L = routes.lane_of(j)
        u_end = G.uturn(L, u_deep)[-1]
        after = M.lane_track(j, M.s_at_tau(M.tau_gate[j] + GATE_DRAW_AFTER), s_start=s_h1)
        lanes.append(flat([u_end] + list(M.lane_pts(j, 0.0, s_h1)) + list(after[1:])))
    return dict(blocks=blocks, files=files, lanes=lanes, step=routes.STAGE_STEP, gap=round(lay['gap'], 4),
                band=flat(G.stage_band(routes.STAGE_HEAD_U - 0.05, routes.STAGE_START_U, -0.25, 0.25)),
                bypassBand=flat(G.stage_band(routes.BYPASS_U, u_deep + 0.25, -0.44, -0.25)),
                uturn=flat([G.B2.off(u_first, routes.UTURN_C)]), uturnU=ud(u_deep),
                gateClear=[ud(routes.GATE_U - 0.47), ud(routes.STAGE_HEAD_U)], stairClear=[0.0, ud(routes.ARRIVE_U)],
                laneOff=[round(routes.stage_off(j), 3) for j in range(6)])


RULES = [
    '兩路：A 路白衣靠看台側、B 路藍衣外側（B1 走廊、樓梯都一樣）；大隊 1→9 依序，兩路同時走（同版本 3）',
    '每一路三列交錯排隊：每列排大的先，三列輪流各出一人（白衣列 6k−5→6k−4→6k−3，藍衣列 6k−2→6k−1→6k），排完的列跳過（同版本 3）',
    '出口：白衣依序用 139 → 140 → 141 → 142，藍衣用 142 → 143 → 144 → 145；出口坐滿才換下一個，換口可以落在大隊中間（同版本 3）',
    '142 兩路共用：藍衣大隊 1–3 先從上排出，白衣大隊 9 最後從下排出；任何時刻白衣用的出口都比藍衣近、且在不同階梯，所以走廊上不交叉（同版本 3）',
    '每個出口是一條隊伍：由上排往下、每排由出口側往中央，先走的坐上面（同版本 3）',
    'B2 集合區（11/8 彩排後改）：西一入口前與樓梯口不排隊、只走路。集合區是西一入口以南那段 B2 走廊（2c 藍衣集結區所在），九個大隊各有一個集合位置，大隊 1 最靠西一入口、大隊 9 最深——和放行順序一致，先放行的不必穿過還在整隊的',
    '下樓後仍是白衣一路、藍衣一路（白衣靠場側），經走廊外側的通行帶走到自己那一排的後方，左轉 180°（白衣內圈、藍衣外圈，同心不交叉；轉過來白衣仍在行進方向左側），後面的人迴轉點只再深一排，白衣散成三路、藍衣散成三路，沿自己那一路走回自己大隊的集合位置；先到的站前面，所以沒有人穿過已站好的人；到位前中途不停，樓梯上也不等',
    '集合位置六路：面向西一入口時左側三路白衣、右側三路藍衣，第 1 路（列 6k−5）在最左（走廊外側）；隊頭是每列排號最大那一位（同版本 3 的進門順序）',
    '放行：九個大隊全部在集合位置站定才開始放行，依大隊 1→9；隊頭一排六人並肩、一排緊跟一排離開，後面的排往前補到隊頭再走；下一大隊第一排緊跟在上一大隊最後一排之後。集合區還沒準備好時，由休息區出口幹部控制放人（人留在座位），不在樓梯上等',
    '整排轉彎：一排六人從集合位置隊頭到自己大隊的列區南緣並肩——沿 B2 往回走、右轉進西一入口、穿過門洞、右轉沿全壘打牆內側、左轉北行、沿第 4–9 排地標一條直線往北（11/9 由版本 3 定案的第 5–10 排整體往西移一欄）；第 1 路（白衣列 6k−5）永遠在行進方向左側：集合區在外側、門洞裡在北、北行時在西（第 4 排地標旁）、進列時對到大隊第一列；不閃舞台、不上舞台階梯，六路都在地面（第 1 路在舞台東側階梯旁最近約 0.84 m）',
    '走到自己那列再轉（同版本 3 定案）：到了自己大隊列區南緣，每人沿自己那一路（兩欄之間的空隙）繼續往北，走到自己那一列才轉；座位在東側的右轉沿那一列往東，座位在西側的在那一列南邊半格的空隙往西、到座位正南方再往北半格進列；北行時壓過的是後面大隊還空著的座位',
    '第 9 排對齊（11/9）：轉進自己那一列往東之後，座位在第 10 排以東的人，每一列排頭先走到第 9 排（第 9、10 排之間的空隙）停住，後面的人跟著前一位停（前後約 0.5 m），所以整塊停住；同一大隊六列排頭都到第 9 排、對齊了，全隊停住的人一起往東走到位，還在路上的人照走不停。第 6 路（最東）一轉進列就到第 9 排、等最久，它後面的人會停回分出點之前、在自己那一路上停。座位在第 9 排與以內的人直接走到自己的位置，不停、也不會被擋',
    '版本 3 的迴廊候隊拿掉：九個大隊改在集合區等，進門後直接北行、進列',
]
ASSUMPTIONS = [
    '1 單位 ≈ 7.6 m；步速 1.1 單位/秒；樓梯同一路相鄰兩人 0.2 秒、兩路錯開 0.17 秒、大隊交界加 0.8 秒；放行後 0.2 秒一排（排距約 1.7 m）；皆為動畫節奏，不是現場秒數',
    '集合區的大小是示意：圖面 B2 走廊只畫六路寬（±0.2 單位），從西一入口南側到圖面盡頭約 12 單位；九個大隊每路前後 0.04 單位（約 0.3 m）才排得進去，這是圖面點距，不是現場間距或容量；「九個大隊排得下」是現場觀察，未驗證',
    '版本 1 圖面在集合區裡的兩根場邊柱 L7、L8（大隊 7、8 的集合位置）先假設不存在：圖面不畫、不算衝突；檢核仍列出若有柱子會碰到的人數，現場若有柱子要改集合位置',
    '通行帶畫在圖面走廊帶外（偏移 −0.30／−0.38），是假設：走廊實際寬度要能在六路旁再留兩人並行；每人在自己那一排後方轉 180° 也是假設（要能兩人並行迴轉；大隊 9 最後幾排在圖面盡頭附近，盡頭之後的邊界未知）',
    '整排並肩的線距：集合區、門洞與沿牆段 0.08 單位，北轉時漸變為座位列距 0.13；轉彎內圈半徑至少 0.08、外圈走步速；只在西一入口門洞穿過全壘打牆；離舞台線稿至少 0.15 單位，不走上舞台階梯',
    '座位、看台幾何、走道口、西一入口與場內路徑沿用版本 1 的示意圖面；保留不坐：139 的 34 席給台東（第 1–10 排 1–3 號、第 11–12 排 4–5 號）、144 第 1–6 排 72 席',
    '樓梯照企劃圖 6白 的綠色 L 形；西一入口 4 扇門、可 12 人並排；長度與寬度為示意',
    '碰撞檢查為圖面點距（0.03 單位），不是人體寬度或通道容量認證',
    '緩衝只有集合區：樓梯以上沒有候隊，任何一人延誤，後面整路跟著延誤；九個大隊全部站定才開始放行，任何一位沒到，全部都等',
    '本版只處理入場；彩排用的外門快速退場方式沒有放進來，不是正式場定案',
]


def write_seats_csv(data, path):
    cols = ['位置編碼', '衣色', '大隊', '演繹列', '演繹位置', '休息區', '休息排', '座號', '出口', '出口帶隊序',
            '樓梯路', '樓梯序號', '欄內順序', '集結區', '西一入口路', '西一入口序號']
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(cols)
        for p in sorted(data['persons'], key=lambda p: (p['lie'], p['pai'])):
            w.writerow([p['id'], p['costume'], p['dadui'], p['lie'], p['pai'], p['rest']['sec'], p['rest']['pai'], p['rest']['no'],
                        p['exit'], p['exitSeq'] + 1, p['lane'], p['laneIdx'] + 1, p['slot'] + 1, f"{STAGE_LABEL} 大隊 {p['dadui']} 第 {p['stageRank'] + 1} 排",
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
    lay = stage_layout(G, people)
    R = prepare(G, people, lay)
    sched, clocks = schedule(G, people, R, lay)
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
