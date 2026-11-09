"""版本 3.1 檢核（自版本 3 spec §4 改：門前隊伍、迴廊候隊換成 B2 集合區）。build.py 也用 check_all 寫 meta.checks。

用法: python3 check.py ../data.json   → 印表；重算與 meta.checks 比對；未通過 exit 1

所有數字都從 persons / restSeats 重算；data.json 裡 exits 的 used / capacity / order 只拿來比對，不信任。
"""
import bisect
import collections
import json
import math
import sys

import numpy as np

import build
import plan
import routes
from collide import collisions, seated_hits
from geo import Poly, pairs

GAP_MIN, GAP_MAX = round(build.HEADWAY - 0.15, 3), round(build.HEADWAY + 0.15, 3)   # 樓梯口節拍容許 ± 0.15（避撞平移）
BOUNDARY_MAX = 7.0                 # 大隊交界的外框；每一處交界另外要等於規則值 HEADWAY×人數差 + HEADWAY + DADUI_GAP（± RULE_SLACK），那才是緊的檢核（現在最多約 3.6 秒）
GATE_GAP_MIN = round(build.RANK_GAP - 0.01, 3)   # 西一入口每條線：一排接一排（整排並肩段所有排同一個速度剖面，不再平移；容許四捨五入）
GATE_GAP_MAX = round(build.RANK_GAP + 0.6, 3)    # 同一大隊內：隊伍不停就是 RANK_GAP，容許避撞平移與短暫停住
RULE_SLACK = 0.4                   # 交界規則值 = 節拍 ×（兩路該大隊人數差）+ 節拍 + 大隊空檔（build.HEADWAY、build.DADUI_GAP），容許錯開與避撞平移 0.4（spec §4）
GATE_BOUNDARY_MAX = 16.0           # 西一入口每條線兩個大隊之間的空檔上限（沿用版本 3 的外框）；11/9 起九隊站齊才連續放行，實際空檔只有約 RANK_GAP
SHIFT_TOL = 0.01                   # 同一排離開隊頭的時刻差、排距的容許（避撞不再平移時間線，只容許四捨五入；舊版 0.16）
WAIT_SLACK = 0.05                  # 步速段的時間不得超過路程 / 步速 + 這麼多（座標與時刻四捨五入的誤差）
POPULATION = 1609
COMPARED = ('collisions', 'nesting', 'assignment', 'routes', 'continuity', 'pace', 'ranks', 'assembly', 'pillars', 'formation', 'wheel', 'laneMap', 'geometry', 'align',
            'seats', 'capacity')   # 與 meta.checks 逐項比對的鍵
# 整排並肩（wheel turn）：從 t.enter 到大隊分出（t.split），每 FORM_DT 秒取樣
FORM_DT = 0.1
ANGLE_MAX = 3.0                    # 排的偏離橫排角度（度）
SPACING_TOL = 0.01                 # 同排相鄰兩人距離 − 設計間距
CENTER_TOL = 0.01                  # 排的中心離中心線
TRACK_TOL = 0.004                  # 每人路徑點離自己那條平移線（座標四捨五入到 0.001、路徑簡化容許 0.002）
SPEED_EPS = 1e-6                   # 中心線取樣（9 位小數）重算的外圈速度容許
PATH_SPEED_ABS = 0.004             # 路徑（3 位小數）逐段速度：路程 ≤ V·Δt + 這麼多（四捨五入誤差）
ROW_TOL = 0.005                    # 進列時 Y 與 field.Y
STAGE_OFF_TOL = 0.02               # 集合區六路的偏移（B2 走廊折線在 u 6.9（截過的 u）有一個折角，中心線倒圓角後離折線最多約 0.02）
STAGE_MIN = 0.15                   # 離舞台線稿（base.stage 中 X < −4.5 的部分）
STAGE_MIN_NORTH = build.march.STAGE_MIN_NORTH   # 0.10；11/9 例外：北行改走第 4–9 排地標後，第 1 路那條北行線（x = map.march 北行直線的 lane 0）在 y ≈ 3.1
                                   # 離舞台東側階梯 0.111（約 0.84 m），不跨階梯線（MAX_STEPS 仍是 0）；只有在那條線上的點用這個門檻，其餘仍 ≥ STAGE_MIN
NORTH_LINE_TOL = build.march.GAP_H # 第 1 路北行線兩側半格（到第 4、5 排座位欄為止）：含第 1 路在階梯旁轉進列的彎；與 march.tail 產生時的檢查同一條帶
STAGE_X = -4.5
SUBDIV = 0.02                      # 幾何避讓：路徑每 0.02 細分
STAIR_BOX = (-5.6, -4.3, 0.8, 4.5) # 數「跨過幾條階梯線」的範圍（x0, x1, y0, y1）：場內舞台東緣這一帶
MAX_STEPS = 0                      # 最多跨過幾條階梯線（上幾階）：北行走第 4–9 排地標的直線，不上階梯
ALIGN_TOL = 0.002                  # 第 9 排對齊：停的位置、停的起訖（路徑存三位小數）
RELEASE_TOL = 0.01                 # 最後一位隊頭到對齊點的時刻與出發時刻差


def _gaps(ps, tkey, group_key, queued=lambda p: False):
    """依序號排好後的拍距：群內 / 交界分開統計；順序必須單調。queued(p) 為真的人（在這一點之前就開始排隊、走走停停），
    他和前後兩人的拍距不算進統計（只驗順序），另外列出對數。"""
    within, boundary, order_ok, skipped = [], [], True, 0
    for a, b in zip(ps, ps[1:]):
        gap = b['t'][tkey] - a['t'][tkey]
        if gap < -1e-9:
            order_ok = False
        if queued(a) or queued(b):
            skipped += 1
            continue
        (within if a[group_key] == b[group_key] else boundary).append(gap)
    return dict(n=len(ps), minGap=round(min(within + boundary), 3) if within + boundary else None,
                maxGapWithin=round(max(within), 3) if within else 0.0,
                maxGapBoundary=round(max(boundary), 3) if boundary else 0.0, orderOk=order_ok, queuedPairs=skipped)


def _seg_cross(p1, p2, p3, p4):
    """兩線段是否真正相交（端點相觸、共線重疊不算）。"""
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    d1, d2, d3, d4 = cross(p3, p4, p1), cross(p3, p4, p2), cross(p1, p2, p3), cross(p1, p2, p4)
    return (d1 > 0) != (d2 > 0) and (d3 > 0) != (d4 > 0) and 0 not in (d1, d2, d3, d4)


def _poly_cross(a, b):
    return sum(1 for s1 in zip(a, a[1:]) for s2 in zip(b, b[1:]) if _seg_cross(*s1, *s2))


def lane_crossings(data):
    """純幾何、不看時間：兩條隊伍的線交叉，再怎麼錯開都是人穿過人。
    B2：每大隊六列頭一位（各列 gateIdx 最小者），從進 B2 走廊（u ≥ 0.9、離中線 < 0.3）到過西一入口後 3 秒，兩兩不相交。
    B1：每大隊兩路頭一位，從離座到樓梯口，不相交。"""
    B2 = Poly(pairs(data['map']['b2Corridor']))
    heads = {}
    for p in data['persons']:
        k = (p['dadui'], p['gateLane'])
        if k not in heads or p['gateIdx'] < heads[k]['gateIdx']:
            heads[k] = p
    lane_heads = {}
    for p in data['persons']:
        k = (p['dadui'], p['lane'])
        if k not in lane_heads or p['laneIdx'] < lane_heads[k]['laneIdx']:
            lane_heads[k] = p

    def b2_part(p):
        out, inside = [], False
        for q in p['path']:
            if q[2] > p['t']['gate'] + 3 + 1e-6:
                break
            if not inside:
                u, _, dist = B2.proj(q[:2])
                inside = q[2] >= p['t']['stair'] and u >= 0.9 and dist < 0.3
            if inside:
                out.append((q[0], q[1]))
        return out

    def b1_part(p):
        return [(q[0], q[1]) for q in p['path'] if q[2] <= p['t']['stair'] + 1e-6]

    n, examples = 0, []
    for d in range(1, 10):
        parts = {j: b2_part(heads[(d, j)]) for j in range(6) if (d, j) in heads}
        for i in parts:
            for j in parts:
                if i < j:
                    c = _poly_cross(parts[i], parts[j])
                    if c:
                        n += c
                        examples.append(dict(phase='B2', dadui=d, lines=[i, j], who=[heads[(d, i)]['id'], heads[(d, j)]['id']]))
        if (d, 'A') in lane_heads and (d, 'B') in lane_heads:
            c = _poly_cross(b1_part(lane_heads[(d, 'A')]), b1_part(lane_heads[(d, 'B')]))
            if c:
                n += c
                examples.append(dict(phase='B1', dadui=d, lines=['A', 'B'], who=[lane_heads[(d, 'A')]['id'], lane_heads[(d, 'B')]['id']]))
    return dict(crossings=n, examples=examples[:4])


