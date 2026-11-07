"""一排六人並肩進場（整排轉彎，wheel turn）的中心線與六條平移線。

隊頭（門前隊伍 u 4.2）→ 左轉進西一入口 → 穿過門洞 → 右轉沿 insideWalk（貼牆內側）→ 左轉北行 → 沿第 5–10 排地標直線北行（不上舞台階梯） → 各大隊在自己列區南緣分出。
- 中心線 = 直線 + 圓弧（折線轉角倒圓角），全部大隊共用；大隊 d 走到 split_s(d) 為止。
- lane j 是中心線往左平移 (2.5 − j) × 間距（lane 0 在行進方向左側）；間距 0.08（隊伍）在西一入口直段漸變到 0.1316（座位列距）。
- 時間：同一時刻六人在同一條法線上（整排一起轉）；每一小段的時間 = 六條線中走最遠那條的路程 / V，
  所以外圈正好是步速、內圈依半徑比放慢，直線段六人都是步速。所有排的速度剖面都一樣，只差 t.enter。
- 分出之後每人沿自己那條線走到自己那一列才轉：座位在東側的右轉往東；座位在西側的在那一列南邊半格的空隙往西（west_plan 錯開人流）。
"""
import math

from geo import pairs

V = 1.1
SP_QUEUE, SP_SEAT = 0.08, 0.1316         # 門前隊伍的線距；座位列距（lie 之間的 Y 間距）
INNER_MIN = 0.08                         # 整排轉彎內圈半徑下限
DS = 0.01                                # 取樣步長（單位）
WALK_OFF = -0.09                         # 沿牆段：中心線比 insideWalk 往牆側移（舞台南翼角離 insideWalk 只有 0.28，要留 0.15）
WALK_TOL = 0.04                          # insideWalk 折線簡化的容許誤差（再倒圓角）
SEAT_X0 = -4.934                         # 座位欄的網格原點（pai 1 那一欄）；欄距 = SP_SEAT
# 北行段：沿牆段轉北之後一條直線往北，不閃舞台、不上階梯。中心線在第 8 排（pai 8）那一欄上，六路（半整數偏移）
# 就走在第 5–10 排地標東側緊鄰的欄間空隙（lane j 貼著第 5+j 排），離任何座位半格；最西的第 1 路離舞台階梯 0.24 以上。
NORTH_X = SEAT_X0 + 7 * SP_SEAT
NORTH = [(NORTH_X, 1.2)]
R_GATE_IN, R_WALL, R_NORTH = 0.35, 0.45, 0.45
SPLIT_AHEAD = 0.12                       # 大隊在最南一列之南這麼遠處分出
NORTH_TY = -0.2                          # 中心線切線 ty < 這個值算「往北走」（北行段）；否則還在沿牆段（大隊 9 在沿牆段就分出）
TURN_R = 0.08                            # 分出後各人轉進自己那一列的轉彎半徑
GAP_H = SP_SEAT / 2                      # 半格：兩列（兩欄）中間的空隙離座位的距離


def _unit(a, b):
    d = math.dist(a, b)
    return ((b[0] - a[0]) / d, (b[1] - a[1]) / d)


def _cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


