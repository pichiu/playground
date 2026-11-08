"""版本 3.1 路徑抽查（README「驗證」一節）：與版本 3 逐人比對不變的欄位，並把大隊 1、5、9 各一列白衣、一列藍衣的完整路徑分段檢查。

用法: python3 verify_paths.py ../data.json ../../entry-animation-v3/data.json [圖.png]
- 不變：人員集合、座位、出口、出口序、樓梯路與序號、樓梯口時刻、離座時刻、列 ↔ 場內位置、西一入口序號、排號、終點。
- 連續：每人路徑時間遞增、任一段速度 ≤ 步速（容許四捨五入），沒有瞬移。
- 左右（以當下行進方向判定，不用螢幕左右）：同一排的白衣第 1 路與藍衣第 6 路，在
  (1) 集合位置（面向西一入口）、(2) 右轉進西一入口的轉彎中、(3) 穿過西一入口、(4) 北行到分出前，白衣都在行進方向左側。
- 圖（需要 matplotlib，沒有就略過）：選定的列從 B2 平台到場內位置，依階段上色。
"""
import json
import math
import sys

V_EPS = 0.004


def seg_speed_ok(path, v):
    worst = 0.0
    for a, b in zip(path, path[1:]):
        dt = b[2] - a[2]
        if dt <= 0:
            return False, float('inf')
        sp = math.dist(a[:2], b[:2]) / dt
        worst = max(worst, sp)
        if math.dist(a[:2], b[:2]) > v * dt + V_EPS:
            return False, sp
    return True, worst


def at(p, t):
    a = p['path']
    if t <= a[0][2]:
        return a[0][:2]
    for q0, q1 in zip(a, a[1:]):
        if q1[2] >= t:
            f = (t - q0[2]) / (q1[2] - q0[2]) if q1[2] > q0[2] else 0
            return (q0[0] + (q1[0] - q0[0]) * f, q0[1] + (q1[1] - q0[1]) * f)
    return a[-1][:2]


def left_of_travel(w, b, t, dt=0.05):
    """在 t 時刻，白衣 w 是否在「行進方向」的左側（行進方向取兩人中點 t → t+dt 的位移；畫面 y 向下，左法向 = (ty, −tx)）。"""
    m0 = [(x + y) / 2 for x, y in zip(at(w, t - dt), at(b, t - dt))]
    m1 = [(x + y) / 2 for x, y in zip(at(w, t + dt), at(b, t + dt))]
    tx, ty = m1[0] - m0[0], m1[1] - m0[1]
    L = math.hypot(tx, ty)
    if L < 1e-9:
        return None
    tx, ty = tx / L, ty / L
    pw, pb = at(w, t), at(b, t)
    return ((pw[0] - pb[0]) * ty - (pw[1] - pb[1]) * tx) > 0


