"""版本 3.1b：B1 先整六路、逐大隊兩路兩路拉下 B2、整隊迴轉（設計見 docs/superpowers/specs/2026-11-10-entry-plan-v3.1b-design.md）。

只取代 3.1「座位 → B2 集合位置站定」這一段；放行之後（build.schedule 第 2、3 步、march、align_sim）原封不動。

B1 走廊偏移：正 = 看台側 = 往樓梯走時的左側。六路 j（gateLane 0–5）在 b1_off(j) = B1_OFF0 − 0.08j，第 1 路（j 0）在看台側。
看台側另有一條 B1 通行帶（B1_BAND）：出口落在自己那一隊整隊範圍裡的人，沿它往上游走到隊尾後方，再橫進自己那一路、往前走到位置。

B1 有兩個位置：整隊點（隊頭在 B1_HEAD_U，正在拉的大隊）與後隊（隊頭在整隊點隊尾後方 B1_GAP）。大隊 1 直接在整隊點整隊；
大隊 d ≥ 2 在大隊 d−1 第一位到樓梯口時離座、在後隊整隊，大隊 d−1 全部離開且自己全員站定後整隊往前補到整隊點。

拉下樓：每個大隊依 PAIRS（第 5、6 路 → 3、4 → 1、2），一對兩路同時（左路先、右路錯開 STAGGER），每一路依排號由小到大（隊頭先）一人 HEADWAY。
樓梯上左路走 A（+0.12）、右路走 B（−0.12）。B2 下樓後左路移到通行帶 −0.30、右路 −0.38，沿通行帶走到自己大隊隊尾再深 TURN_GAP，
在那裡左轉 180°（圓心偏移 = 通行帶與自己那一路偏移的中點，一對同心），轉完沿自己那一路往入口走到自己的位置。
"""
import math
import routes
from routes import STAIR_U_B1, LANE_OFF, BYPASS_OFF, STAGE_STEP, lane_run

B1_HEAD_U = STAIR_U_B1 - 0.3       # 整隊點隊頭（樓梯口前 0.3：一對兩路從這裡斜移到樓梯兩路）
B1_STEP = STAGE_STEP               # B1 前後間距（同 B2 集合區，圖面點距）
B1_GAP = 0.12                      # 後隊隊頭在整隊點隊尾後方這麼遠（同 STAGE_GAP_MIN）
B1_OFF0 = 0.14                     # 第 1 路的 B1 偏移；六路 +0.14 … −0.26
B1_BAND = 0.24                     # 看台側 B1 通行帶（出口在走廊邊 +0.25）
B1_ENTRY_BACK = 0.08               # 隊尾後方這麼遠橫進自己那一路
TURN_GAP = 0.04                    # B2 迴轉圓心在自己大隊隊尾再深這麼多
PAIRS = [(4, 5), (2, 3), (0, 1)]   # 拉下樓的順序：第 5、6 路 → 3、4 → 1、2（左路 = j 小的那一路）
PAIR_NAME = {(4, 5): '56', (2, 3): '34', (0, 1): '12'}
STAIR_SIDE = {0: 'A', 1: 'B'}      # 一對裡的左路走樓梯 A（+0.12）、右路走 B（−0.12）


def b1_off(j):
    return B1_OFF0 - 0.08 * j


def pair_of(j):
    return next(pr for pr in PAIRS if j in pr)


def side_of(j):
    """'A'＝一對裡的左路（j 小）、'B'＝右路。"""
    return STAIR_SIDE[pair_of(j).index(j)]


def turn_center_off(j):
    return (BYPASS_OFF[side_of(j)] + routes.stage_off(j)) / 2


def uturn_pts(G, j, u_c, n=12):
    """自己那一對的左轉 180°：圓心 B2.off(u_c, 中點)，從通行帶轉到自己那一路；回傳轉彎上的點（不含起點）。"""
    c_off = turn_center_off(j)
    r = c_off - BYPASS_OFF[side_of(j)]
    c = G.B2.off(u_c, c_off)
    t, nv = G.B2.tan(u_c), G.B2.nrm(u_c)
    return [(c[0] + r * (-nv[0] * math.cos(a) + t[0] * math.sin(a)), c[1] + r * (-nv[1] * math.cos(a) + t[1] * math.sin(a)))
            for a in (math.pi * k / n for k in range(1, n + 1))]