class Centerline:
    """折線倒圓角：prims 為 ('L', p, q) 或 ('A', 圓心, 半徑, 起角, 掃角)；畫面座標 y 向下，左法向 = (ty, −tx)。"""

    def __init__(self, pts, radii):
        self.prims = []
        cur = pts[0]
        for i in range(1, len(pts) - 1):
            p, d1, d2 = pts[i], _unit(pts[i - 1], pts[i]), _unit(pts[i], pts[i + 1])
            cr = _cross(d1, d2)
            phi = math.atan2(cr, d1[0] * d2[0] + d1[1] * d2[1])
            r = radii[i - 1]
            t = r * math.tan(abs(phi) / 2)
            a = (p[0] - d1[0] * t, p[1] - d1[1] * t)
            b = (p[0] + d2[0] * t, p[1] + d2[1] * t)
            assert math.dist(cur, p) >= t - 1e-9 and math.dist(p, pts[i + 1]) >= t - 1e-9, ('轉角放不下', i, p, r)
            assert ((a[0] - cur[0]) * d1[0] + (a[1] - cur[1]) * d1[1]) >= -1e-9, ('相鄰轉角重疊', i, p)
            n1 = (d1[1], -d1[0])
            sgn = 1 if cr < 0 else -1                           # cr < 0：左轉，圓心在左
            c = (a[0] + n1[0] * r * sgn, a[1] + n1[1] * r * sgn)
            a0 = math.atan2(a[1] - c[1], a[0] - c[0])
            self.prims.append(('L', cur, a))
            self.prims.append(('A', c, r, a0, phi))
            cur = b
        self.prims.append(('L', cur, pts[-1]))
        self.lens = [math.dist(q[1], q[2]) if q[0] == 'L' else abs(q[4]) * q[2] for q in self.prims]
        self.cum = [0.0]
        for L in self.lens:
            self.cum.append(self.cum[-1] + L)
        self.L = self.cum[-1]

    def at(self, s):
        """(x, y, tx, ty, 曲率)；曲率 > 0 為左轉。"""
        s = max(0.0, min(self.L, s))
        i = 0
        while i < len(self.prims) - 1 and s > self.cum[i + 1]:
            i += 1
        q, f = self.prims[i], s - self.cum[i]
        if q[0] == 'L':
            d = _unit(q[1], q[2]) if self.lens[i] > 1e-12 else _unit(q[1], (q[1][0] + 1e-9, q[1][1]))
            return (q[1][0] + d[0] * f, q[1][1] + d[1] * f, d[0], d[1], 0.0)
        _, c, r, a0, phi = q
        ang = a0 + (f / r) * (1 if phi > 0 else -1)
        x, y = c[0] + r * math.cos(ang), c[1] + r * math.sin(ang)
        tx, ty = (-math.sin(ang), math.cos(ang)) if phi > 0 else (math.sin(ang), -math.cos(ang))
        return (x, y, tx, ty, (-1 if phi > 0 else 1) / r)

    def arcs(self):
        """每個轉彎：(起 s, 迄 s, 半徑, 左轉?)。"""
        return [(self.cum[i], self.cum[i + 1], q[2], q[4] < 0) for i, q in enumerate(self.prims) if q[0] == 'A']


def lane_off(j, sp):
    return (2.5 - j) * sp


