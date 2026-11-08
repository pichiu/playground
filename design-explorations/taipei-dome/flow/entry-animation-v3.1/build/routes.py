"""版本 3.1 路線幾何：自版本 3 routes.py 改。B1 走廊、樓梯（L 形）兩路不變（A +0.12 白衣、B −0.12 藍衣）。

11/8 現場彩排：西一入口前（樓梯口到入口這段 B2）沒有空間整一個大隊，改用 2c 藍衣集結區（P2–P5）所在的 B2 走廊（西一入口以南、
沿走廊往東到圖面盡頭）當集合區，第一至第九大隊各有一個集合位置，大隊 1 最靠西一入口、大隊 9 最深。
路線：座位 → … → 樓梯 → B2 平台 → 白衣一路、藍衣一路沿走廊外側的「通行帶」往深處走（不碰已整好的隊伍）
→ 集合區盡頭整路左轉 180°（白衣在內圈）→ 白衣散成三路、藍衣散成三路（共六路）→ 沿自己那一路往回走到自己大隊的集合位置。
放行時由集合位置的隊頭一排六人並肩往西一入口走、右轉進門（march.py）。

通行帶與六路的偏移（B2 走廊左法向為正，正 = 場側）：
- 下樓後兩路：A +0.12、B −0.12（同版本 3），到 u BYPASS_U 前漸移到通行帶 A −0.30、B −0.38（白衣仍在行進方向左側）。
- 集合區六路（面向西一入口、往 u 變小的方向走，行進方向左側 = 負偏移）：第 j 路在 −0.2 + 0.08j；j 0–2 白衣、3–5 藍衣，
  第 1 路（j 0、列 6k−5）在行進方向最左側，右轉進門後在北側，與版本 3 門洞裡、北行、進列的左右相同。
圖面 b2Band 只畫到 ±0.2（六路寬）；通行帶在帶外，是假設，要現場確認走廊實際寬度。
"""
import math
from geo import Poly, flat, pairs
import plan

STAIR_U_B1, B2_U_START = 13.15, 1.0      # 樓梯口在 B1 走廊折線的 u；B2 走廊起點 u
LANE_OFF = {'A': 0.12, 'B': -0.12}
STAIR_RUN = 0.62                         # 樓梯直段長（約 4.7 m），由 B1 走廊樓梯口往南直下
LANDING_X, LANDING_END_X = -11.80, -11.31  # B2 平台：路線走到 x −11.80 轉進 B2 走廊；底色帶接到 B2 走廊外緣
STAIR_HALF_W = 0.2                       # 樓梯／平台半寬
GATE_W, GATE_DOORS = 0.95, 4                 # 西一入口：4 扇門，可 12 人並排（約 7.2 m）
GATE_LABEL = '西一入口（4 扇門）'
JOIN_AHEAD = 0.3                         # 從走廊邊併入路時往樓梯方向斜走的距離（u）
LANE_STEP = 0.35                         # lane_run 取點間距
ARRIVE_U = 1.36                          # 下樓後兩路在這個 u 進到 B2 走廊（同版本 3 六條線的起點）
ARRIVE_OFF = {'A': 0.12, 'B': -0.12}     # 下樓後兩路的偏移（白衣靠場側，與樓梯平台的北／南兩路不交叉）
BYPASS_U = 3.6                           # 兩路在這之前移到通行帶（西一入口帶從 u 4.1 起）
BYPASS_OFF = {'A': -0.30, 'B': -0.38}    # 通行帶：集合區六路（±0.2）外側，離最外一路 0.10
GATE_U = 4.57                            # 西一入口中線（gateIn）與 B2 走廊交會的 u
STAGE_HEAD_U = 5.15                      # 大隊 1 集合位置的隊頭（西一入口帶到 u 5.05 為止，入口前留空）
STAGE_TAIL_U = 17.15                     # 大隊 9 集合位置的隊尾最深到這裡（圖面 B2 走廊畫到 u 17.91）
STAGE_START_U = 17.2                     # 六路的起點（散成六路完成）：放行中心線 s = 0
UTURN_U = 17.55                          # 兩路在這裡左轉 180°（白衣內圈）
UTURN_C = -0.17                          # 轉彎圓心的偏移；白衣半徑 0.13（−0.30 → −0.04）、藍衣 0.21（−0.38 → +0.04）
STAGE_STEP = 0.04                        # 集合位置前後間距（圖面點距；只為把九個大隊排進示意圖面，不是現場間距，見 README）
STAGE_GAP_MIN = 0.12                     # 相鄰兩個大隊集合位置之間至少空這麼多（隊尾到下一隊隊頭，扣掉一格）


