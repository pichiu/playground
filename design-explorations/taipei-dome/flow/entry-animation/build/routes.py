"""2c 集結區與路線幾何（spec §3.5），自版本 2 build.py 移植。

改動只有：走廊、樓梯、B2 一律三路（LANE_OFF）；P6 改為白3 候隊；白4 以後直達西一入口；刪除 P7–P9；
樓梯改畫成企劃圖 6白 的綠色 L 形：直段是樓梯（順著 B1 走廊往南直下），橫段是樓梯下的 B2 平台（往東接 B2 走廊）。
"""
import math
from geo import Poly, pairs
import plan

STAIR_U_B1, B2_U_START = 13.15, 1.0      # 樓梯口在 B1 走廊折線的 u；B2 走廊起點 u
U_SHIFT0, U_SHIFT1 = 5.25, 4.95          # B2 死巷後進場的大隊平行外移到西一入口三路的區間
LANE_OFF = {'A': 0.12, 'B': 0.0, 'C': -0.12}
STAIR_RUN = 0.62                         # 樓梯直段長（約 4.7 m），由 B1 走廊樓梯口往南直下
LANDING_X, LANDING_END_X = -11.80, -11.31  # B2 平台：路線走到 x −11.80 轉進 B2 走廊；底色帶接到 B2 走廊外緣
STAIR_HALF_W = 0.2                       # 樓梯／平台半寬（三路 ±0.12 加身寬）
GATE_W, GATE_DOORS = 0.95, 4                 # 西一入口：4 扇門，可 12 人並排（約 7.2 m）
GATE_LABEL = '西一入口（4 扇門）'
JOIN_AHEAD = 0.3                         # 從走廊邊併入路時往樓梯方向斜走的距離（u）
ZONES = {
    'P1':    dict(label='1',      floor='B2', kind='FIFO', corr='B2',    head=4.15,  step=-0.073),
    'P2':    dict(label='藍 2·3', floor='B2', kind='LIFO', corr='B2',    head=5.0,   step=0.075),
    'P3':    dict(label='藍 4·5', floor='B2', kind='LIFO', corr='B2',    head=8.2,   step=0.075),
    'P4':    dict(label='藍 6·7', floor='B2', kind='LIFO', corr='B2',    head=11.0,  step=0.075),
    'P5':    dict(label='藍 8·9', floor='B2', kind='LIFO', corr='B2',    head=14.5,  step=0.075),
    'STAIR': dict(label='白 2',   floor='B1', kind='FIFO', corr='STAIR'),
    'P6':    dict(label='白 3',   floor='B1', kind='FIFO', corr='B1',    head=12.75, step=-0.058),
}


def lane_run(poly, u0, u1, off, step=0.35):
    n = max(1, int(abs(u1 - u0) / step))
    return [poly.off(u0 + (u1 - u0) * k / n, off) for k in range(1, n + 1)]


def miter(pts, o):
    """折線往左法向（畫面 y 向下）平移 o，轉角取斜接點，讓每一路在轉角各自走自己的折線、不互相擠進。"""
    def nrm(a, b):
        d = math.dist(a, b) or 1e-9
        return ((b[1] - a[1]) / d, -(b[0] - a[0]) / d)
    out = []
    for k, q in enumerate(pts):
        n1 = nrm(pts[k - 1], q) if k else None
        n2 = nrm(q, pts[k + 1]) if k < len(pts) - 1 else None
        if n1 and n2:
            c = 1 + n1[0] * n2[0] + n1[1] * n2[1]
            n = ((n1[0] + n2[0]) / c, (n1[1] + n2[1]) / c)
        else:
            n = n1 or n2
        out.append((q[0] + n[0] * o, q[1] + n[1] * o))
    return out


def poly_between(poly, u0, u1):
    """折線上 u0→u1 的點（含中間的轉角頂點）。"""
    inner = [q for q, c in zip(poly.p, poly.cum) if min(u0, u1) < c < max(u0, u1)]
    return [poly.at(u0)] + (inner if u1 >= u0 else inner[::-1]) + [poly.at(u1)]


def trim_corridors(B1, B2, u_top, y_landing):
    """圖面用的走廊線：B1 畫到樓梯口為止、B2 從平台那一排開始，不再畫成穿過樓梯的樣子（路線幾何仍用完整折線，u 不變）。"""
    u2 = B2.proj((B2.at(0)[0], y_landing))[0]
    b1 = [q for q, c in zip(B1.p, B1.cum) if c < u_top] + [B1.at(u_top)]
    b2 = [B2.at(u2)] + [q for q, c in zip(B2.p, B2.cum) if c > u2]
    return dict(b1Corridor=[round(v, 3) for q in b1 for v in q], b2Corridor=[round(v, 3) for q in b2 for v in q])