class March:
    def __init__(self, G, base, u0):
        """G：routes.Geometry（B2 走廊）；base：base.json（gateIn、insideWalk、wall）；u0：隊頭在 B2 的 u。
        起點 = 隊頭中心 B2.at(u0)、方向 B2.tan(u0)，所以 t.enter 那一刻六人正好在 B2.off(u0, 線偏移) 的隊頭位置。"""
        q0, t0 = G.B2.at(u0), G.B2.tan(u0)
        ga, gb = pairs(base['map']['gateIn'])
        # 隊頭方向與 gateIn 線的交點（西一入口轉角）
        dg = _unit(ga, gb)
        den = _cross(t0, dg)
        k = _cross((ga[0] - q0[0], ga[1] - q0[1]), dg) / den
        corner = (q0[0] + t0[0] * k, q0[1] + t0[1] * k)
        walk = pairs(base['map']['insideWalk'])
        walk_off = _simplify(_offset(walk, WALK_OFF), WALK_TOL)
        # 沿牆段末端方向延長到北行段的 x
        e1, e2 = walk_off[-2], walk_off[-1]
        de = _unit(e1, e2)
        xs = NORTH[0][0]
        corner_n = (xs, e2[1] + de[1] * (xs - e2[0]) / de[0])
        self.pts = [q0, corner] + [_line_hit(corner, dg, walk_off[0], walk_off[1])] + walk_off[1:-1] + [corner_n] + NORTH
        radii = [R_GATE_IN, R_WALL] + [_walk_r(walk_off, i) for i in range(1, len(walk_off) - 1)] + [R_NORTH]
        self.C = Centerline(self.pts, radii)
        self._tracks = {}
        # 間距漸變：在北轉的弧內由 0.08 漸變到 0.1316（門洞與沿牆段放不下 0.13 間距；大隊 8 一轉北就分出）
        arcs = self.C.arcs()
        self.sp0, self.sp1 = arcs[-1][:2]                         # 北轉弧（corner_n 那個轉角，最後一個弧）
        self.s_walk = arcs[1][1]                                  # 沿牆段開始（右轉進 insideWalk 之後）
        self.sample()
        self.wall = pairs(base['map']['wall'])
        self.stage = [(a, b) for poly in base['map']['base']['stage'] for a, b in zip(pairs(poly), pairs(poly)[1:]) if a[0] < -4.5 and b[0] < -4.5]
        self.tau_gate = [self._wall_tau(j) for j in range(6)]     # 各線穿過全壘打牆（西一入口牆線）的 τ

    def sp(self, s):
        if s <= self.sp0:
            return SP_QUEUE
        if s >= self.sp1:
            return SP_SEAT
        return SP_QUEUE + (SP_SEAT - SP_QUEUE) * (s - self.sp0) / (self.sp1 - self.sp0)

    def lane_xy(self, s, j):
        x, y, tx, ty, _ = self.C.at(s)
        o = lane_off(j, self.sp(s))
        return (x + ty * o, y - tx * o)

    def sample(self):
        """s 取樣與時間 τ（相對 t.enter）：每段時間 = 六條線中最長的位移 / V。"""
        n = max(2, int(self.C.L / DS))
        brk = sorted({0.0, self.C.L, self.sp0, self.sp1} | {c for c in self.C.cum})
        ss = []
        for v in sorted(set([self.C.L * k / n for k in range(n + 1)] + brk)):
            if not ss or v - ss[-1] > 3e-3:                  # 斷點與格點太近就合併（Δt 太小，時間四捨五入會放大速度誤差）
                ss.append(v)
        ss[-1] = self.C.L
        self.ss = ss
        self.tau = [0.0]
        prev = [self.lane_xy(ss[0], j) for j in range(6)]
        for s in ss[1:]:
            cur = [self.lane_xy(s, j) for j in range(6)]
            self.tau.append(self.tau[-1] + max(math.dist(a, b) for a, b in zip(prev, cur)) / V)
            prev = cur

    def s_at_tau(self, tau):
        import bisect
        k = max(0, min(len(self.tau) - 2, bisect.bisect_right(self.tau, tau) - 1))
        f = (tau - self.tau[k]) / (self.tau[k + 1] - self.tau[k]) if self.tau[k + 1] > self.tau[k] else 0.0
        return self.ss[k] + (self.ss[k + 1] - self.ss[k]) * max(0.0, min(1.0, f))

    def tau_at_s(self, s):
        import bisect
        k = max(0, min(len(self.ss) - 2, bisect.bisect_right(self.ss, s) - 1))
        f = (s - self.ss[k]) / (self.ss[k + 1] - self.ss[k])
        return self.tau[k] + (self.tau[k + 1] - self.tau[k]) * max(0.0, min(1.0, f))

    def _wall_tau(self, j):
        prev = None
        for s, t in zip(self.ss, self.tau):
            q = self.lane_xy(s, j)
            if prev:
                for w1, w2 in zip(self.wall, self.wall[1:]):
                    f = _seg_hit(prev[0], q, w1, w2)
                    if f is not None:
                        return prev[1] + (t - prev[1]) * f
            prev = (q, t)
        raise SystemExit(f'第 {j} 條線沒有穿過全壘打牆')

    def split_s(self, y_south, x_front=None):
        """大隊分出點：北轉之後的正北直線上，整排第一次走到 y ≤ 最南一列 + SPLIT_AHEAD 的 s（六路都在欄間空隙上）。
        北轉弧結束時已經在最南一列半格以北（這個大隊的列區南緣在弧裡）就停止建置。"""
        for s in self.ss:
            if s >= self.sp1 - 1e-9 and self.lane_xy(s, 0)[1] <= y_south + SPLIT_AHEAD:
                if self.lane_xy(s, 0)[1] < y_south + GAP_H - 1e-9:
                    raise SystemExit(f'北轉弧結束時已經越過列區南緣（y_south = {y_south:.3f}）')
                return s
        return self.C.L

    def lane_track(self, j, s_end, tol=2e-3, s_start=0.0):
        """lane j 從 s_start（預設隊頭）到 s_end 的 (x, y, τ)：省略「與前後點等速共線」的中間點（任何省略點偏離 < tol）。
        結果只看這四個參數，同一大隊同一路的人與避撞每一輪都一樣，記下來重用（回傳 tuple，呼叫端不能改它）。"""
        key = (j, s_end, tol, s_start)
        if key not in self._tracks:
            self._tracks[key] = tuple(self._lane_track(*key))
        return self._tracks[key]

    def _lane_track(self, j, s_end, tol, s_start):
        raw = [(*self.lane_xy(s_start, j), self.tau_at_s(s_start))] if s_start > 0 else []
        raw += [(*self.lane_xy(s, j), t) for s, t in zip(self.ss, self.tau) if s_start + 1e-9 < s < s_end - 1e-9 or (s_start == 0 and s == 0)]
        raw.append((*self.lane_xy(s_end, j), self.tau_at_s(s_end)))
        out, k = [raw[0]], 0
        while k < len(raw) - 1:
            m = k + 1
            while m + 1 < len(raw) and _fits(raw, k, m + 1, tol):
                m += 1
            out.append(raw[m])
            k = m
        return out

    def stage_clear(self, q):
        """q 離舞台線稿（X < −4.5 的部分）的距離。"""
        best = 9.0
        for (ax, ay), (bx, by) in self.stage:
            dx, dy = bx - ax, by - ay
            L2 = dx * dx + dy * dy or 1e-12
            f = max(0.0, min(1.0, ((q[0] - ax) * dx + (q[1] - ay) * dy) / L2))
            best = min(best, math.hypot(q[0] - ax - dx * f, q[1] - ay - dy * f))
        return best

    def tail(self, p0, heading, seat, xlim, y_south, f_lat=None):
        """分出之後的個人路線（不含 p0）：點 (x, y) 或 (x, y, 速度倍數)，沒寫倍數就是步速。座位都在同一個網格上（欄距、列距都是 SP_SEAT，原點 SEAT_X0），
        「欄間空隙」（座位欄 ± 半格）與「列間空隙」（座位列 ± 半格）離任何座位都是半格（GAP_H = 0.066），
        走在那裡不會擦過已坐好的人，也不會擦過正坐下的同排的人。
        分出點在正北直線上，六路都在欄間空隙 ax；每人沿自己那一路直直往北，走到自己那一列才轉：
        1. 座位在 ax 東側：走到自己那一列右轉往東到座位（同一列由東往西坐，經過的座位都還空著）。
        2. 座位在 ax 西側：走到自己那一列南邊半格的列間空隙左轉往西，到座位正南方再往北半格進座位
           （同一列東側的座位已經有人，所以不沿著列走，改走列間空隙）。f_lat：build.avoid 指定的往西那一段速度倍數。
        xlim、y_south 保留給呼叫端（不再使用）。"""
        xs, ys = seat
        if heading[1] >= NORTH_TY:
            raise SystemExit('分出點不在北行直線上')
        ax = SEAT_X0 + SP_SEAT * (math.floor((p0[0] - SEAT_X0) / SP_SEAT) + 0.5)
        out = [(ax, p0[1] - abs(ax - p0[0]))] if abs(ax - p0[0]) > 1e-6 else []
        y_from = out[-1][1] if out else p0[1]
        if ax < xs:
            r = min(TURN_R, xs - ax, y_from - ys)
            c = (ax + r, ys + r)
            return out + [(c[0] - r * math.cos(math.pi / 2 * i / 6), c[1] - r * math.sin(math.pi / 2 * i / 6)) for i in range(7)] + [(xs, ys)]
        yg = ys + GAP_H
        pts = out + ([(ax, yg)] if y_from > yg + 1e-9 else [])
        return pts + west_plan(ax, yg, xs, f_lat if f_lat is not None else 1.0) + [(xs, ys)]


