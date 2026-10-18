"""檢查「行進中的人穿過已站定者」:任何時刻,走動中的人與已在集結區站定的人(含同一列)距離 < R 即算一次。

用法: python3 check.py new.json
時間步長 DT 秒、行進速度約 1.1 單位/秒,每步最多走 0.055 單位;直線穿過站定者時必有一個取樣點落在 R=0.03 內。
"""
import json, sys, collections
import numpy as np

DT, R = 0.05, 0.03
d = json.load(open(sys.argv[1])); P = d['persons']
T = np.arange(6, d['meta']['tEnd'], DT)
X = np.empty((len(P), len(T))); Y = np.empty_like(X)
for i, p in enumerate(P):
    a = np.array(p['path'])
    X[i] = np.interp(T, a[:, 2], a[:, 0]); Y[i] = np.interp(T, a[:, 2], a[:, 1])
tt = lambda k: np.array([p['t'][k] for p in P])
leave, assembly, enter, gate = tt('leave'), tt('assembly'), tt('enter'), tt('gate')
lie = np.array([p['lie'] for p in P])

bad = {}
for k, t in enumerate(T):
    st = np.nonzero((assembly <= t) & (t < enter - 0.05))[0]
    mv = np.nonzero(((leave < t) & (t < assembly - 0.05)) | ((enter + 0.05 < t) & (t < gate)))[0]
    if not len(st) or not len(mv): continue
    grid = collections.defaultdict(list)
    for i in st: grid[(int(X[i, k] // R), int(Y[i, k] // R))].append(i)
    for i in mv:
        if P[i]['id'] in bad: continue
        cx, cy = int(X[i, k] // R), int(Y[i, k] // R)
        for gx in (cx - 1, cx, cx + 1):
            for gy in (cy - 1, cy, cy + 1):
                for j in grid.get((gx, gy), ()):
                    if (X[i, k] - X[j, k]) ** 2 + (Y[i, k] - Y[j, k]) ** 2 < R * R:
                        bad.setdefault(P[i]['id'], (round(float(t), 2), P[j]['id'], '同列' if lie[i] == lie[j] else '他列'))
print('穿過站定者人數', len(bad), '(同列', sum(v[2] == '同列' for v in bad.values()), ')')
for pid, v in list(bad.items())[:12]: print(' ', pid, v)