def _wall_time(a, wall):
    """路徑第一次穿過全壘打牆的時刻（沒有穿過回 None）。"""
    for q0, q1 in zip(a, a[1:]):
        for w0, w1 in zip(wall, wall[1:]):
            f = _seg_frac(q0, q1, w0, w1)
            if f is not None:
                return q0[2] + (q1[2] - q0[2]) * f
    return None


def _seg_frac(p1, p2, p3, p4):
    d = (p2[0] - p1[0]) * (p4[1] - p3[1]) - (p2[1] - p1[1]) * (p4[0] - p3[0])
    if abs(d) < 1e-12:
        return None
    t = ((p3[0] - p1[0]) * (p4[1] - p3[1]) - (p3[1] - p1[1]) * (p4[0] - p3[0])) / d
    u = ((p3[0] - p1[0]) * (p2[1] - p1[1]) - (p3[1] - p1[1]) * (p2[0] - p1[0])) / d
    return t if 0 <= t <= 1 and 0 <= u <= 1 else None


class _Track:
    """在路徑上依時間取位置（二分搜尋）。"""

    def __init__(self, path):
        self.a = path
        self.t = [q[2] for q in path]

    def at(self, t):
        a = self.a
        k = max(0, min(len(a) - 2, bisect.bisect_right(self.t, t) - 1))
        q0, q1 = a[k], a[k + 1]
        f = max(0.0, min(1.0, (t - q0[2]) / (q1[2] - q0[2]))) if q1[2] > q0[2] else 0.0
        return (q0[0] + (q1[0] - q0[0]) * f, q0[1] + (q1[1] - q0[1]) * f)


class _March:
    """data.json map.march：中心線取樣（τ 相對 t.enter）。"""

    def __init__(self, m):
        self.m = m
        self.tau = m['tau']

    def at(self, tau):
        m, T = self.m, self.tau
        k = max(0, min(len(T) - 2, bisect.bisect_right(T, tau) - 1))
        f = max(0.0, min(1.0, (tau - T[k]) / (T[k + 1] - T[k]))) if T[k + 1] > T[k] else 0.0
        g = lambda key: m[key][k] + (m[key][k + 1] - m[key][k]) * f
        tx, ty = g('tx'), g('ty')
        n = math.hypot(tx, ty)
        return (g('x'), g('y')), (tx / n, ty / n), g('sp')

    def lanes(self, k):
        m = self.m
        return [(m['x'][k] + m['ty'][k] * (2.5 - j) * m['sp'][k], m['y'][k] - m['tx'][k] * (2.5 - j) * m['sp'][k]) for j in range(6)]


def _tau(p, t, ht):
    """t 對應中心線上的 τ（相對中心線起點 s = 0）：τ = t − t.enter + headTau[大隊]（離開自己集合位置隊頭時是 headTau）。
    只對還沒進第 9 排對齊排隊時段（t ≤ t.holdStart）的時刻成立；排隊時走走停停，τ 由路徑本身決定，呼叫端要先排除。"""
    return t - p['t']['enter'] + ht[p['dadui']]


def _free_until(p):
    """這個人照名目速度剖面走到哪個時刻（第 9 排對齊的排隊時段開始；沒有排隊就是無限）。"""
    return p['t'].get('holdStart', math.inf)


def _in_hold(p, q0, q1):
    """q0 → q1 是不是在這個人的排隊時段（t.holdStart → t.holdEnd）裡：那段可以停、可以慢，不快過步速。"""
    return q0[2] >= _free_until(p) - ALIGN_TOL and q1[2] <= p['t'].get('holdEnd', -1) + ALIGN_TOL


def _head_tau(data):
    """各大隊集合位置隊頭的中心線 τ（map.march.headTau）。"""
    return {int(d): v for d, v in data['map']['march']['headTau'].items()}


