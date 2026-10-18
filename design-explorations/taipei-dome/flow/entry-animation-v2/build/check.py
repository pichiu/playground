"""動畫資料的碰撞檢查(兩項都必須是 0):

1. 穿過站定者:走動中的人與已在集結區站定的人(含同一列)距離 < R。
2. 走路互撞:兩個都在走的人距離 < R(走向集結區、離開集結區到 6口、場內就位,全程)。

用法: python3 check.py new.json
時間步長 DT 秒、行進速度約 1.1 單位/秒,每步最多走 0.011 單位,遠小於 R=0.03;
build.py 內的避撞用的是較粗的取樣加較大的半徑,這裡用細取樣獨立驗收。
"""
import json, sys, collections
import numpy as np

DT, R = 0.01, 0.03
d = json.load(open(sys.argv[1])); P = d['persons']
T = np.arange(6, d['meta']['tEnd'], DT)
X = np.empty((len(P), len(T)), dtype=np.float32); Y = np.empty_like(X)
for i, p in enumerate(P):
    a = np.array(p['path'])
    X[i] = np.interp(T, a[:, 2], a[:, 0]); Y[i] = np.interp(T, a[:, 2], a[:, 1])
tt = lambda k: np.array([p['t'][k] for p in P])
leave, assembly, enter, arrive = tt('leave'), tt('assembly'), tt('enter'), tt('arrive')
lie = np.array([p['lie'] for p in P])

stand_hit, walk_hit = {}, {}
for k, t in enumerate(T):
    st = np.nonzero((assembly <= t) & (t < enter - 0.05))[0]
    mv = np.nonzero(((leave + 0.05 < t) & (t < assembly - 0.05)) | ((enter + 0.05 < t) & (t < arrive - 0.05)))[0]
    if not len(mv): continue
    grid = collections.defaultdict(list)
    for i in mv: grid[(int(X[i, k] // R), int(Y[i, k] // R))].append(('m', i))
    for i in st: grid[(int(X[i, k] // R), int(Y[i, k] // R))].append(('s', i))
    for i in mv:
        cx, cy = int(X[i, k] // R), int(Y[i, k] // R)
        for gx in (cx - 1, cx, cx + 1):
            for gy in (cy - 1, cy, cy + 1):
                for kind, j in grid.get((gx, gy), ()):
                    if j == i or (X[i, k] - X[j, k]) ** 2 + (Y[i, k] - Y[j, k]) ** 2 >= R * R: continue
                    if kind == 's':
                        stand_hit.setdefault(P[i]['id'], (round(float(t), 2), P[j]['id'], '同列' if lie[i] == lie[j] else '他列'))
                    elif j > i:
                        walk_hit.setdefault((P[i]['id'], P[j]['id']), round(float(t), 2))
print('穿過站定者人數', len(stand_hit), '(同列', sum(v[2] == '同列' for v in stand_hit.values()), ')')
print('走路互撞對數', len(walk_hit))
for pid, v in list(stand_hit.items())[:6]: print('  站定', pid, v)
for pr, t in list(walk_hit.items())[:6]: print('  互撞', pr, t)
sys.exit(1 if stand_hit or walk_hit else 0)