def main(new_path, old_path, png=None):
    a = json.load(open(old_path, encoding='utf-8'))
    b = json.load(open(new_path, encoding='utf-8'))
    A = {p['id']: p for p in a['persons']}
    B = {p['id']: p for p in b['persons']}
    V = b['meta']['speedUnitPerSec']
    out = {'population': [len(A), len(B)], 'sameIds': set(A) == set(B), 'unique': len(B) == len(b['persons'])}
    keys = ['lie', 'pai', 'dadui', 'costume', 'rest', 'exit', 'exitSeq', 'lane', 'laneIdx', 'gateLane', 'gateIdx', 'slot', 'field', 'rank']
    out['fieldDiffs'] = {k: sum(1 for i in A if A[i][k] != B[i][k]) for k in keys}
    out['timeDiffs'] = {k: round(max(abs(A[i]['t'][k] - B[i]['t'][k]) for i in A), 6) for k in ('leave', 'stair')}
    out['endDiffs'] = sum(1 for i in A if A[i]['path'][-1][:2] != B[i]['path'][-1][:2])
    gate_order = lambda P: [i for i, _ in sorted(P.items(), key=lambda kv: (kv[1]['t']['gate'], kv[1]['gateLane']))]
    out['gateOrderSame'] = gate_order(A) == gate_order(B)
    out['daduiOrderAtGate'] = all(B[x]['dadui'] <= B[y]['dadui'] for x, y in zip(gate_order(B), gate_order(B)[1:]))
    bad_speed, vmax = [], 0.0
    for p in b['persons']:
        ok, sp = seg_speed_ok(p['path'], V)
        vmax = max(vmax, sp if sp != float('inf') else 0)
        if not ok:
            bad_speed.append(p['id'])
    out['continuity'] = dict(teleports=len(bad_speed), examples=bad_speed[:3], maxSegmentSpeed=round(vmax, 4), speed=V)
    # 左右：大隊 1、5、9，每一排白衣第 1 路（列 6k−5）與藍衣第 6 路（列 6k）
    sides = {}
    for d in (1, 5, 9):
        rows = {}
        for p in b['persons']:
            if p['dadui'] == d and p['gateLane'] in (0, 5):
                rows.setdefault(p['rank'], {})[p['gateLane']] = p
        res = dict(stage=0, turn=0, gate=0, north=0, wrong=0, rows=0)
        m = b['map']['march']
        for r, two in rows.items():
            if len(two) < 2:
                continue
            w, bl = two[0], two[5]
            res['rows'] += 1
            ts = {'stage': (w['t']['enter'] + w['t']['assembly']) / 2,                      # 站定中：以「下一步往哪走」判定，取放行後 0.05 秒的方向
                  'turn': w['t']['enter'] + (m['gateArcTau'] - m['headTau'][str(d)]) + 0.15,
                  'gate': (w['t']['gate'] + bl['t']['gate']) / 2,
                  'north': w['t']['enter'] + (m['northTau'] - m['headTau'][str(d)]) + 0.3}
            for k, t in ts.items():
                if k == 'north' and t >= min(w['t']['split'], bl['t']['split']):
                    continue                                                                 # 大隊 9 在沿牆段就分出，沒有北行段
                tt = w['t']['enter'] + 0.06 if k == 'stage' else t
                lo = left_of_travel(w, bl, tt)
                if lo is None:
                    continue
                res[k] += 1 if lo else 0
                res['wrong'] += 0 if lo else 1
        sides[str(d)] = res
    out['whiteLeftOfTravel'] = sides
    print(json.dumps(out, ensure_ascii=False, indent=1))
    if png:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            from matplotlib import font_manager
        except ImportError:
            print('沒有 matplotlib，略過圖')
            return 0
        for f in ('WenQuanYi Zen Hei', 'Noto Sans CJK TC', 'Noto Sans TC'):
            if any(f in x.name for x in font_manager.fontManager.ttflist):
                plt.rcParams['font.family'] = f
                break
        fig, axes = plt.subplots(1, 3, figsize=(18, 8))
        M = b['map']
        pairs = lambda f: list(zip(f[0::2], f[1::2]))
        for ax, d in zip(axes, (1, 5, 9)):
            for poly, c in ((M['staging']['band'], '#efe6da'), (M['staging']['bypassBand'], '#f6f1ea'), (M['gate']['band'], '#f6dcc0')):
                xs, ys = zip(*pairs(poly))
                ax.fill(xs, ys, color=c, zorder=0)
            for blk in M['staging']['blocks']:
                xs, ys = zip(*pairs(blk['poly']))
                ax.fill(xs, ys, fill=False, ec='#8f7b6a' if blk['dadui'] == d else '#ccc', lw=1.5 if blk['dadui'] == d else .6)
            xs, ys = zip(*pairs(M['wall']))
            ax.plot(xs, ys, color='#999', lw=.8)
            for lie, col in ((6 * d - 5, '#b08d57'), (6 * d, '#2f6fd6')):
                ps = sorted((p for p in b['persons'] if p['lie'] == lie), key=lambda p: p['stageRank'])
                for p in (ps[0], ps[-1]):
                    t = p['t']
                    segs = [(t['stair'], t['entry'], ':'), (t['entry'], t['assembly'], '-'), (t['assembly'], t['enter'], None), (t['enter'], t['split'], '-'), (t['split'], t['arrive'], '--')]
                    for t0, t1, ls in segs:
                        q = [x for x in p['path'] if t0 - 1e-6 <= x[2] <= t1 + 1e-6]
                        if ls and len(q) > 1:
                            ax.plot([x[0] for x in q], [x[1] for x in q], ls, color=col, lw=1.6 if p is ps[0] else .9, alpha=.9)
                    s = at(p, t['assembly'])
                    ax.plot(*s, 'o', color=col, ms=4)
                    ax.annotate(f"列{lie} 排{p['pai']}", s, fontsize=7, color=col, xytext=(4, 4), textcoords='offset points')
            ax.set_title(f'大隊 {d}：白衣列 {6*d-5}（褐）、藍衣列 {6*d}（藍）；粗線＝隊頭、細線＝隊尾\n點線＝樓梯→通行帶→回頭、實線＝進集合位置／放行後並肩、虛線＝分出進列', fontsize=9)
            ax.set_xlim(-12.2, 0.4)
            ax.set_ylim(11.6, -0.6)
            ax.set_aspect('equal')
            ax.axis('off')
        fig.tight_layout()
        fig.savefig(png, dpi=130)
        print('圖寫到', png)
    return 0 if (out['sameIds'] and not any(out['fieldDiffs'].values()) and not bad_speed and all(v['wrong'] == 0 for v in sides.values())) else 1


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:4]))