def assembly(data):
    """B2 集合區（版本 3.1）：
    - 九個大隊各有一個集合位置：沿 B2 走廊大隊 1 最靠西一入口、大隊 9 最深（隊頭 u 隨大隊遞增）；相鄰兩個位置不重疊（隊尾 u < 下一隊隊頭 u）；
      全部在西一入口帶之外（隊頭 u ≥ gateClear 上緣）、離樓梯口遠（> stairClear 上緣）。
    - 每人站定（t.assembly）的位置：在自己大隊的集合位置內（u 在隊頭隊尾之間）、偏移 = 自己那一路（−0.2 + 0.08 j，± STAGE_OFF_TOL）、
      在自己那一路的第 stageRank 格（第 0 格在隊頭，相鄰兩格相距約一格）。
    - 站定後到放行（t.assembly → t.enter）一直在自己大隊的集合位置內、自己那一路上。
    - 下樓到站定之間不停（含樓梯上）：樓梯口 → 站定的時間 = 路程 / 步速（± WAIT_SLACK）。樓梯上候隊時間記為 stairWait。
    - 兩路在 B2：西一入口帶到集合區這一段，下樓後走在通行帶（偏移 ≤ −0.26）；要進六路帶（迴轉、散開）只能在自己那一格的深處（u ≥ 自己格位），
      所以不會從已站好的人旁邊切進去（11/9 起每人在自己那一排附近迴轉，不再走到集合區盡頭）。
    - 放行（11/9）：九個大隊全部站定後才有人離開隊頭；大隊 d + 1 第一排離開隊頭時，大隊 d 已全部離開隊頭。"""
    S = data['map']['staging']
    ht = _head_tau(data)
    B2 = Poly(pairs(data['map']['b2Corridor']))
    V = data['meta']['speedUnitPerSec']
    bl = {b['dadui']: b for b in S['blocks']}
    bad = []
    ds = sorted(bl)
    for a, b in zip(ds, ds[1:]):
        if not bl[a]['uHead'] < bl[a]['uTail'] < bl[b]['uHead'] < bl[b]['uTail']:
            bad.append(dict(why='block order', dadui=[a, b]))
    if bl[ds[0]]['uHead'] < S['gateClear'][1] - 1e-6 or bl[ds[0]]['uHead'] <= S['stairClear'][1]:
        bad.append(dict(why='gate clear'))
    step = S['step']
    max_wait, bypass_bad = 0.0, 0
    slots = collections.defaultdict(list)
    for p in data['persons']:
        t, a, d, j = p['t'], p['path'], p['dadui'], p['gateLane']
        b = bl[d]
        lo, hi = b['uHead'] - 0.01, b['uTail'] + 0.01
        off = S['laneOff'][j]
        ka = next((i for i, q in enumerate(a) if abs(q[2] - t['assembly']) < 2e-3), None)
        ke = next((i for i, q in enumerate(a) if abs(q[2] - t['enter']) < 2e-3), None)
        ks = next((i for i, q in enumerate(a) if q[2] >= t['stair'] - 1e-6), None)
        if ka is None or ke is None or ks is None:
            bad.append(dict(who=p['id'], why='times'))
            continue
        u0, o0, _ = B2.proj(a[ka][:2])
        slots[(d, j)].append((p['stageRank'], a[ka][:2]))
        if not lo <= u0 <= hi or abs(o0 - off) > STAGE_OFF_TOL:
            bad.append(dict(who=p['id'], why='slot', u=round(u0, 3), off=round(o0, 3)))
            continue
        for q in a[ka:ke + 1]:
            u, o, _ = B2.proj(q[:2])
            if not lo <= u <= hi or abs(o - off) > STAGE_OFF_TOL:
                bad.append(dict(who=p['id'], why='left block'))
                break
        w = (a[ka][2] - a[ks][2]) - build.cum([q[:2] for q in a[ks:ka + 1]])[-1] / V
        max_wait = max(max_wait, w)
        if w > WAIT_SLACK:
            bad.append(dict(who=p['id'], why='waited before slot', w=round(w, 3)))
        for q in a[ks:ka]:                              # 到站定之前：在入口帶到集合區這一段，只能在通行帶上走；要進六路帶（迴轉、散開）一定在自己那一格的深處
            u, o, _ = B2.proj(q[:2])
            if S['gateClear'][0] <= u <= S['uturnU'] + 0.3 and o > -0.26 and u < u0 - 0.01:
                bypass_bad += 1
                bad.append(dict(who=p['id'], why='bypass', u=round(u, 3), off=round(o, 3)))
                break
    for (d, j), sl in slots.items():                    # 第 0 格在隊頭；同一路相鄰兩格相距一格（彎道上弦長與弧長差，容許 0.8–1.25 倍）
        sl.sort()
        if sl[0][0] == 0 and math.dist(sl[0][1], bl[d]['heads'][j]) > 0.01:
            bad.append(dict(why='head slot', dadui=d, lane=j))
        for (r0_, q0), (r1_, q1) in zip(sl, sl[1:]):
            if not 0.8 * step * (r1_ - r0_) <= math.dist(q0, q1) <= 1.25 * step * (r1_ - r0_) + 1e-3:
                bad.append(dict(why='slot spacing', dadui=d, lane=j, ranks=[r0_, r1_]))
                break
    if min(p['t']['enter'] for p in data['persons']) < max(p['t']['assembly'] for p in data['persons']) - 1e-6:
        bad.append(dict(why='released before all nine staged'))
    for a_, b_ in zip(ds, ds[1:]):
        last = max(p['t']['enter'] for p in data['persons'] if p['dadui'] == a_)
        first = min(p['t']['enter'] for p in data['persons'] if p['dadui'] == b_)
        gref = lambda d, t: t + ht[ds[0]] - ht[d]
        if gref(b_, first) < gref(a_, last) + build.RANK_GAP - SHIFT_TOL:
            bad.append(dict(why='release order', dadui=b_))
    occ = {}
    for d in ds:
        ps = [p for p in data['persons'] if p['dadui'] == d]
        occ[str(d)] = dict(uHead=bl[d]['uHead'], uTail=bl[d]['uTail'], ranks=bl[d]['ranks'], firstIn=round(min(p['t']['assembly'] for p in ps), 2),
                           full=round(max(p['t']['assembly'] for p in ps), 2), go=round(min(p['t']['enter'] for p in ps), 2), out=round(max(p['t']['enter'] for p in ps), 2))
    t0_, t1_ = min(v['firstIn'] for v in occ.values()), max(v['out'] for v in occ.values())
    peak = max(sum(1 for v in occ.values() if v['firstIn'] <= t0_ + k * 0.5 < v['out']) for k in range(int((t1_ - t0_) / 0.5) + 1))   # 動畫時間每 0.5 秒取樣
    return dict(blocks=len(bl), gap=S['gap'], step=step, maxWaitBeforeSlot=round(max_wait, 3), bypassViolations=bypass_bad,
                peakDaduiInArea=peak, occupancy=occ, violations=len(bad), examples=bad[:3])


def pillars(data):
    """圖面柱位（map.pillars，版本 1 的「場邊柱」示意）與路徑的衝突：不算進 ok，列出來給現場確認。
    每人路徑任一段離柱心小於柱半徑就算；分「站在柱上」（集合位置格位）與「走過柱子」。
    map.pillarsAssumedAbsent（假設不存在的柱，例如 L7、L8）照樣算，放在 assumedAbsent：若現場其實有柱，會碰到這些人。"""
    absent_ids = {c['id'] for c in data['map'].get('pillarsAssumedAbsent', [])}
    pl = data['map']['pillars'] + data['map'].get('pillarsAssumedAbsent', [])
    hit, stand = collections.defaultdict(set), collections.defaultdict(set)
    for p in data['persons']:
        a = p['path']
        ka = next((i for i, q in enumerate(a) if abs(q[2] - p['t']['assembly']) < 2e-3), None)
        for c in pl:
            if ka is not None and math.dist(a[ka][:2], (c['X'], c['Y'])) < c['r']:
                stand[c['id']].add(p['id'])
        A = np.array(a, dtype=float)[:, :2]
        S0, D = A[:-1], A[1:] - A[:-1]
        L2 = np.maximum((D * D).sum(1), 1e-12)
        for c in pl:                                    # 柱心到每一段路徑的最短距離（向量化）
            Q = np.array((c['X'], c['Y']))
            f = np.clip(((Q - S0) * D).sum(1) / L2, 0, 1)
            if (np.hypot(*(S0 + D * f[:, None] - Q).T) < c['r']).any():
                hit[c['id']].add(p['id'])
    B2 = Poly(pairs(data['map']['b2Corridor']))
    dad = {p['id']: p['dadui'] for p in data['persons']}
    where, assumed = {}, {}
    for c in pl:
        if c['id'] in hit:
            u, o, _ = B2.proj((c['X'], c['Y']))
            (assumed if c['id'] in absent_ids else where)[c['id']] = dict(X=c['X'], Y=c['Y'], u=round(u, 3), off=round(o, 3), persons=len(hit[c['id']]), standing=len(stand[c['id']]),
                                  daduis=sorted({dad[i] for i in stand[c['id']]}))
    real = [hit[k] for k in where]
    return dict(conflicts=len(where), persons=len(set().union(*real)) if real else 0, where=where, assumedAbsent=assumed)


def formation(data, by_rank):
    """並肩：每一排從 t.enter（離開集合位置隊頭）到本大隊分出（t.split；同一排有人在分出前就停的，到他停下為止），
    每 FORM_DT 秒取樣（τ = t − t.enter + headTau[大隊]）：
    偏離橫排角度（最西到最東那兩人的連線與行進方向法線的夾角）≤ ANGLE_MAX；同排相鄰兩人距離 − 設計間距 ≤ SPACING_TOL
    （中間有空位就除以差幾路）；排的中心（每人扣掉自己的設計偏移後平均）離中心線 ≤ CENTER_TOL。另外每人路徑點（到自己分出為止，含停住的那一點）
    離自己那條平移線 ≤ TRACK_TOL（τ 扣掉停住的時間）。"""
    M = _March(data['map']['march'])
    split = data['map']['march']['split']
    ht = _head_tau(data)
    tr = {p['id']: _Track(p['path']) for p in data['persons']}
    worst = dict(angle=0.0, spacing=0.0, center=0.0, track=0.0)
    bad, n_samp = [], 0
    for r, ps in by_rank.items():
        ps = sorted(ps, key=lambda p: p['gateLane'])
        t0 = ps[0]['t']['enter']
        t1 = min(p['t']['split'] for p in ps)
        if all(_free_until(p) >= p['t']['split'] - 1e-6 for p in ps) and abs(_tau(ps[0], t1, ht) - split[str(ps[0]['dadui'])]) > 2e-3:
            bad.append(dict(rank=r, why='split'))
        t1 = min([t1] + [_free_until(p) for p in ps])     # 有人在分出前就開始排隊（走走停停）：並肩只驗到他開始排隊
        k = 0
        while t0 + k * FORM_DT < t1 - 1e-9:
            tt = t0 + k * FORM_DT
            k += 1
            n_samp += 1
            c, (tx, ty), sp = M.at(_tau(ps[0], tt, ht))
            nx, ny = ty, -tx
            pos = [tr[p['id']].at(tt) for p in ps]
            js = [p['gateLane'] for p in ps]
            cx = sum(q[0] - nx * (2.5 - j) * sp for q, j in zip(pos, js)) / len(ps)
            cy = sum(q[1] - ny * (2.5 - j) * sp for q, j in zip(pos, js)) / len(ps)
            e = dict(center=math.dist((cx, cy), c), angle=0.0, spacing=0.0)
            if len(ps) > 1:
                v = (pos[-1][0] - pos[0][0], pos[-1][1] - pos[0][1])
                e['angle'] = math.degrees(math.atan2(abs(v[0] * tx + v[1] * ty), abs(v[0] * nx + v[1] * ny)))
                e['spacing'] = max(abs(math.dist(a, b) / (jb - ja) - sp) for a, b, ja, jb in zip(pos, pos[1:], js, js[1:]))
            for key in ('angle', 'spacing', 'center'):
                worst[key] = max(worst[key], e[key])
            if e['angle'] > ANGLE_MAX or e['spacing'] > SPACING_TOL or e['center'] > CENTER_TOL:
                bad.append(dict(rank=r, t=round(tt, 2), **{k_: round(v_, 4) for k_, v_ in e.items()}))
        for p in ps:                                     # 路徑點都在自己那條平移線上
            for q in p['path']:
                if t0 - 1e-9 <= q[2] <= min(p['t']['split'], _free_until(p)) + 1e-9:
                    c, (tx, ty), sp = M.at(_tau(p, q[2], ht))
                    o = (2.5 - p['gateLane']) * sp
                    d = math.dist(q[:2], (c[0] + ty * o, c[1] - tx * o))
                    worst['track'] = max(worst['track'], d)
                    if d > TRACK_TOL:
                        bad.append(dict(rank=r, who=p['id'], track=round(d, 4)))
                        break
    return dict(samples=n_samp, maxAngle=round(worst['angle'], 3), maxSpacingErr=round(worst['spacing'], 4), maxCenterOff=round(worst['center'], 4),
                maxTrackDev=round(worst['track'], 4), violations=len(bad), examples=bad[:3])