def stage_off(j):
    """集合區第 j 路在 B2 的偏移：面向西一入口（往 u 變小）時 j 0 在行進方向最左側 = 走廊外側（負偏移）。"""
    return -0.2 + 0.08 * j


def lane_of(j):
    return next(L for L in plan.LANES if j in plan.LANE_J[L])


def lane_run(poly, u0, u1, off, step=LANE_STEP):
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
    return dict(b1Corridor=flat(b1), b2Corridor=flat(b2))


class Geometry:
    def __init__(self, base):
        self.D = base
        M = base['map']
        self.B1, self.B2 = Poly(pairs(M['b1Corridor'])), Poly(pairs(M['b2Corridor']))
        top = self.B1.at(STAIR_U_B1)
        bot = (top[0], top[1] + STAIR_RUN)
        self.STAIR_PTS = [top, bot, (LANDING_X, bot[1])]       # 樓梯口 → 樓梯底（B2）→ 平台東端
        self.LANE_OFF = LANE_OFF
        self._lines = {}
        self.ST_LANE = {o: Poly(miter(self.STAIR_PTS, o)) for o in self.LANE_OFF.values()}   # 樓梯兩路各自的折線

    def _down_stair(self, off):
        lp = self.ST_LANE[off]
        return [self.B1.off(STAIR_U_B1, off)] + poly_between(lp, 0.05, lp.L - 0.05)

    def _pre_b2(self, person):
        """座位 → 走道口 → 接入點 → 自己那一路 → 樓梯（到平台端）。"""
        off = self.LANE_OFF[person['lane']]
        pts = [(person['rest']['X'], person['rest']['Y'])] + [tuple(q) for q in person['approach']]   # 座位 → 走道口 → … → 走廊邊
        u_in = self.B1.proj(pts[-1])[0] + JOIN_AHEAD                                                # 斜向前方併入自己那一路
        pts.append(self.B1.off(u_in, off))
        return pts + lane_run(self.B1, u_in, STAIR_U_B1 - 0.25, off) + self._down_stair(off)

    def bypass(self, lane):
        """平台端 → B2 兩路 → 漸移到通行帶 → 沿通行帶到轉彎起點（不含平台端那一點）。"""
        o0, o1 = ARRIVE_OFF[lane], BYPASS_OFF[lane]
        pts = [self.B2.off(ARRIVE_U, o0)]
        n = max(1, int((BYPASS_U - ARRIVE_U) / LANE_STEP))
        for k in range(1, n + 1):
            f = k / n
            pts.append(self.B2.off(ARRIVE_U + (BYPASS_U - ARRIVE_U) * f, o0 + (o1 - o0) * f))
        return pts + lane_run(self.B2, BYPASS_U, UTURN_U, o1)

    def uturn(self, lane, n=12):
        """集合區盡頭整路左轉 180°：以 B2.off(UTURN_U, UTURN_C) 為圓心，白衣在內圈；回傳轉彎上的點（不含起點）。"""
        c = self.B2.off(UTURN_U, UTURN_C)
        t, nv = self.B2.tan(UTURN_U), self.B2.nrm(UTURN_U)
        r = UTURN_C - BYPASS_OFF[lane]
        return [(c[0] + r * (-nv[0] * math.cos(a) + t[0] * math.sin(a)), c[1] + r * (-nv[1] * math.cos(a) + t[1] * math.sin(a)))
                for a in (math.pi * k / n for k in range(1, n + 1))]

    def entry_route(self, person):
        """座位 → … → 樓梯 → 通行帶 → 盡頭轉彎（到六路起點之前，不含散開那一步）。"""
        return self._pre_b2(person) + self.bypass(person['lane']) + self.uturn(person['lane'])

    def stage_band(self, u0, u1, o0, o1, step=0.3):
        """B2 走廊上 u0–u1、偏移 o0–o1 的帶狀多邊形（圖面用）。"""
        n = max(1, int(abs(u1 - u0) / step))
        us = [u0 + (u1 - u0) * k / n for k in range(n + 1)]
        return [self.B2.off(u, o1) for u in us] + [self.B2.off(u, o0) for u in reversed(us)]

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
        return dict(doors=doors, band=flat(band))