def rows(people):
    """各大隊的排數（= 該大隊最長那一列的人數）。"""
    out = {}
    for p in people:
        out[p['dadui']] = max(out.get(p['dadui'], 0), p['slot'] + 1)
    return out


def layout(people):
    """B1 位置：front_u(r) = B1_HEAD_U − B1_STEP·r；大隊 d ≥ 2 的後隊隊頭 back[d] = B1_HEAD_U − B1_STEP·rows(d−1) − B1_GAP；delta[d] = 往前補的距離。"""
    n = rows(people)
    ds = sorted(n)
    back, delta = {ds[0]: B1_HEAD_U}, {ds[0]: 0.0}
    for a, b in zip(ds, ds[1:]):
        back[b] = B1_HEAD_U - B1_STEP * n[a] - B1_GAP
        delta[b] = B1_HEAD_U - back[b]
    return dict(rows=n, back=back, delta=delta)


def _cum(pts):
    c = [0.0]
    for a, b in zip(pts, pts[1:]):
        c.append(c[-1] + math.dist(a[:2], b[:2]))
    return c


def routes_of(G, M, p, b1lay, s_slot, u_tail):
    """回傳 dict：to_b1（座位 → B1 自己的位置，後隊或整隊點）、mu（後隊 → 整隊點，往前補，兩點）、go（整隊點位置 → 樓梯 → B2 → 迴轉 → 自己集合位置），
    及 go 上樓梯口、迴轉結束的序號。"""
    j, d, r = p['gateLane'], p['dadui'], p['slot']
    o = b1_off(j)
    u_back = b1lay['back'][d] - B1_STEP * r
    u_front = B1_HEAD_U - B1_STEP * r
    u_e = b1lay['back'][d] - B1_STEP * (b1lay['rows'][d] - 1) - B1_ENTRY_BACK      # 自己那一隊隊尾後方
    pts = [(p['rest']['X'], p['rest']['Y'])] + [tuple(q) for q in p['approach']]
    u_a = G.B1.proj(pts[-1])[0]
    if u_a + routes.JOIN_AHEAD <= u_e:
        u_in = u_a + routes.JOIN_AHEAD
        pts.append(G.B1.off(u_in, o))                              # 斜向前方併入自己那一路（在隊尾之後，那裡還沒有人站）
    else:
        pts.append(G.B1.off(u_a - 0.05, B1_BAND))                 # 出口在自己那一隊範圍裡：上 B1 通行帶，往上游走到隊尾後方
        pts += lane_run(G.B1, u_a - 0.05, u_e, B1_BAND)
        u_in = u_e - 0.05
        pts.append(G.B1.off(u_in, o))
    pts += lane_run(G.B1, u_in, u_back, o)
    mu = [G.B1.off(u_back, o), G.B1.off(u_front, o)]
    side = side_of(j)
    s_off = LANE_OFF[side]
    go = [G.B1.off(u_front, o)]
    if r > 0:
        go.append(G.B1.off(B1_HEAD_U, o))
    go += G._down_stair(s_off)                                    # 第一點是 B1.off(STAIR_U_B1, s_off)：樓梯口
    i_top = len(go) - len(G._down_stair(s_off))
    u_c = u_tail + TURN_GAP
    go += G.bypass(side, u_c)
    go += uturn_pts(G, j, u_c)
    i_turn = len(go) - 1
    s_c = M.s_of_u(u_c)
    go += [q[:2] for q in M.lane_pts(j, s_c, s_slot)][1:]
    c = _cum(go)
    return dict(to_b1=pts, L_b1=_cum(pts)[-1], mu=mu, go=go, d_top=c[i_top], L_turn=c[i_turn], L_go=c[-1], u_c=u_c)


