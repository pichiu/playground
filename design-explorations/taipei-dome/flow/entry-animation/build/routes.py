"""2c 集結區與路線幾何（spec §3.5），自版本 2 build.py 移植。

改動只有：走廊、樓梯、B2 一律三路（LANE_OFF）；P6 改為白3 候隊；白4 以後直達 6口；刪除 P7–P9。
"""
import math
from geo import Poly, pairs
import plan

STAIR_U_B1, B2_U_START = 13.15, 1.0      # 樓梯口在 B1 走廊折線的 u；B2 走廊起點 u
U_SHIFT0, U_SHIFT1 = 5.25, 4.95          # B2 死巷後進場的大隊平行外移到 6口 三路的區間
LANE_OFF = {'A': 0.12, 'B': 0.0, 'C': -0.12}
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


def first_in_zone(person):
    """同區兩個大隊：先進場者站往 6口 不必穿越的一側。偶數大隊、大隊 1、白3（單獨一區）為先。"""
    d = person['dadui']
    return d == 1 or d % 2 == 0 or (d == 3 and person['costume'] == '白')


class Geometry:
    def __init__(self, base):
        self.D = base
        M = base['map']
        self.B1, self.B2, self.ST = Poly(pairs(M['b1Corridor'])), Poly(pairs(M['b2Corridor'])), Poly(pairs(M['stair']))
        self.ZONES = {k: dict(v) for k, v in ZONES.items()}
        self.LANE_OFF = dict(LANE_OFF)
        self.STAIR_SLOTS = {}                                   # 白2 樓梯格位：沿用版本 1 的 6白（列 31–33）
        for lie_old, j in ((31, 0), (32, 1), (33, 2)):
            ps = sorted([p for p in base['persons'] if p['lie'] == lie_old], key=lambda p: p['gateIdx'])
            self.STAIR_SLOTS[j] = [tuple(next(q for q in p['path'] if abs(q[2] - p['t']['assembly']) < 1e-6)[:2]) for p in ps]
        self.GATE_PTS, self.GATE_DIR = {}, {}                   # 6口 六路收攏點：版本 1 大隊 1 過 6口 的點；GATE_DIR 是該點之後場內線的方向（橫越走廊往場側）
        for p in base['persons']:
            if p['dadui'] == 1 and p['laneIdx'] not in self.GATE_PTS:
                k = next(i for i, q in enumerate(p['path']) if abs(q[2] - p['t']['gate']) < 1e-6)
                a, b = p['path'][k], p['path'][k + 1]
                d = math.dist(a[:2], b[:2])
                self.GATE_PTS[p['laneIdx']] = (a[0], a[1])
                self.GATE_DIR[p['laneIdx']] = ((b[0] - a[0]) / d, (b[1] - a[1]) / d)
        n_of = {f['lie']: f['n'] for f in base['files']}
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
        if Z['corr'] == 'B2':                          # 死巷：從 6口 上游反向走回來，六條場內線的先後對調 → 鏡射：最靠場側（−0.04）給最先轉進場的 j=5
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
            pts = self.STAIR_SLOTS[person['gateLane']]
            if i < len(pts):
                return pts[i]
            a, b = pts[-2], pts[-1]
            return (b[0] + (b[0] - a[0]) * (i - len(pts) + 1), b[1] + (b[1] - a[1]) * (i - len(pts) + 1))
        poly = self.B1 if self.ZONES[z]['corr'] == 'B1' else self.B2
        return poly.off(self.slot_u(person, i), self.slot_offset(person))

    # ---------- 路線 ----------
    def _down_stair(self, off):
        return [self.B1.off(STAIR_U_B1, off), self.ST.off(0.05, off), self.ST.off(self.ST.L - 0.05, off)]

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
        """座位 → 走道口 → 接入點 → 自己那一路 → 集結格位（白4 以後直達 6口）。"""
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
            pts.append(self.STAIR_SLOTS[j][-1])
        else:                                          # P6：沿自己那一路走到格位
            pts += lane_run(self.B1, u_in, self.slot_u(person, i), off)
        pts.append(self.slot_xy(person, i))
        return pts

    def depart_route(self, person, i):
        """集結格位 → 6口（白4 以後沒有這一段）。"""
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
            return [s0, self.STAIR_SLOTS[j][0]] + self._b2_to_gate(j)
        off = self.LANE_OFF[lane]                       # P6
        return [s0] + lane_run(self.B1, self.slot_u(person, i), STAIR_U_B1 - 0.25, off) + self._down_stair(off) + self._b2_to_gate(j)

    def stair_top_index(self, pts):
        """路線中樓梯口那個點的序號（沒有經過樓梯口回 None）。"""
        tops = [self.B1.off(STAIR_U_B1, off) for off in self.LANE_OFF.values()]
        for k, q in enumerate(pts):
            if any(math.dist(q, t) < 1e-6 for t in tops):
                return k
        return None

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