def wheel(data):
    """整排轉彎（由 map.march 的中心線取樣重算，六條線 = 中心線往左平移 (2.5 − j) × 間距）：
    任何一段六條線都不快過步速（外圈 ≤ V + SPEED_EPS）；每個轉彎內，內圈半徑 ≥ innerMin、內圈位移沿行進方向單調前進（不倒退、不原地轉）；
    直線段（間距不變）六人都是步速。"""
    m = data['map']['march']
    M = _March(m)
    V = m['speed']
    T = m['tau']
    vmax, inner_min_v, bad = 0.0, 9.0, []
    prev = M.lanes(0)
    for k in range(1, len(T)):
        cur = M.lanes(k)
        dt = T[k] - T[k - 1]
        sp = [math.dist(a, b) / dt for a, b in zip(prev, cur)]
        vmax = max(vmax, max(sp))
        if max(sp) > V + SPEED_EPS:
            bad.append(dict(kind='speed', tau=round(T[k], 3), v=round(max(sp), 7)))
        prev = cur
    turns = []
    for t0, t1, R, left in m['arcs']:
        jin = 0 if left else 5                           # 左轉內圈是 lane 0（左側），右轉是 lane 5
        ks = [k for k, t in enumerate(T) if t0 - 1e-9 <= t <= t1 + 1e-9]
        sp_max = max(m['sp'][k] for k in ks)
        r_in = R - 2.5 * sp_max
        outer_v, inner_v = 0.0, 9.0
        for k0, k1 in zip(ks, ks[1:]):
            a, b = M.lanes(k0), M.lanes(k1)
            dt = T[k1] - T[k0]
            tx, ty = m['tx'][k0], m['ty'][k0]
            fwd = (b[jin][0] - a[jin][0]) * tx + (b[jin][1] - a[jin][1]) * ty
            outer_v = max(outer_v, max(math.dist(p, q) / dt for p, q in zip(a, b)))
            inner_v = min(inner_v, fwd / dt)
            if fwd <= 0:
                bad.append(dict(kind='inner', tau=round(T[k1], 3)))
        inner_min_v = min(inner_min_v, inner_v)
        if r_in < m['innerMin'] - 1e-9:
            bad.append(dict(kind='radius', tau=round(t0, 3), inner=round(r_in, 4)))
        turns.append(dict(tau=[round(t0, 3), round(t1, 3)], R=round(R, 3), left=left, innerR=round(r_in, 3), outerV=round(outer_v, 6), innerV=round(inner_v, 4)))
    return dict(turns=len(turns), maxSpeed=round(vmax, 7), minInnerSpeed=round(inner_min_v, 4), minInnerR=round(min(t['innerR'] for t in turns), 3),
                detail=turns, violations=len(bad), examples=bad[:3])


def lane_map(data, by_rank):
    """lane 對應：lie = 6(大隊 − 1) + gateLane + 1（lane 0 對到大隊第一列、Y 最小）；分出時同一排 lane 0 在行進方向最左、依序往右；
    分出後每人進到自己那一列（|Y − field.Y| ≤ ROW_TOL）之後一直在那一列上、朝座位單調前進（座位在東側的右轉沿那一列往東；
    座位在西側的沿那一列南邊半格的列間空隙往西、到座位正南方才往北半格，所以進到那一列時就已經在座位上），到 field 停下，而且不越過自己那一列往北。"""
    M = _March(data['map']['march'])
    ht = _head_tau(data)
    bad, worst_row = [], 0.0
    for p in data['persons']:
        if p['lie'] != 6 * (p['dadui'] - 1) + p['gateLane'] + 1:
            bad.append(dict(who=p['id'], why='lie'))
            continue
        fy, fx = p['field']['Y'], p['field']['X']
        tail = [q for q in p['path'] if q[2] >= p['t']['split'] - 1e-6]
        k = next((i for i, q in enumerate(tail) if abs(q[1] - fy) <= ROW_TOL), None)
        if k is None or math.dist(tail[-1][:2], (fx, fy)) > ROW_TOL or min(q[1] for q in tail) < fy - ROW_TOL:
            bad.append(dict(who=p['id'], why='row'))
            continue
        row = tail[k:]
        worst_row = max(worst_row, max(abs(q[1] - fy) for q in row))
        toward = all(abs(fx - b[0]) <= abs(fx - a[0]) + 1e-9 for a, b in zip(row, row[1:]))
        if any(abs(q[1] - fy) > ROW_TOL for q in row) or not toward:
            bad.append(dict(who=p['id'], why='east'))
    for r, ps in by_rank.items():
        if len(ps) < 2:
            continue
        ps = sorted(ps, key=lambda p: p['gateLane'])
        t = min(p['t']['split'] for p in ps)
        if t > _free_until(ps[0]):                       # 第 1 路那位已經在排隊：中心線上的位置不能由 τ 推，這一排不驗左右順序
            continue
        c, (tx, ty), _ = M.at(_tau(ps[0], t, ht))
        offs = [(q[0] - c[0]) * ty - (q[1] - c[1]) * tx for q in (_Track(p['path']).at(t) for p in ps)]   # 往左（左法向）為正
        if any(b >= a for a, b in zip(offs, offs[1:])):
            bad.append(dict(rank=r, why='order'))
    return dict(maxRowDev=round(worst_row, 4), violations=len(bad), examples=bad[:3])