def schedule_pre(G, people, R, V, T0, HEADWAY, STAGGER, DADUI_GAP):
    """座位 → B2 站定的時刻（每人）：leave、b1（在 B1 站定）、mu0（開始往前補）、ready（到整隊點）、b1Go（離開整隊點）、stair、entry（迴轉完）、assembly。"""
    b1lay = R['_b1lay']
    by_d = {}
    for p in people:
        by_d.setdefault(p['dadui'], []).append(p)
    out, release, prev_end, prev_golast = {}, T0, None, None
    LANE_K = {'A': 0, 'B': 1}
    info = {}
    for d in sorted(by_d):
        ps = by_d[d]
        rel = {p['id']: HEADWAY * p['dadIdx'] + STAGGER * LANE_K[p['lane']] for p in ps}        # 離座順序同 3.1（每路依 laneIdx、兩路錯開）
        A = max(release + R[p['id']]['L_b1'] / V - rel[p['id']] for p in ps)                     # 到 B1 位置的時鐘：每一路先到的站前面、中途不停
        b1 = {p['id']: A + rel[p['id']] for p in ps}
        stood = max(b1.values())
        mu0 = stood if prev_golast is None else max(stood, prev_golast)
        ready = mu0 + b1lay['delta'][d] / V
        # 樓梯時刻（相對 P）：PAIRS 依序，一對兩路同時（右路錯開），每一路隊頭先
        offs, base = {}, 0.0
        for pr in PAIRS:
            end = base
            for k, j in enumerate(pr):
                col = sorted((p for p in ps if p['gateLane'] == j), key=lambda p: p['slot'])
                for n, p in enumerate(col):
                    offs[p['id']] = base + HEADWAY * n + STAGGER * k
                    end = max(end, offs[p['id']])
            base = end + HEADWAY
        P = max(ready + R[p['id']]['d_top'] / V - offs[p['id']] for p in ps)
        if prev_end is not None:
            P = max(P, prev_end + HEADWAY + DADUI_GAP)
        for p in ps:
            pid = p['id']
            st = P + offs[pid]
            go = st - R[pid]['d_top'] / V
            out[pid] = dict(leave=b1[pid] - R[pid]['L_b1'] / V, b1=b1[pid], mu0=mu0, ready=ready, b1Go=go, stair=st,
                            entry=go + R[pid]['L_turn'] / V, assembly=go + R[pid]['L_go'] / V)
        prev_end = max(P + v for v in (offs[p['id']] for p in ps))
        prev_golast = max(out[p['id']]['b1Go'] for p in ps)
        info[d] = dict(release=release, stood=stood, mu0=mu0, ready=ready, P=P, stairEnd=prev_end, stairIdle=None)
        release = P                                                                         # 下一個大隊：本大隊第一位到樓梯口時離座
    ds = sorted(info)
    for a, b in zip(ds, ds[1:]):
        info[b]['stairIdle'] = round(info[b]['P'] - (info[a]['stairEnd'] + HEADWAY + DADUI_GAP), 3)
    return out, info


def pre_path(G, p, r, t):
    """座位 → B1 位置（站）→ 往前補（站）→ 下樓 → B2 → 迴轉 → 集合位置；回傳 (x, y, t) 折線（全程步速、站的地方停）。"""
    V = (r['L_b1'] / (t['b1'] - t['leave'])) if t['b1'] > t['leave'] else 1.1
    out = []
    tt = t['leave']
    pts = r['to_b1']
    for k, q in enumerate(pts):
        if k:
            tt += math.dist(pts[k - 1], q) / V
        out.append((q[0], q[1], tt))
    a, b = r['mu']
    if math.dist(a, b) > 1e-9:
        out.append((a[0], a[1], t['mu0']))
        out.append((b[0], b[1], t['ready']))
    g = r['go']
    out.append((g[0][0], g[0][1], t['b1Go']))
    tt = t['b1Go']
    for k in range(1, len(g)):
        tt += math.dist(g[k - 1], g[k]) / V
        out.append((g[k][0], g[k][1], tt))
    return out
