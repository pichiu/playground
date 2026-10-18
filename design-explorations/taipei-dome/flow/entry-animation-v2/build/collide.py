"""碰撞判定(build.py 收尾自我檢查與 check.py 驗收共用)。

兩項都必須是 0:
1. 穿過站定者:走動中的人與已在集結區站定的人(含同一列)距離 < R。
2. 走路互撞:兩個都在走的人距離 < R(走向集結區、離開集結區到 6口、場內就位,全程)。

每個取樣區間內兩人的相對位置視為線性變化,取區間內的最近距離,
所以在直線段內不會漏掉區間中間的擦身而過;區間內有轉角時誤差約 速度×dt/2(dt=0.01 時約 0.006)。
"""
import collections
import numpy as np


def collisions(persons, t_end, dt=0.01, r=0.03, t_start=6.0):
    P = persons
    T = np.arange(t_start, t_end, dt)
    X = np.empty((len(P), len(T)), dtype=np.float32); Y = np.empty_like(X)
    vmax = 0.0
    for i, p in enumerate(P):
        a = np.array(p['path'], dtype=float)
        X[i] = np.interp(T, a[:, 2], a[:, 0]); Y[i] = np.interp(T, a[:, 2], a[:, 1])
        seg = np.diff(a, axis=0); ok = seg[:, 2] > 1e-9
        if ok.any(): vmax = max(vmax, float((np.hypot(seg[ok, 0], seg[ok, 1]) / seg[ok, 2]).max()))
    tt = lambda k: np.array([p['t'][k] for p in P])
    leave, assembly, enter, arrive = tt('leave'), tt('assembly'), tt('enter'), tt('arrive')
    lie = np.array([p['lie'] for p in P])
    cell = r + 2 * vmax * dt                     # 一個區間內兩人最多能靠近的距離,格子取這麼大才不漏
    stand_hit, walk_hit = {}, {}
    for k in range(len(T) - 1):
        t = T[k]
        st = np.nonzero((assembly <= t) & (t < enter - 0.05))[0]
        mv = np.nonzero(((leave + 0.05 < t) & (t < assembly - 0.05)) | ((enter + 0.05 < t) & (t < arrive - 0.05)))[0]
        if not len(mv): continue
        grid = collections.defaultdict(list)
        for i in mv: grid[(int(X[i, k] // cell), int(Y[i, k] // cell))].append(('m', i))
        for i in st: grid[(int(X[i, k] // cell), int(Y[i, k] // cell))].append(('s', i))
        for i in mv:
            cx, cy = int(X[i, k] // cell), int(Y[i, k] // cell)
            for gx in (cx - 1, cx, cx + 1):
                for gy in (cy - 1, cy, cy + 1):
                    for kind, j in grid.get((gx, gy), ()):
                        if j == i or (kind == 'm' and j < i): continue
                        dx0, dy0 = float(X[i, k] - X[j, k]), float(Y[i, k] - Y[j, k])
                        ex = float(X[i, k + 1] - X[j, k + 1]) - dx0; ey = float(Y[i, k + 1] - Y[j, k + 1]) - dy0
                        ee = ex * ex + ey * ey
                        f = 0.0 if ee < 1e-12 else min(1.0, max(0.0, -(dx0 * ex + dy0 * ey) / ee))
                        if (dx0 + ex * f) ** 2 + (dy0 + ey * f) ** 2 >= r * r: continue
                        if kind == 's':
                            stand_hit.setdefault(P[i]['id'], (round(float(t), 2), P[j]['id'], '同列' if lie[i] == lie[j] else '他列'))
                        else:
                            walk_hit.setdefault((P[i]['id'], P[j]['id']), round(float(t), 2))
    return stand_hit, walk_hit
