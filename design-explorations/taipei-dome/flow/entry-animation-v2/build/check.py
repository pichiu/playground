"""動畫資料的碰撞驗收(兩項都必須是 0,否則 exit 1;判定見 collide.py)。

用法: python3 check.py new.json
以 0.01 秒取樣、R=0.03 獨立驗收;build.py 內的避撞用較粗的取樣加較大的半徑(0.035)。
"""
import json, sys
from collide import collisions

d = json.load(open(sys.argv[1]))
stand_hit, walk_hit = collisions(d['persons'], d['meta']['tEnd'])
print('穿過站定者人數', len(stand_hit), '(同列', sum(v[2] == '同列' for v in stand_hit.values()), ')')
print('走路互撞對數', len(walk_hit))
for pid, v in list(stand_hit.items())[:6]: print('  站定', pid, v)
for pr, t in list(walk_hit.items())[:6]: print('  互撞', pr, t)
sys.exit(1 if stand_hit or walk_hit else 0)
