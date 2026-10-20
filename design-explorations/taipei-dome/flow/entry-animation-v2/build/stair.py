"""樓梯 L 形與西一入口的圖面（與 ../../entry-animation/build/routes.py 同一套幾何）。

企劃圖 6白 的綠色 L 形：直段是樓梯（順著 B1 走廊往南直下），橫段是樓梯下的 B2 平台（往東接 B2 走廊）。
西一入口 4 扇門，可 12 人並排；中線沿用原版的 gateIn。
"""
import math
from geo import Poly, pairs

STAIR_RUN = 0.62                         # 樓梯直段長（約 4.7 m），由 B1 走廊樓梯口往南直下
LANDING_X, LANDING_END_X = -11.80, -11.31  # B2 平台：路線走到 x −11.80 轉進 B2 走廊；底色帶接到 B2 走廊外緣
STAIR_HALF_W = 0.2
GATE_W, GATE_DOORS = 0.95, 4                 # 4 扇門，可 12 人並排（約 7.2 m）
GATE_LABEL = '西一入口（4 扇門）'


def miter(pts, o):
    """折線往左法向（畫面 y 向下）平移 o，轉角取斜接點。"""
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


def stair_pts(B1, u_top):
    top = B1.at(u_top)
    bot = (top[0], top[1] + STAIR_RUN)
    return [top, bot, (LANDING_X, bot[1])]


def lane_polys(pts, offsets):
    return {o: Poly(miter(pts, o)) for o in offsets}


def trim_corridors(B1, B2, u_top, y_landing):
    """圖面用的走廊線：B1 畫到樓梯口為止、B2 從平台那一排開始（路線幾何仍用完整折線）。"""
    u2 = B2.proj((B2.at(0)[0], y_landing))[0]
    b1 = [q for q, c in zip(B1.p, B1.cum) if c < u_top] + [B1.at(u_top)]
    b2 = [B2.at(u2)] + [q for q, c in zip(B2.p, B2.cum) if c > u2]
    return dict(b1Corridor=[round(v, 3) for q in b1 for v in q], b2Corridor=[round(v, 3) for q in b2 for v in q])


def stair_map(pts):
    top, bot, _ = pts
    band = [top, bot, (LANDING_END_X, bot[1])]
    ring = miter(band, STAIR_HALF_W) + miter(band, -STAIR_HALF_W)[::-1]
    n = 8
    treads = [[round(top[0] - STAIR_HALF_W, 3), round(top[1] + STAIR_RUN * k / n, 3), round(top[0] + STAIR_HALF_W, 3), round(top[1] + STAIR_RUN * k / n, 3)]
              for k in range(1, n)]
    flat = lambda q: [round(v, 3) for p in q for v in p]
    return dict(stair=flat(pts), stairBand=flat(ring), stairTreads=treads)


def gate_map(gate_in):
    a, b = pairs(gate_in)
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