def geometry(data):
    """幾何避讓：所有路徑（每 SUBDIV 細分）只在西一入口門洞（gate.band）內穿過全壘打牆；離舞台線稿（X < STAGE_X 的部分）≥ STAGE_MIN，
    舞台東側的階梯也一樣（北行走第 4–9 排地標的直線，不上階梯）。
    STAIR_BOX 裡每一點往東數跨過幾條舞台線：不能超過 MAX_STEPS（0）條（不能走上階梯、走進舞台）。"""
    band = pairs(data['map']['gate']['band'])
    wall = np.array(pairs(data['map']['wall']))
    W0, W1 = wall[:-1], wall[1:]

    def inside(q):
        c = False
        for a, b in zip(band, band[1:] + band[:1]):
            if (a[1] > q[1]) != (b[1] > q[1]) and q[0] < a[0] + (b[0] - a[0]) * (q[1] - a[1]) / (b[1] - a[1]):
                c = not c
        return c
    segs = [(a, b) for poly in data['map']['base']['stage'] for a, b in zip(pairs(poly), pairs(poly)[1:]) if a[0] < STAGE_X and b[0] < STAGE_X]
    S = np.array([(a[0], a[1], b[0], b[1]) for a, b in segs])
    cell = 0.25
    grid = collections.defaultdict(list)
    for i, (ax, ay, bx, by) in enumerate(S):
        for gx in range(int(math.floor((min(ax, bx) - STAGE_MIN) / cell)), int(math.floor((max(ax, bx) + STAGE_MIN) / cell)) + 1):
            for gy in range(int(math.floor((min(ay, by) - STAGE_MIN) / cell)), int(math.floor((max(ay, by) + STAGE_MIN) / cell)) + 1):
                grid[(gx, gy)].append(i)
    pts = []
    wall_out, wall_bad = 0, []
    for p in data['persons']:
        a = np.array(p['path'], dtype=float)[:, :2]
        n_cross = 0
        for q0, q1 in zip(a[:-1], a[1:]):
            n = max(1, int(math.ceil(np.hypot(*(q1 - q0)) / SUBDIV)))
            f = np.arange(n)[:, None] / n
            pts.append(q0 + (q1 - q0) * f)
            # 穿牆：這一段與牆的每一段求交點
            d = (q1[0] - q0[0]) * (W1[:, 1] - W0[:, 1]) - (q1[1] - q0[1]) * (W1[:, 0] - W0[:, 0])
            ok = np.abs(d) > 1e-12
            with np.errstate(divide='ignore', invalid='ignore'):
                t = ((W0[:, 0] - q0[0]) * (W1[:, 1] - W0[:, 1]) - (W0[:, 1] - q0[1]) * (W1[:, 0] - W0[:, 0])) / d
                u = ((W0[:, 0] - q0[0]) * (q1[1] - q0[1]) - (W0[:, 1] - q0[1]) * (q1[0] - q0[0])) / d
            for k in np.nonzero(ok & (t >= 0) & (t <= 1) & (u >= 0) & (u <= 1))[0]:
                n_cross += 1
                x = q0 + (q1 - q0) * t[k]
                if not inside(x):
                    wall_out += 1
                    wall_bad.append(dict(who=p['id'], at=[round(float(x[0]), 3), round(float(x[1]), 3)]))
        pts.append(a[-1:])
        if n_cross != 1:
            wall_bad.append(dict(who=p['id'], crossings=n_cross))
    P = np.concatenate(pts)
    P = P[P[:, 0] < STAGE_X + STAGE_MIN + cell]
    best = np.full(len(P), 9.0)
    keys = np.floor(P / cell).astype(int)
    order = collections.defaultdict(list)
    for i, (gx, gy) in enumerate(map(tuple, keys)):
        order[(gx, gy)].append(i)
    for key, idx in order.items():
        si = grid.get(key)
        if not si:
            continue
        Q = P[idx]
        ax, ay, bx, by = S[si].T
        dx, dy = bx - ax, by - ay
        L2 = np.maximum(dx * dx + dy * dy, 1e-12)
        f = np.clip(((Q[:, 0:1] - ax) * dx + (Q[:, 1:2] - ay) * dy) / L2, 0, 1)
        best[idx] = np.hypot(Q[:, 0:1] - (ax + dx * f), Q[:, 1:2] - (ay + dy * f)).min(1)
    # 階梯：STAIR_BOX 裡每一點往東數跨過幾條舞台線
    x0, x1, y0, y1 = STAIR_BOX
    steps = np.zeros(len(P), dtype=int)
    inbox = (P[:, 0] > x0) & (P[:, 0] < x1) & (P[:, 1] > y0) & (P[:, 1] < y1)
    SB = S[(np.maximum(S[:, 1], S[:, 3]) > y0 - 0.2) & (np.minimum(S[:, 1], S[:, 3]) < y1 + 0.2) & (np.maximum(S[:, 0], S[:, 2]) > x0 - 0.5)]
    ib = np.nonzero(inbox)[0]
    for k0 in range(0, len(ib), 20000):
        idx = ib[k0:k0 + 20000]
        Q = P[idx]
        ay, by = SB[:, 1], SB[:, 3]
        span = (ay - Q[:, 1:2]) * (by - Q[:, 1:2]) < 0
        with np.errstate(divide='ignore', invalid='ignore'):
            xx = SB[:, 0] + (SB[:, 2] - SB[:, 0]) * (Q[:, 1:2] - ay) / (by - ay)
        steps[idx] = (span & (xx > Q[:, 0:1]) & (xx < x1)).sum(1)
    bad_steps = int((steps > MAX_STEPS).sum())
    x_l0 = _March(data['map']['march']).lanes(-1)[0][0]           # 北行直線（中心線最後一點）上的第 1 路 x
    on_north = np.abs(P[:, 0] - x_l0) <= NORTH_LINE_TOL
    near_out = int((best < np.where(on_north, STAGE_MIN_NORTH, STAGE_MIN)).sum())
    k = int(best.argmin()) if len(best) else 0
    min_stage = float(best[k]) if len(best) else 9.0
    return dict(points=int(len(P)), minStage=round(min(min_stage, 9.0), 4), stageNear=near_out, wallOutside=wall_out,
                stairPoints=int((steps > 0).sum()), maxSteps=int(steps.max()) if len(steps) else 0, stepViolations=bad_steps,
                at=[round(float(P[k][0]), 3), round(float(P[k][1]), 3)] if len(P) else None,
                violations=near_out + bad_steps + len(wall_bad), examples=wall_bad[:3])


def align(data):
    """第 9 排對齊（11/9 第二版）：map.align 給對齊線 x（第 9 排東側的欄間空隙）與各大隊各排過線時刻 ranks[大隊] = [T0, T1, …]。
    - 第 10 排以東（field.X > x）的人：路徑經過 (x, 自己那一列的 Y)，離開那一點的時刻 = 自己那一排（slot）的 T（± RELEASE_TOL）：
      同一排六列一起過線；之後不再排隊（t.holdEnd ≤ 過線時刻）。各排的 T 依序、相鄰至少 RANK_GAP；T0 = release。
    - 第 9 排與以內的人不經過對齊點；可以被前面的隊伍擋（有排隊時段，列出人數）。
    - 沒有排隊時段的人，離開隊頭之後路徑上沒有任何停留點；排隊時段只有一段（t.holdStart → t.holdEnd）。
    - 資訊：排隊人數、最長排隊時段、在穿過西一入口之前就開始排隊的人數（11/9 企劃同意後面大隊在進門前等）。"""
    A = data['map']['align']
    X = A['x']
    ranks = {int(d): v for d, v in A['ranks'].items()}
    bad, worst = [], 0.0
    for d, T in ranks.items():
        if abs(T[0] - A['release'][str(d)]) > 1e-6 or any(b - a < build.RANK_GAP - RELEASE_TOL for a, b in zip(T, T[1:])):
            bad.append(dict(dadui=d, why='ranks'))
    n_hold = n_pre = n_direct = 0
    max_hold = 0.0
    for p in data['persons']:
        t, a = p['t'], p['path']
        k = next((i for i, q in enumerate(a) if q[2] >= t['enter'] - 1e-6), len(a))
        stays = any(q0[:2] == q1[:2] for q0, q1 in zip(a[k:], a[k + 1:]))
        held = 'holdStart' in t
        if held:
            n_hold += 1
            n_pre += t['holdStart'] < t['gate']
            n_direct += p['field']['X'] <= X
            max_hold = max(max_hold, t['holdEnd'] - t['holdStart'])
            if t['holdEnd'] < t['holdStart'] or t['holdStart'] < t['enter'] - ALIGN_TOL:
                bad.append(dict(who=p['id'], why='holdWindow'))
        elif stays:
            bad.append(dict(who=p['id'], why='stopWithoutHold'))
        fy = p['field']['Y']
        at = [q for q in a if q[2] >= t['split'] - 1e-6 and abs(q[0] - X) <= ALIGN_TOL and abs(q[1] - fy) <= ALIGN_TOL]
        if p['field']['X'] <= X:
            continue
        T = ranks.get(p['dadui'], [])
        if not at or p['slot'] >= len(T):
            bad.append(dict(who=p['id'], why='noAlignPoint'))
            continue
        c = at[-1][2]                                    # 離開對齊點（在線上等的話，是最後一個點）
        worst = max(worst, abs(c - T[p['slot']]))
        if abs(c - T[p['slot']]) > RELEASE_TOL or (held and t['holdEnd'] > c + RELEASE_TOL + build.ALIGN_DT):
            bad.append(dict(who=p['id'], why='cross', at=c, rank=T[p['slot']]))
    return dict(x=X, pai=A['pai'], ranks=sum(len(v) for v in ranks.values()), holders=n_hold, directHeld=n_direct, preGate=n_pre,
                maxHold=round(max_hold, 3), maxCrossErr=round(worst, 4), violations=len(bad), examples=bad[:3])


