"""版本 3 路線幾何（spec §3.5），自 2c routes.py 精簡。

只留一條路：座位 → 走道口 → 走廊邊 → 斜向前方併入自己那一路 → B1 → 樓梯（L 形）→ B2 側移到自己那條西一入口線 → 收攏點。
沒有集結區、格位、死巷、遞補。兩路偏移 A +0.12（白衣、靠看台）、B −0.12（藍衣、外側）。
"""
import math
from geo import Poly, pairs

STAIR_U_B1, B2_U_START = 13.15, 1.0      # 樓梯口在 B1 走廊折線的 u；B2 走廊起點 u
LANE_OFF = {'A': 0.12, 'B': -0.12}
STAIR_RUN = 0.62                         # 樓梯直段長（約 4.7 m），由 B1 走廊樓梯口往南直下
LANDING_X, LANDING_END_X = -11.80, -11.31  # B2 平台：路線走到 x −11.80 轉進 B2 走廊；底色帶接到 B2 走廊外緣
STAIR_HALF_W = 0.2                       # 樓梯／平台半寬
GATE_W, GATE_DOORS = 0.95, 4                 # 西一入口：4 扇門，可 12 人並排（約 7.2 m）
GATE_LABEL = '西一入口（4 扇門）'
JOIN_AHEAD = 0.3                         # 從走廊邊併入路時往樓梯方向斜走的距離（u）


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
    """圖面用的走廊線：B1 畫到樓梯口為止、B2 從平台那一排開始（路線幾何仍用完整折線，u 不變）。"""
    u2 = B2.proj((B2.at(0)[0], y_landing))[0]
    b1 = [q for q, c in zip(B1.p, B1.cum) if c < u_top] + [B1.at(u_top)]
    b2 = [B2.at(u2)] + [q for q, c in zip(B2.p, B2.cum) if c > u2]
    return dict(b1Corridor=[round(v, 3) for q in b1 for v in q], b2Corridor=[round(v, 3) for q in b2 for v in q])


class Geometry:
    def __init__(self, base):
        self.D = base
        M = base['map']
        self.B1, self.B2 = Poly(pairs(M['b1Corridor'])), Poly(pairs(M['b2Corridor']))
        top = self.B1.at(STAIR_U_B1)
        bot = (top[0], top[1] + STAIR_RUN)
        self.STAIR_PTS = [top, bot, (LANDING_X, bot[1])]       # 樓梯口 → 樓梯底（B2）→ 平台東端
        self.LANE_OFF = dict(LANE_OFF)
        self.ST_LANE = {o: Poly(miter(self.STAIR_PTS, o)) for o in self.LANE_OFF.values()}   # 樓梯兩路各自的折線
        self.GATE_PTS, self.GATE_DIR = {}, {}                   # 西一入口六路收攏點：版本 1 大隊 1 過西一入口的點；GATE_DIR 是該點之後場內線的方向
        for p in base['persons']:
            if p['dadui'] == 1 and p['laneIdx'] not in self.GATE_PTS:
                k = next(i for i, q in enumerate(p['path']) if abs(q[2] - p['t']['gate']) < 1e-6)
                a, b = p['path'][k], p['path'][k + 1]
                d = math.dist(a[:2], b[:2])
                self.GATE_PTS[p['laneIdx']] = (a[0], a[1])
                self.GATE_DIR[p['laneIdx']] = ((b[0] - a[0]) / d, (b[1] - a[1]) / d)

    def _down_stair(self, off):
        lp = self.ST_LANE[off]
        return [self.B1.off(STAIR_U_B1, off)] + poly_between(lp, 0.05, lp.L - 0.05)

    def _b2_to_gate(self, j):
        return lane_run(self.B2, B2_U_START, 4.2, 0.2 - 0.08 * j) + [self.GATE_PTS[j]]

    def arrival_route(self, person):
        """座位 → 走道口 → 接入點 → 自己那一路 → 樓梯 → B2 側移到第 j 條線 → 西一入口收攏點。"""
        off = self.LANE_OFF[person['lane']]
        pts = [(person['rest']['X'], person['rest']['Y'])] + [tuple(q) for q in person['approach']]   # 座位 → 走道口 → … → 走廊邊
        u_in = self.B1.proj(pts[-1])[0] + JOIN_AHEAD                                                # 斜向前方併入自己那一路
        pts.append(self.B1.off(u_in, off))
        return pts + lane_run(self.B1, u_in, STAIR_U_B1 - 0.25, off) + self._down_stair(off) + self._b2_to_gate(person['gateLane'])

    def stair_top_index(self, pts):
        """路線中樓梯口那個點的序號（沒有經過樓梯口回 None）。"""
        tops = [self.B1.off(STAIR_U_B1, off) for off in self.LANE_OFF.values()]
        for k, q in enumerate(pts):
            if any(math.dist(q, t) < 1e-6 for t in tops):
                return k
        return None

    # ---------- 圖面 ----------
    def gate_lanes_map(self):
        """下樓後到門前的六條線：從樓梯平台（A／B 路各自的端點）側移到第 j 條線，沿 B2 走到西一入口收攏點。j 0–2 白、3–5 藍。"""
        out = []
        for j in range(6):
            lp = self.ST_LANE[self.LANE_OFF['A' if j < 3 else 'B']]
            pts = [lp.at(lp.L - 0.05)] + self._b2_to_gate(j)
            out.append([round(v, 3) for q in pts for v in q])
        return out

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