# 往西進列（座位在自己那一路西側）要橫越西側幾路還在往北走的人流：同一排六人同時走到同一個 Y、一排接一排每 RANK_GAP 秒，
# 所以人流在「跟著往北走的座標」裡是欄距 × 排距（SP_SEAT × V·RANK_GAP）的格點。沿列間空隙等速往西，每過一欄的節拍相同，
# 連過 4–5 欄時一定有一欄正好碰上某一排（等速直走無解）。所以每人在列間空隙裡規劃：在每個座位欄上的折點離空隙中線
# 偏移 WEST_DY 之一（離座位列至少 GAP_H − 0.03 = 0.036），兩折點之間是直線；平的那一段可以放慢到 WEST_F 之一（≥ 0.7 倍步速），
# 斜的那一段走步速。在格點人流裡選離每一個人都最遠的走法（beam search）。
RANK_GAP = 0.2
WEST_DY = (-0.03, -0.015, 0.0, 0.015, 0.03)
WEST_F = (1.0, 0.9, 0.8, 0.7)
WEST_BEAM = 40


def _seg_min(p0, t0, p1, t1, cols, yg):
    """walker 從 (p0, t0) 直線到 (p1, t1)；人流在 x ∈ cols、於 t = n·RANK_GAP 時在 yg、以 V 往北。回傳最近距離。"""
    dt = t1 - t0
    vx, vy = (p1[0] - p0[0]) / dt, (p1[1] - p0[1]) / dt
    best = 9.0
    for xc in cols:
        if (p0[0] - xc) * (p1[0] - xc) > 0 and min(abs(p0[0] - xc), abs(p1[0] - xc)) > 0.05:
            continue
        n0 = math.floor((t0 - 1.0) / RANK_GAP)
        for n in range(n0, n0 + int((dt + 2.0) / RANK_GAP) + 2):
            if n == 0 and abs(xc - cols[0]) < 1e-9:      # 自己那一路的這一排就是自己
                continue
            # 相對位置 d(t) = walker − 人流，t ∈ [t0, t1]
            rx0 = p0[0] - xc
            ry0 = p0[1] - (yg - V * (t0 - n * RANK_GAP))
            rvx, rvy = vx, vy + V
            vv = rvx * rvx + rvy * rvy
            f = 0.0 if vv < 1e-12 else max(0.0, min(dt, -(rx0 * rvx + ry0 * rvy) / vv))
            best = min(best, math.hypot(rx0 + rvx * f, ry0 + rvy * f))
    return best