def first_in_zone(person):
    """同區兩個大隊：先進場者站往西一入口不必穿越的一側。偶數大隊、大隊 1、白3（單獨一區）為先。"""
    d = person['dadui']
    return d == 1 or d % 2 == 0 or (d == 3 and person['costume'] == '白')


class Geometry:
    def __init__(self, base):
        self.D = base
        M = base['map']
        self.B1, self.B2 = Poly(pairs(M['b1Corridor'])), Poly(pairs(M['b2Corridor']))
        top = self.B1.at(STAIR_U_B1)
        bot = (top[0], top[1] + STAIR_RUN)
        self.STAIR_PTS = [top, bot, (LANDING_X, bot[1])]       # 樓梯口 → 樓梯底（B2）→ 平台東端
        self.ZONES = {k: dict(v) for k, v in ZONES.items()}
        self.LANE_OFF = dict(LANE_OFF)
        self.ST_LANE = {o: Poly(miter(self.STAIR_PTS, o)) for o in self.LANE_OFF.values()}   # 樓梯三路各自的折線
        n_of = {f['lie']: f['n'] for f in base['files']}
        n_stair = max(n_of[plan.column_of(b, L)] for b in plan.BLOCKS if plan.ZONE_OF[b] == 'STAIR' for L in plan.LANES)
        self.STAIR_SLOTS, self.STAIR_SLOT_U = {}, {}            # 白2 樓梯格位：頭在平台東端（B2），沿自己那一路往回排到樓梯上
        for j, L in enumerate(plan.LANES):
            lp = self.ST_LANE[self.LANE_OFF[L]]
            step = (lp.L - 0.08) / (n_stair - 1)
            self.STAIR_SLOT_U[j] = [lp.L - 0.03 - step * k for k in range(n_stair)]
            self.STAIR_SLOTS[j] = [lp.at(u) for u in self.STAIR_SLOT_U[j]]
        self.GATE_PTS, self.GATE_DIR = {}, {}                   # 西一入口六路收攏點：版本 1 大隊 1 過西一入口的點；GATE_DIR 是該點之後場內線的方向（橫越走廊往場側）
        for p in base['persons']:
            if p['dadui'] == 1 and p['laneIdx'] not in self.GATE_PTS:
                k = next(i for i, q in enumerate(p['path']) if abs(q[2] - p['t']['gate']) < 1e-6)
                a, b = p['path'][k], p['path'][k + 1]
                d = math.dist(a[:2], b[:2])
                self.GATE_PTS[p['laneIdx']] = (a[0], a[1])
                self.GATE_DIR[p['laneIdx']] = ((b[0] - a[0]) / d, (b[1] - a[1]) / d)
        self.ZONE_NMAX = {}
        for block in plan.BLOCKS:
            z = plan.ZONE_OF[block]
            for L in plan.LANES:
                self.ZONE_NMAX[z] = max(self.ZONE_NMAX.get(z, 0), n_of[plan.column_of(block, L)])

    # ---------- 格位 ----------
    def slot_offset(self, person):
        z, j = person['assembly'], person['gateLane']
        Z = self.ZONES[z]
        if z == 'P1':
            return 0.2 - 0.08 * j
        if Z['corr'] == 'B2':                          # 死巷：從西一入口上游反向走回來，六條場內線的先後對調 → 鏡射：最靠場側（−0.04）給最先轉進場的 j=5
            m = 5 - j                                  # 先進場者站 −0.04…−0.20、後進場者站 +0.20…+0.04（離開時平行外移到 −0.04…−0.20）
            return (-0.04 - 0.08 * m) if first_in_zone(person) else (0.2 - 0.08 * m)
        return self.LANE_OFF[person['lane']]           # P6：各路就地停在自己那一路

    def second_back(self, z):
        Z = self.ZONES[z]
        return max(0.0, U_SHIFT0 + 0.1 - Z['head']) if Z['kind'] == 'LIFO' else 0.0

    def slot_u(self, person, i):
        Z = self.ZONES[person['assembly']]
        back = 0.0 if first_in_zone(person) else self.second_back(person['assembly'])
        return Z['head'] + Z['step'] * i + back

    def slot_xy(self, person, i):
        z = person['assembly']
        if z == 'STAIR':
            j = person['gateLane']
            return self._stair_lane(j).at(self.STAIR_SLOT_U[j][i])
        poly = self.B1 if self.ZONES[z]['corr'] == 'B1' else self.B2
        return poly.off(self.slot_u(person, i), self.slot_offset(person))

    # ---------- 路線 ----------
    def _stair_lane(self, j):
        return self.ST_LANE[self.LANE_OFF[plan.LANES[j]]]

    def _down_stair(self, off):
        lp = self.ST_LANE[off]
        return [self.B1.off(STAIR_U_B1, off)] + poly_between(lp, 0.05, lp.L - 0.05)

    def _b2_to_gate(self, j):
        return lane_run(self.B2, B2_U_START, 4.2, 0.2 - 0.08 * j) + [self.GATE_PTS[j]]

    def gate_join(self, j, o):
        """從 B2 走廊偏移 o 併入第 j 路的場內線。場內線從 GATE_PTS[j]（偏移 0.2−0.08j）橫越走廊往場側：
        o 在它外側（更遠離場）就先走到線上、經過 GATE_PTS 再進場；o 已在場側就從線上那一點直接進場，不回頭。"""
        d = o - (0.2 - 0.08 * j)
        g, v = self.GATE_PTS[j], self.GATE_DIR[j]
        if abs(d) < 1e-9:
            return [g]
        join = (g[0] + v[0] * d, g[1] + v[1] * d)
        return [join, g] if d < 0 else [join]

    def arrival_route(self, person, i):
        """座位 → 走道口 → 接入點 → 自己那一路 → 集結格位（白4 以後直達西一入口）。"""
        z, j, lane = person['assembly'], person['gateLane'], person['lane']
        Z = self.ZONES.get(z)
        off = self.LANE_OFF[lane]
        pts = [(person['rest']['X'], person['rest']['Y'])] + [tuple(q) for q in person['approach']]   # 座位 → 走道口 → … → 走廊邊
        u_in = self.B1.proj(pts[-1])[0] + JOIN_AHEAD                                                # 斜向前方併入自己那一路
        if z == 'P6':                                                                               # 白3 的格位可能就在接入點前方不到 0.3：直接斜走到格位前
            u_in = min(u_in, self.slot_u(person, i) - 0.05)
        pts.append(self.B1.off(u_in, off))
        if z == 'FEEDER':
            pts += lane_run(self.B1, u_in, STAIR_U_B1 - 0.25, off) + self._down_stair(off) + self._b2_to_gate(j)
            return pts
        if Z['corr'] == 'B2':
            pts += lane_run(self.B1, u_in, STAIR_U_B1 - 0.25, off) + self._down_stair(off)
            so = self.slot_offset(person)
            if Z['kind'] == 'FIFO':                    # 大隊 1：從尾端（樓梯側）進
                if person['costume'] == '藍':          # 藍1 緊跟在藍2 隊尾後面：沿自己那路走到格位前 0.25 才側移，不踩到還在通過的藍2
                    ut = self.slot_u(person, i) - 0.25
                    pts += lane_run(self.B2, B2_U_START, ut, off)
                else:                                  # 白1 到時藍1 已站定在 −0.04…−0.2：先在 1.45→1.65 側移到 0.04…0.2 再往前
                    ut = 1.45
                    pts += lane_run(self.B2, B2_U_START, ut, off)
                    pts.append(self.B2.off(ut + 0.2, so))
                    pts += lane_run(self.B2, ut + 0.2, self.slot_u(person, i), so)
            else:                                      # 死巷：在區頭前換到自己那路，往裡走
                ut = Z['head'] - 0.3
                pts += lane_run(self.B2, B2_U_START, ut, off)
                pts.append(self.B2.off(Z['head'] - 0.1, so))
                pts += lane_run(self.B2, Z['head'] - 0.1, self.slot_u(person, i), so)
        elif z == 'STAIR':
            pts += lane_run(self.B1, u_in, STAIR_U_B1 - 0.35, off)
            pts.append(self.B1.off(STAIR_U_B1, off))
            pts += poly_between(self._stair_lane(j), 0.0, self.STAIR_SLOT_U[j][i])[:-1]   # 沿自己那一路下樓梯、轉平台，走到格位
        else:                                          # P6：沿自己那一路走到格位
            pts += lane_run(self.B1, u_in, self.slot_u(person, i), off)
        pts.append(self.slot_xy(person, i))
        return pts

    def depart_route(self, person, i):
        """集結格位 → 西一入口（白4 以後沒有這一段）。"""
        z, j, lane = person['assembly'], person['gateLane'], person['lane']
        if z == 'FEEDER':
            return []
        Z = self.ZONES[z]
        s0 = self.slot_xy(person, i)
        if z == 'P1':
            return [s0, self.GATE_PTS[j]]
        if Z['corr'] == 'B2':                           # 死巷回程：偏移鏡射（見 slot_offset），走到自己那條場內線再橫越進場
            o, o_gate = self.slot_offset(person), -0.04 - 0.08 * (5 - j)
            if abs(o - o_gate) < 1e-9:
                return [s0] + lane_run(self.B2, self.slot_u(person, i), U_SHIFT1, o) + self.gate_join(j, o_gate)
            assert self.slot_u(person, i) >= U_SHIFT0, (person['id'], i)   # 後進場者整排往外平移的空間
            return [s0] + lane_run(self.B2, self.slot_u(person, i), U_SHIFT0, o) + [self.B2.off(U_SHIFT1, o_gate)] + self.gate_join(j, o_gate)
        if z == 'STAIR':
            return [s0] + poly_between(self._stair_lane(j), self.STAIR_SLOT_U[j][i], self.STAIR_SLOT_U[j][0])[1:] + self._b2_to_gate(j)
        off = self.LANE_OFF[lane]                       # P6
        return [s0] + lane_run(self.B1, self.slot_u(person, i), STAIR_U_B1 - 0.25, off) + self._down_stair(off) + self._b2_to_gate(j)

    def stair_top_index(self, pts):
        """路線中樓梯口那個點的序號（沒有經過樓梯口回 None）。"""
        tops = [self.B1.off(STAIR_U_B1, off) for off in self.LANE_OFF.values()]
        for k, q in enumerate(pts):
            if any(math.dist(q, t) < 1e-6 for t in tops):
                return k
        return None

    # ---------- 圖面 ----------
    def stair_map(self):
        """樓梯 L 形的圖面：stair 是路線中線，stairBand 是底色帶（平台接到 B2 走廊外緣），stairTreads 是直段的踏階線。"""
        top, bot, _ = self.STAIR_PTS
        band = [top, bot, (LANDING_END_X, bot[1])]
        ring = miter(band, STAIR_HALF_W) + miter(band, -STAIR_HALF_W)[::-1]
        n = 8
        treads = [[round(top[0] - STAIR_HALF_W, 3), round(top[1] + STAIR_RUN * k / n, 3), round(top[0] + STAIR_HALF_W, 3), round(top[1] + STAIR_RUN * k / n, 3)]
                  for k in range(1, n)]
        flat = lambda pts: [round(v, 3) for q in pts for v in q]
        return dict(stair=flat(self.STAIR_PTS), stairBand=flat(ring), stairTreads=treads,
                    **trim_corridors(self.B1, self.B2, STAIR_U_B1, bot[1]))

    def gate_map(self):
        """西一入口：中線沿用版本 1 的 gateIn（B2 走廊 → 場內），帶寬 = 4 扇門可 12 人並排；門畫在場內端，橫跨通行方向。"""
        a, b = pairs(self.D['map']['gateIn'])
        d = math.dist(a, b)
        tx, ty = (b[0] - a[0]) / d, (b[1] - a[1]) / d
        nx, ny = ty, -tx
        h = GATE_W / 2
        band = [(a[0] + nx * h, a[1] + ny * h), (b[0] + nx * h, b[1] + ny * h), (b[0] - nx * h, b[1] - ny * h), (a[0] - nx * h, a[1] - ny * h)]
        gap = 0.04
        w = (GATE_W - gap * (GATE_DOORS - 1)) / GATE_DOORS
        doors = []
        for k in range(GATE_DOORS):
            s0 = -h + k * (w + gap)
            doors.append([round(v, 3) for v in (b[0] + nx * s0, b[1] + ny * s0, b[0] + nx * (s0 + w), b[1] + ny * (s0 + w))])
        return dict(doors=doors, band=[round(v, 3) for q in band for v in q])

    # ---------- 區域 ----------
    def region(self, z):
        Z = self.ZONES[z]
        if z == 'STAIR':
            return [('STAIR', 0, 1), ('B1', STAIR_U_B1 - 0.3, STAIR_U_B1)]
        nmax = self.ZONE_NMAX[z]
        a, b = Z['head'], Z['head'] + Z['step'] * (nmax - 1) + self.second_back(z)
        return [(Z['corr'], min(a, b) - 0.1, max(a, b) + 0.1)]

    def regions(self):
        R = {z: self.region(z) for z in self.ZONES}
        for z1 in R:
            for z2 in R:
                if z1 >= z2:
                    continue
                for c1, a1, b1 in R[z1]:
                    for c2, a2, b2 in R[z2]:
                        if c1 == c2 != 'STAIR':
                            assert b1 - 0.1 <= a2 + 0.1 or b2 - 0.1 <= a1 + 0.1, ('集結區重疊', z1, z2)
        return R