def check_all(data, coll=None):
    """coll：已算好的 (穿過站定者, 走路互撞, 穿過已坐好的人)，build.py 從避撞最後一輪帶進來；沒給就重算。"""
    persons = data['persons']
    ht = _head_tau(data)
    out = {}
    # 1. 碰撞
    if coll is None:
        coll = collisions(persons, data['meta']['tEnd']) + (seated_hits(persons, data['meta']['tEnd']),)
    st, wk, sh = coll
    out['collisions'] = dict(standing=len(st), walking=len(wk), seated=len(sh),
                             examples=[dict(kind='standing', who=[k, v[1]], t=v[0]) for k, v in list(st.items())[:3]] +
                                      [dict(kind='walking', who=list(k), t=t) for k, t in list(wk.items())[:3]] +
                                      [dict(kind='seated', who=[k, v[1]], t=v[0]) for k, v in list(sh.items())[:3]])
    # 2. 依時間的巢狀：兩路依通過樓梯口時刻合併，兩路都開始後 A 的出口比 B 近、且不在同一座階梯
    bad, same = plan.nesting_violations(persons, key=lambda p: (p['t']['stair'], p['lane']))
    out['nesting'] = dict(violations=len(bad), sameStair=len(same), examples=(bad + same)[:3])
    # 2b. 指派：每路換口只往上游；換口前那個出口已用滿（兩路合計）；分坐兩出口的列數只列出、不算違反
    seqs = {L: sorted((p for p in persons if p['lane'] == L), key=lambda p: p['laneIdx']) for L in plan.LANES}
    by_exit = {e: sorted((p for p in persons if p['exit'] == e), key=lambda p: p['exitSeq']) for e in plan.EXITS}
    cap_of = {e: len(plan.usable_seats(data, e)) for e in plan.EXITS}
    upstream, not_full, segments, examples = 0, 0, {}, []
    for L in plan.LANES:
        pairs_ = [(a, b) for a, b in zip(seqs[L], seqs[L][1:]) if a['exit'] != b['exit']]
        segments[L] = 1 + len(pairs_)
        for a, b in pairs_:
            if plan.EXIT_RANK[b['exit']] < plan.EXIT_RANK[a['exit']]:
                upstream += 1
                examples.append(dict(lane=L, idx=b['laneIdx'], exits=[a['exit'], b['exit']]))
            elif len(by_exit[a['exit']]) < cap_of[a['exit']]:
                not_full += 1
                examples.append(dict(lane=L, idx=b['laneIdx'], exits=[a['exit'], b['exit']], used=len(by_exit[a['exit']]), capacity=cap_of[a['exit']]))
    by_col = collections.defaultdict(set)
    for p in persons:
        by_col[p['lie']].add(p['exit'])
    split = sorted(lie for lie, es in by_col.items() if len(es) > 1)
    out['assignment'] = dict(upstreamViolations=upstream, notFullSwitches=not_full, segments=segments, splitColumns=len(split),
                             splitLies=split, examples=examples[:3])
    # 2c. 路徑不交叉
    out['routes'] = lane_crossings(data)
    # 3. 不斷拍：樓梯口兩路（t.stair）、西一入口六路（t.gate）
    stair = {L: _gaps(seqs[L], 'stair', 'dadui') for L in plan.LANES}
    gate = {}
    for j in range(6):
        ps = sorted((p for p in persons if p['gateLane'] == j), key=lambda p: p['gateIdx'])
        gate[str(j)] = _gaps(ps, 'gate', 'dadui', lambda p: _free_until(p) < p['t']['gate'])   # 11/9：後面大隊在進門前排隊時，入口拍距不再固定
    n_ld = collections.Counter((p['lane'], p['dadui']) for p in persons)
    rule_bad = []
    for L in plan.LANES:
        for a, b in zip(seqs[L], seqs[L][1:]):
            if a['dadui'] != b['dadui']:
                d = a['dadui']
                rule = build.HEADWAY * (max(n_ld[(M, d)] for M in plan.LANES) - n_ld[(L, d)]) + build.HEADWAY + build.DADUI_GAP
                gap = b['t']['stair'] - a['t']['stair']
                if gap > rule + RULE_SLACK + 1e-6:
                    rule_bad.append(dict(lane=L, dadui=d, gap=round(gap, 3), rule=round(rule, 3)))
    cont_ok = not rule_bad and all(v['maxGapBoundary'] <= GATE_BOUNDARY_MAX for v in gate.values()) and all(v['orderOk'] and v['minGap'] >= GAP_MIN and v['maxGapWithin'] <= GAP_MAX and v['maxGapBoundary'] <= BOUNDARY_MAX for v in stair.values()) and \
        all(v['orderOk'] and (v['minGap'] is None or v['minGap'] >= GATE_GAP_MIN) and v['maxGapWithin'] <= GATE_GAP_MAX for v in gate.values())
    out['continuity'] = dict(stair=stair, gate=gate, boundaryRuleViolations=len(rule_bad), boundaryExamples=rule_bad[:3], ok=cont_ok)
    # 3b. 步速與集合位置：離座 → 樓梯 → 通行帶 → 轉彎 → 自己的集合位置 全程步速；集合位置裡（t.assembly → t.enter）只在自己那一路上站住或往前補、
    #     不快過 build.SLOW（彎道外側那一路比中心線長，容許 1.2 倍）；離開隊頭之後不快過步速（整排轉彎時內圈放慢）、除了第 9 排對齊的停住時段不停；分出（t.split）之後步速
    #     （沿列間空隙往西橫走那一段可以放慢到 build.SLOW_MIN 倍，避撞用）；
    #     t.gate 是自己的路徑穿過全壘打牆的時刻
    V = data['meta']['speedUnitPerSec']
    B2 = Poly(pairs(data['map']['b2Corridor']))
    wall = pairs(data['map']['wall'])

    def extra(a):
        return (a[-1][2] - a[0][2]) - build.cum([q[:2] for q in a])[-1] / V if len(a) > 1 else 0.0

    def idx(a, t):
        return next((i for i, q in enumerate(a) if abs(q[2] - t) < 2e-3), None)
    pace_bad, block_t, gate_err = [], [], 0.0
    for p in persons:
        t, a = p['t'], p['path']
        ka, ke, ks = idx(a, t['assembly']), idx(a, t['enter']), idx(a, t['split'])
        bad = ka is None or ke is None or ks is None or not ke < ks or abs(a[0][2] - t['leave']) > 1e-6 or abs(a[-1][2] - t['arrive']) > 1e-6
        if not bad:
            bad = extra(a[:ka + 1]) > WAIT_SLACK
        if not bad:                                      # 分出之後步速；只有沿列間空隙往西橫走的那一段可以放慢（避撞），不低於 SLOW_MIN 倍；第 9 排對齊停住那一段除外
            for q0, q1 in zip(a[ks:], a[ks + 1:]):
                if _in_hold(p, q0, q1):
                    continue
                d, dt = math.dist(q0[:2], q1[:2]), q1[2] - q0[2]
                lateral = abs(q1[1] - q0[1]) < 1e-6 and q1[0] < q0[0]
                if dt <= 0 or d > V * dt + PATH_SPEED_ABS or (d < V * dt - PATH_SPEED_ABS and not (lateral and d >= build.SLOW_MIN * V * dt - PATH_SPEED_ABS)):
                    bad = True
                    break
        if not bad:
            for q0, q1 in zip(a[ka:ke], a[ka + 1:ke + 1]):
                u, o, _ = B2.proj(q1[:2])
                if math.dist(q0[:2], q1[:2]) > build.SLOW * 1.2 * (q1[2] - q0[2]) + 0.002 or abs(o - routes.stage_off(p['gateLane'])) > STAGE_OFF_TOL:
                    bad = True
                    break
        if not bad:
            for q0, q1 in zip(a[ke:], a[ke + 1:]):
                d = math.dist(q0[:2], q1[:2])
                if q1[2] <= q0[2] or d > V * (q1[2] - q0[2]) + PATH_SPEED_ABS or (d < 1e-9 and not _in_hold(p, q0, q1)):
                    bad = True
                    break
        if not bad:
            tg = _wall_time(a, wall)
            if tg is None:
                bad = True
            else:
                gate_err = max(gate_err, abs(tg - t['gate']))
                bad = abs(tg - t['gate']) > 0.01
        if bad:
            pace_bad.append(p['id'])
        block_t.append(t['enter'] - t['assembly'])
    out['pace'] = dict(violations=len(pace_bad), examples=pace_bad[:3], minBlock=round(min(block_t), 3), maxBlock=round(max(block_t), 3),
                       gateTimeErr=round(gate_err, 4))
    # 3c. 一排六人：排號自己重算（每個大隊從新的一排開始、大隊內第 slot 位在第 slot 排）；同一排一起離開隊頭（容許 SHIFT_TOL），
    #     排與排（以經過大隊 1 隊頭的時刻比）至少 RANK_GAP；每個大隊全員站定之後第一排才出發；同一路前後兩人在集合位置裡始終相距至少 0.9 格
    n_dl = collections.Counter((p['dadui'], p['gateLane']) for p in persons)
    start, off_ = {}, 0
    for d in sorted({p['dadui'] for p in persons}):
        start[d] = off_
        off_ += max(c for (dd, _), c in n_dl.items() if dd == d)
    by_rank = collections.defaultdict(list)
    for p in persons:
        by_rank[start[p['dadui']] + p['slot']].append(p)
    r_bad, skew = [], 0.0
    rank_t = []
    for r in sorted(by_rank):
        es = [p['t']['enter'] for p in by_rank[r]]
        skew = max(skew, max(es) - min(es))
        if max(es) - min(es) > SHIFT_TOL or len({p['gateLane'] for p in by_rank[r]}) != len(by_rank[r]):
            r_bad.append(dict(rank=r, who=[p['id'] for p in by_rank[r]][:6]))
        d0 = by_rank[r][0]['dadui']
        rank_t.append(min(es) + ht[1] - ht[d0])          # 換算成經過大隊 1 隊頭的時刻
    gaps = [b - a for a, b in zip(rank_t, rank_t[1:])]
    if gaps and min(gaps) < build.RANK_GAP - SHIFT_TOL:
        r_bad.append(dict(rank='gap', minGap=round(min(gaps), 3)))
    fill_ok = all(max(p['t']['assembly'] for p in persons if p['dadui'] == d) <= min(p['t']['enter'] for p in persons if p['dadui'] == d) + 1e-6
                  for d in {p['dadui'] for p in persons})                      # 每個大隊全員在集合位置站定後才出發
    if not fill_ok:
        r_bad.append(dict(rank='fill'))

    def xy_at(p, t):
        a = p['path']
        k = max(i for i, q in enumerate(a) if q[2] <= t + 1e-9)
        q0, q1 = a[k], a[min(k + 1, len(a) - 1)]
        f = (t - q0[2]) / (q1[2] - q0[2]) if q1[2] > q0[2] else 0.0
        return (q0[0] + (q1[0] - q0[0]) * f, q0[1] + (q1[1] - q0[1]) * f)
    min_sp = 9.0
    for j in range(6):
        ps = sorted((p for p in persons if p['gateLane'] == j), key=lambda p: p['gateIdx'])
        for a_, b_ in zip(ps, ps[1:]):
            t0, t1 = b_['t']['assembly'], min(a_['t']['enter'], b_['t']['enter'])
            for k in range(5):
                if t1 <= t0:
                    break
                tt = t0 + (t1 - t0) * k / 4
                min_sp = min(min_sp, math.dist(xy_at(a_, tt), xy_at(b_, tt)))
    if min_sp < 0.75 * routes.STAGE_STEP:                             # 彎道內側那一路比中心線短（R 1.13 的彎、偏移 0.2：0.82 倍）
        r_bad.append(dict(rank='spacing', minSpacing=round(min_sp, 3)))
    out['ranks'] = dict(n=len(by_rank), maxSkew=round(skew, 3), minGap=round(min(gaps), 3) if gaps else None, fillOk=fill_ok,
                        minSpacing=round(min_sp, 3), violations=len(r_bad), examples=r_bad[:3])
    out['assembly'] = assembly(data)
    # 3d–3g. 整排並肩、轉彎、lane 對應、幾何避讓
    out['formation'] = formation(data, by_rank)
    out['wheel'] = wheel(data)
    out['laneMap'] = lane_map(data, by_rank)
    out['geometry'] = geometry(data)
    out['align'] = align(data)
    out['pillars'] = pillars(data)                     # 資訊：圖面柱位衝突（待現場確認），不算進 ok
    # 4. 座位：唯一、合法、休息區＝出口的區、每出口由上排往下且由出口側往中央、exits.order 名單就是該出口全員（依 exitSeq）
    keys = [(p['rest']['sec'], p['rest']['pai'], p['rest']['no']) for p in persons]
    seat_of = {(s['sec'], s['pai'], s['no']): s for s in data['restSeats']}
    illegal = sum(1 for k in keys if k not in seat_of or not plan.seat_usable(seat_of[k]))
    wrong_sec = sum(1 for p in persons if p['rest']['sec'] != plan.EXIT_DEF[p['exit']]['sec'])
    listed = {e['key']: e for e in data['exits']}
    order_bad = coverage_bad = 0
    for e in plan.EXITS:
        q = by_exit[e]
        if [p['exitSeq'] for p in q] != list(range(len(q))) or listed.get(e, {}).get('order') != [p['id'] for p in q]:
            coverage_bad += 1
        pais = [p['rest']['pai'] for p in q]
        if pais != sorted(pais, reverse=True):
            order_bad += 1
        for pai in set(pais):
            nos = [p['rest']['no'] for p in q if p['rest']['pai'] == pai]
            want = sorted(nos) if plan.EXIT_DEF[e]['fill'] == 'asc' else sorted(nos, reverse=True)
            if nos != want:
                order_bad += 1
        leaves = [p['t']['leave'] for p in q]                  # FIFO：先走的坐上面
        if any(b < a - 0.15 - 1e-6 for a, b in zip(leaves, leaves[1:])):
            order_bad += 1
    out['seats'] = dict(unique=len(set(keys)), population=len(persons), illegal=illegal, wrongSection=wrong_sec, orderViolations=order_bad, orderCoverage=coverage_bad)
    # 5. 容量：用量由 persons 計、可用席由 restSeats 重算，再與 exits 欄位比對
    cap = {}
    for e in plan.EXITS:
        used = len(by_exit[e])
        f = listed.get(e, {})
        cap[e] = dict(used=used, capacity=cap_of[e], fieldsOk=bool(f.get('used') == used and f.get('capacity') == cap_of[e]))
    out['capacity'] = cap
    out['ok'] = bool(not st and not wk and not sh and out['nesting']['violations'] == 0 == out['nesting']['sameStair'] and upstream == 0 and not_full == 0 and cont_ok
                     and out['routes']['crossings'] == 0 and not pace_bad and not r_bad
                     and all(out[k]['violations'] == 0 for k in ('assembly', 'formation', 'wheel', 'laneMap', 'geometry', 'align'))
                     and len(set(keys)) == len(persons) == POPULATION and illegal == 0 and wrong_sec == 0 and order_bad == 0 and coverage_bad == 0
                     and all(v['used'] <= v['capacity'] and v['fieldsOk'] for v in cap.values()))
    return out