def west_plan(ax, yg, xs, f_cap=1.0):
    """從 (ax, yg)（此刻同一排的人都在 yg）往西到 (xs, yg) 的折點（不含起點）：(x, y, 速度倍數)。"""
    lane = int(round((ax - NORTH_X) / SP_SEAT + 2.5))    # 自己是第幾路：西側還有 lane 條欄間空隙有人往北走
    n_cross = min(lane, int(round((ax - xs) / SP_SEAT - 0.5)))   # 會跨過其中幾條（ax 西側、xs 東側）
    if n_cross <= 0:
        return [(xs, yg, f_cap)]
    cols = [ax - k * SP_SEAT for k in range(0, n_cross + 1)]
    wps = [ax - (k + 0.5) * SP_SEAT for k in range(n_cross)] + [xs]
    fs = [f for f in WEST_F if f <= f_cap + 1e-9] or [f_cap]
    beam = [(9.0, 0.0, 0.0, [])]                         # (目前最近距離, 時刻, 偏移, 折點)
    for i, x in enumerate(wps):
        last = i == len(wps) - 1
        cand = {}
        for score, t, dy0, pts in beam:
            p0 = (pts[-1][0], pts[-1][1]) if pts else (ax, yg)
            for dy in ((0.0,) if last else WEST_DY):
                p1 = (x, yg + dy)
                d = math.dist(p0, p1)
                for f in (fs if abs(dy - dy0) < 1e-9 else (1.0,)):
                    t1 = t + d / (V * f)
                    sc = min(score, _seg_min(p0, t, p1, t1, cols, yg))
                    key = (round(dy, 4), round(t1, 2))
                    if key not in cand or cand[key][0] < sc:
                        cand[key] = (sc, t1, dy, pts + [(x, yg + dy, f)])
        beam = sorted(cand.values(), key=lambda c: (-c[0], c[1]))[:WEST_BEAM]
    return beam[0][3]


def export(M, split):
    """寫進 data.json map.march：中心線取樣（τ 相對 t.enter）與間距，check.py 用它驗並肩、轉彎與步速。"""
    xs, ys, txs, tys, sps = [], [], [], [], []
    for s in M.ss:
        x, y, tx, ty, _ = M.C.at(s)
        xs.append(x); ys.append(y); txs.append(tx); tys.append(ty); sps.append(M.sp(s))
    r9 = lambda v: [round(q, 9) for q in v]
    return dict(tau=r9(M.tau), x=r9(xs), y=r9(ys), tx=r9(txs), ty=r9(tys), sp=r9(sps),
                stageTau=[round(M.tau_at_s(M.s_walk), 6), round(M.tau_at_s(M.sp0), 6)],
                arcs=[[round(M.tau_at_s(a), 6), round(M.tau_at_s(b), 6), round(r, 6), left] for a, b, r, left in M.C.arcs()],
                tauGate=[round(t, 6) for t in M.tau_gate], split={str(d): round(M.tau_at_s(s), 6) for d, s in split.items()},
                spQueue=SP_QUEUE, spSeat=SP_SEAT, innerMin=INNER_MIN, speed=V)


def _fits(raw, k, m, tol):
    a, c = raw[k], raw[m]
    for b in raw[k + 1:m]:
        f = (b[2] - a[2]) / (c[2] - a[2]) if c[2] > a[2] else 0
        if math.hypot(a[0] + (c[0] - a[0]) * f - b[0], a[1] + (c[1] - a[1]) * f - b[1]) > tol:
            return False
    return True


def _seg_hit(p1, p2, p3, p4):
    """線段 p1p2 與 p3p4 相交時回傳 p1p2 上的比例，否則 None。"""
    d = (p2[0] - p1[0]) * (p4[1] - p3[1]) - (p2[1] - p1[1]) * (p4[0] - p3[0])
    if abs(d) < 1e-12:
        return None
    t = ((p3[0] - p1[0]) * (p4[1] - p3[1]) - (p3[1] - p1[1]) * (p4[0] - p3[0])) / d
    u = ((p3[0] - p1[0]) * (p2[1] - p1[1]) - (p3[1] - p1[1]) * (p2[0] - p1[0])) / d
    return t if 0 <= t <= 1 and 0 <= u <= 1 else None


def _offset(pts, o):
    import routes
    return routes.miter(pts, o)


def _line_hit(p, d, a, b):
    """射線 p + d·k 與直線 ab 的交點。"""
    e = _unit(a, b)
    k = _cross((a[0] - p[0], a[1] - p[1]), e) / _cross(d, e)
    return (p[0] + d[0] * k, p[1] + d[1] * k)


def _walk_r(pts, i):
    """沿牆折線的轉角：在相鄰兩段各一半長度內放得下的最大圓角（上限 3）。"""
    d1, d2 = _unit(pts[i - 1], pts[i]), _unit(pts[i], pts[i + 1])
    phi = abs(math.atan2(_cross(d1, d2), d1[0] * d2[0] + d1[1] * d2[1]))
    if phi < 1e-6:
        return 1.0
    room = min(math.dist(pts[i - 1], pts[i]), math.dist(pts[i], pts[i + 1])) / 2
    return min(3.0, room / math.tan(phi / 2))


def _simplify(pts, tol):
    """Douglas–Peucker：保留端點，去掉離弦小於 tol 的中間點。"""
    if len(pts) < 3:
        return list(pts)
    a, b = pts[0], pts[-1]
    d = _unit(a, b)
    far, k = -1.0, 0
    for i in range(1, len(pts) - 1):
        e = abs(_cross((pts[i][0] - a[0], pts[i][1] - a[1]), d))
        if e > far:
            far, k = e, i
    if far < tol:
        return [a, b]
    return _simplify(pts[:k + 1], tol)[:-1] + _simplify(pts[k:], tol)