def main(path):
    data = json.load(open(path, encoding='utf-8'))
    C = check_all(data)
    A, S, Rt, Cn = C['assignment'], C['seats'], C['routes'], C['continuity']
    F, Wh, Lm, Ge, St = C['formation'], C['wheel'], C['laneMap'], C['geometry'], C['assembly']
    rng = lambda vs: f"{min(v['minGap'] for v in vs if v['minGap'] is not None)}–{max(v['maxGapWithin'] for v in vs)}"
    Al = C['align']
    rows = [
        ('穿過站定者 / 走路互撞 / 穿過已坐好的人', f"{C['collisions']['standing']} / {C['collisions']['walking']} / {C['collisions']['seated']}", '0 / 0 / 0',
         C['collisions']['standing'] == 0 == C['collisions']['walking'] == C['collisions']['seated']),
        ('依時間巢狀：出口順序違反 / 同一座階梯', f"{C['nesting']['violations']} / {C['nesting']['sameStair']}", '0 / 0', C['nesting']['violations'] == 0 == C['nesting']['sameStair']),
        ('指派：換口往下游 / 未坐滿就換', f"{A['upstreamViolations']} / {A['notFullSwitches']}（每路 {'、'.join(f'{L} {A['segments'][L]} 段' for L in plan.LANES)}；分坐兩出口 {A['splitColumns']} 列）",
         '0 / 0', A['upstreamViolations'] == 0 == A['notFullSwitches']),
        ('路徑交叉（B2 六列 / B1 兩路）', f"{Rt['crossings']}", '0', Rt['crossings'] == 0),
        ('不斷拍', f"樓梯 {rng(Cn['stair'].values())}，交界 ≤ {max(v['maxGapBoundary'] for v in Cn['stair'].values())}（超出規則值 {Cn['boundaryRuleViolations']} 處）；西一入口 {rng(Cn['gate'].values())}",
         f'樓梯 {GAP_MIN}–{GAP_MAX}、交界 ≤ {BOUNDARY_MAX}；西一入口 ≥ {GATE_GAP_MIN}、大隊內 ≤ {GATE_GAP_MAX}、大隊間 ≤ {GATE_BOUNDARY_MAX}', Cn['ok']),
        ('步速與集合位置（到集合位置前不停；集合位置裡只在自己那一路站住或往前補；放行後不停、不快過步速）', f"{C['pace']['violations']}（每人在集合位置 {C['pace']['minBlock']}–{C['pace']['maxBlock']} 秒；t.gate 與穿牆時刻差 ≤ {C['pace']['gateTimeErr']}）", '0', C['pace']['violations'] == 0),
        ('一排六人一起放行（每個大隊站齊才放行、排距、前後間距）', f"{C['ranks']['violations']}（{C['ranks']['n']} 排；同排最大差 {C['ranks']['maxSkew']} 秒；排距 ≥ {C['ranks']['minGap']}；前後 ≥ {C['ranks']['minSpacing']}）", '0', C['ranks']['violations'] == 0),
        ('並肩（t.enter → 分出，每 0.1 秒）', f"{F['violations']}（{F['samples']} 次取樣；偏離橫排 ≤ {F['maxAngle']}°、間距誤差 ≤ {F['maxSpacingErr']}、中心偏 ≤ {F['maxCenterOff']}、離平移線 ≤ {F['maxTrackDev']}）",
         f'0（≤ {ANGLE_MAX}° / {SPACING_TOL} / {CENTER_TOL} / {TRACK_TOL}）', F['violations'] == 0),
        ('整排轉彎（外圈不超速、內圈不倒退、內圈半徑）', f"{Wh['violations']}（{Wh['turns']} 個轉彎；最快 {Wh['maxSpeed']}、內圈最慢 {Wh['minInnerSpeed']}、內圈半徑 ≥ {Wh['minInnerR']}）",
         f"0（≤ V + {SPEED_EPS}、> 0、≥ {data['map']['march']['innerMin']}）", Wh['violations'] == 0),
        ('lane 對應（lane j → 列 6k−5+j、進列後在自己那一列朝座位走）', f"{Lm['violations']}（進列後 Y 偏差 ≤ {Lm['maxRowDev']}）", f'0（≤ {ROW_TOL}）', Lm['violations'] == 0),
        ('B2 集合區（九個集合位置依序不重疊、入口前留空、站在自己那一路那一格、到位前不停、兩路走通行帶、九隊站齊才依序放行）', f"{St['violations']}（{St['blocks']} 個位置；到位前最長停留 {St['maxWaitBeforeSlot']} 秒；通行帶越界 {St['bypassViolations']}；動畫裡同時有人在集合區的大隊最多 {St['peakDaduiInArea']} 個）", '0', St['violations'] == 0),
        ('幾何避讓（只在門洞穿牆、離舞台、不上階梯）', f"{Ge['violations']}（門洞外穿牆 {Ge['wallOutside']}；離舞台最近 {Ge['minStage']}，< {STAGE_MIN} 的點 {Ge['stageNear']}；走上階梯最多 {Ge['maxSteps']} 階、越界 {Ge['stepViolations']}）",
         f'0（≥ {STAGE_MIN}，第 1 路北行線 ≥ {STAGE_MIN_NORTH}；上階梯 {MAX_STEPS} 階）', Ge['violations'] == 0),
        ('第 9 排對齊（第 10 排以東每一排六人同時過第 9 排、依序；第 9 排以內不對齊）', f"{Al['violations']}（{Al['ranks']} 排；過線時刻誤差 ≤ {Al['maxCrossErr']}；排隊 {Al['holders']} 人（第 9 排以內 {Al['directHeld']}、進門前就開始 {Al['preGate']}）、最長 {Al['maxHold']} 秒）",
         f"0（± {RELEASE_TOL}）", Al['violations'] == 0),
        ('座位唯一 / 違規席 / 區不符 / 順序違反 / 名單不符', f"{S['unique']} / {S['illegal']} / {S['wrongSection']} / {S['orderViolations']} / {S['orderCoverage']}", f'{POPULATION} / 0 / 0 / 0 / 0',
         S['unique'] == POPULATION and S['illegal'] == 0 == S['wrongSection'] == S['orderViolations'] == S['orderCoverage']),
        ('出口用量 ≤ 可用席（重算，與 exits 欄位一致）', ', '.join(f"{k} {v['used']}/{v['capacity']}" + ('' if v['fieldsOk'] else '（欄位不符）') for k, v in C['capacity'].items()), '成立',
         all(v['used'] <= v['capacity'] and v['fieldsOk'] for v in C['capacity'].values())),
    ]
    for name, val, thr, ok in rows:
        print(f"[{'OK' if ok else 'NG'}] {name}: {val}（門檻 {thr}）")
    Pl = C['pillars']
    print(f"[{'待確認' if Pl['conflicts'] else 'OK'}] 圖面柱位與路徑衝突（不算進通過與否）: {Pl['conflicts']} 根柱、{Pl['persons']} 人經過"
          + ''.join(f"；{k}（B2 u {v['u']}、偏移 {v['off']}）走過 {v['persons']} 人、站在柱上 {v['standing']} 人（大隊 {'、'.join(map(str, v['daduis'])) or '—'}）" for k, v in Pl['where'].items())
          + ''.join(f"；{k} 假設沒有（若有：走過 {v['persons']} 人、站在柱上 {v['standing']} 人，大隊 {'、'.join(map(str, v['daduis'])) or '—'}）" for k, v in Pl.get('assumedAbsent', {}).items()))
    meta = data['meta'].get('checks') or {}
    same = bool(meta) and all(meta.get(k) == C.get(k) for k in COMPARED) and meta.get('ok') == C['ok']
    print('meta.checks 與重算一致' if same else 'meta.checks 與重算不一致或缺少', '；', '通過' if C['ok'] and same else '未通過')
    return 0 if C['ok'] and same else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1]))
