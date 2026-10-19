#!/usr/bin/env python3
"""Reproducible, floor-aware white-chain audit of full-diagonal-plans.json.

Only strict transverse interior segment crossings are counted (sin angle >= .2,
each segment parameter .01..99). Point proximity uses .03 *figure units*, not
human clearance or a body width. Geometric counts do not assert simultaneous
presence; timing and corridor occupation are not certified by this audit.
"""
import sys
import collections
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = {'horizontal':json.loads(Path(sys.argv[1]).read_text()),'vertical':json.loads(Path(sys.argv[2]).read_text())} if len(sys.argv)>2 else json.loads((ROOT / 'full-diagonal-plans.json').read_text())
OUT = Path(sys.argv[3]) if len(sys.argv)>3 else ROOT / 'white-review-evidence.json'
CELL = .5
PROX = .03
SINE_MIN = .2
INTERIOR = .01
MAX_EXAMPLES = 6
PAIRS = [(i, i + 1) for i in range(1, 9)] + [(1, 3)]
STATION_PAIRS = [(1, 2), (2, 3), (1, 3)]


def brief(p):
    return {'id': p['id'], 'lie': p['lie'], 'feeder': p['feeder'],
            'stairLane': 'ABC'[p['stairLane'] - 1], 'assembly': p['assembly']}


def leg(p, segment):
    a, b = segment['a'], segment['b']
    return {'person': p, 'a': a, 'b': b, 'floor': segment['floor'],
            'stage': segment.get('stage', '集結至6口')}


def grid_for(segments):
    grid = collections.defaultdict(list)
    for j, s in enumerate(segments):
        a, b = s['a'], s['b']
        for x in range(math.floor(min(a[0], b[0]) / CELL), math.floor(max(a[0], b[0]) / CELL) + 1):
            for y in range(math.floor(min(a[1], b[1]) / CELL), math.floor(max(a[1], b[1]) / CELL) + 1):
                grid[(s['floor'], x, y)].append(j)
    return grid


def candidate_indices(grid, s):
    a, b = s['a'], s['b']
    found = set()
    for x in range(math.floor(min(a[0], b[0]) / CELL), math.floor(max(a[0], b[0]) / CELL) + 1):
        for y in range(math.floor(min(a[1], b[1]) / CELL), math.floor(max(a[1], b[1]) / CELL) + 1):
            found.update(grid.get((s['floor'], x, y), ()))
    return sorted(found)


def crossing(s, t):
    a, b, c, d = s['a'], s['b'], t['a'], t['b']
    ax, ay = b[0]-a[0], b[1]-a[1]
    bx, by = d[0]-c[0], d[1]-c[1]
    z = ax*by-ay*bx
    den = math.hypot(ax, ay)*math.hypot(bx, by)
    if den < 1e-12 or abs(z)/den < SINE_MIN:
        return None
    cx, cy = c[0]-a[0], c[1]-a[1]
    u, v = (cx*by-cy*bx)/z, (cx*ay-cy*ax)/z
    if INTERIOR < u < 1-INTERIOR and INTERIOR < v < 1-INTERIOR:
        return [round(a[0]+u*ax, 5), round(a[1]+u*ay, 5)]
    return None


def cross_groups(first, second):
    a = [leg(p, s) for p in first for s in p['arrivalParts']]
    b = [leg(p, s) for p in second for s in p['arrivalParts']]
    grid = grid_for(b)
    hits = 0
    pairs = set()
    geometric_points = set()
    cross_lane_pairs = set()
    stages = collections.Counter()
    floors = collections.Counter()
    sample_by_pattern = {}
    fallback_examples = []
    example_pairs = set()
    for s in a:
        for j in candidate_indices(grid, s):
            t = b[j]
            point = crossing(s, t)
            if point is None:
                continue
            hits += 1
            geometric_points.add((s['floor'], point[0], point[1]))
            key = (s['person']['id'], t['person']['id'])
            pairs.add(key)
            if s['person']['stairLane'] != t['person']['stairLane']:
                cross_lane_pairs.add(key)
            stages[f"{s['stage']} × {t['stage']}"] += 1
            floors[s['floor']] += 1
            if key not in example_pairs:
                example = {'first': brief(s['person']), 'second': brief(t['person']),
                           'firstStage': s['stage'], 'secondStage': t['stage'],
                           'firstSegment': [s['a'], s['b']],
                           'secondSegment': [t['a'], t['b']],
                           'floor': s['floor'], 'point': point}
                pattern = (s['person']['lie'], t['person']['lie'], s['stage'], t['stage'])
                if s['person']['stairLane'] != t['person']['stairLane']:
                    sample_by_pattern.setdefault(pattern, example)
                if len(fallback_examples) < MAX_EXAMPLES:
                    fallback_examples.append(example)
                example_pairs.add(key)
    examples = list(sample_by_pattern.values())[:MAX_EXAMPLES]
    selected = {(e['first']['id'], e['second']['id']) for e in examples}
    for example in fallback_examples:
        key = (example['first']['id'], example['second']['id'])
        if len(examples) >= MAX_EXAMPLES:
            break
        if key not in selected:
            examples.append(example)
            selected.add(key)
    return {'strictTransverseSegmentHits': hits, 'uniqueGeometricPoints': len(geometric_points),
            'uniquePersonPairs': len(pairs),
            'differentStairLaneUniquePersonPairs': len(cross_lane_pairs),
            'byFloors': dict(floors), 'byStages': dict(stages.most_common()), 'examples': examples}


def distance_to_segment(point, s):
    a, b = s['a'], s['b']
    vx, vy = b[0]-a[0], b[1]-a[1]
    l2 = vx*vx+vy*vy
    t = 0 if l2 == 0 else max(0, min(1, ((point[0]-a[0])*vx+(point[1]-a[1])*vy)/l2))
    near = [a[0]+t*vx, a[1]+t*vy]
    return math.dist(point, near), near


def points_near_routes(moving, stationary, path_key):
    # Stationary positions are the modeled arrival endpoints; their floor is
    # that of the last arrival segment, including the white-2 STAIR slots.
    points = [(p, p['arrival'][-1], p['arrivalParts'][-1]['floor']) for p in stationary]
    grid = collections.defaultdict(list)
    for p, q, floor in points:
        ix, iy = math.floor(q[0]/CELL), math.floor(q[1]/CELL)
        grid[(floor, ix, iy)].append((p, q))
    person_pairs = set()
    near_hits = 0
    examples = []
    sample_pairs = set()
    for p in moving:
        for raw in p[path_key]:
            s = leg(p, raw)
            a, b = s['a'], s['b']
            xs = range(math.floor((min(a[0], b[0])-PROX)/CELL), math.floor((max(a[0], b[0])+PROX)/CELL)+1)
            ys = range(math.floor((min(a[1], b[1])-PROX)/CELL), math.floor((max(a[1], b[1])+PROX)/CELL)+1)
            for x in xs:
                for y in ys:
                    for qperson, q in grid.get((s['floor'], x, y), ()):
                        dist, closest = distance_to_segment(q, s)
                        if dist > PROX:
                            continue
                        near_hits += 1
                        key = (p['id'], qperson['id'])
                        person_pairs.add(key)
                        if len(examples) < MAX_EXAMPLES and key not in sample_pairs:
                            examples.append({'moving': brief(p), 'stationary': brief(qperson),
                                             'movingStage': s['stage'], 'floor': s['floor'],
                                             'movingSegment': [s['a'], s['b']],
                                             'stationaryPoint': q,
                                             'nearestPoint': [round(v, 5) for v in closest],
                                             'distanceFigureUnits': round(dist, 5)})
                            sample_pairs.add(key)
    return {'segmentPointProximities': near_hits, 'uniquePersonPairs': len(person_pairs),
            'thresholdFigureUnits': PROX, 'examples': examples}


def audit(mode, plan):
    white = {d: [p for p in plan['people'] if p['costume']=='白' and p['dadui']==d]
             for d in range(1, 10)}
    group = {g['dadui']: g for g in plan['groups'] if g['costume']=='白'}
    cohorts = []
    for d in range(1, 10):
        ps = white[d]
        cohorts.append({'dadui': d, 'population': len(ps), 'lies': sorted({p['lie'] for p in ps}),
                        'feederByLie': {str(l): dict(collections.Counter(p['feeder'] for p in ps if p['lie']==l))
                                        for l in sorted({p['lie'] for p in ps})},
                        'assembly': dict(collections.Counter((p['assembly'], p['arrivalParts'][-1]['floor']) for p in ps)),
                        'withinCohortReportedSegmentHits': {key: group[d]['checks'][key]['count']
                                                            for key in ('arrival','departure','field','gateSeam')},
                        'withinCohortArrivalByStages': group[d]['checks']['arrival']['byStage']})
        cohorts[-1]['assembly'] = [{'node': node, 'floor': floor, 'people': n}
                                   for (node, floor), n in cohorts[-1]['assembly'].items()]
    crosses = {}
    for d, e in PAIRS:
        crosses[f'{d}->{e}'] = cross_groups(white[d], white[e])
    stationary = {}
    for d, e in STATION_PAIRS:
        stationary[f'{d}->{e}'] = {
            'laterArrivalVsEarlierWaiting': points_near_routes(white[e], white[d], 'arrivalParts'),
            'earlierDepartureVsLaterWaiting': points_near_routes(white[d], white[e], 'departureParts')}
    return {'title': plan['title'], 'cohorts': cohorts,
            'crossCohortArrivalVsArrival': crosses,
            'crossCohortWaitingPointChecks': stationary,
            'whiteChain': {'A': list(range(1, 54, 6)), 'B': list(range(2, 54, 6)),
                           'C': list(range(3, 54, 6))},
            'firstThreeFeederSources': {str(d): cohorts[d-1]['feederByLie'] for d in (1,2,3)},
            'white8and9FeederSources': {str(d): dict(collections.Counter(p['feeder'] for p in white[d])) for d in (8,9)}}


result = {
    'source': 'full-diagonal-plans.json; full-diagonal-plan.py',
    'method': {
        'crossing': 'Same-floor interior segment intersection, sin(angle)>=0.2 and each segment parameter strictly between 0.01 and 0.99. Raw segment hits repeat people; uniqueGeometricPoints deduplicates (floor, round(x,5), round(y,5)); uniquePersonPairs deduplicates by ID.',
        'stationary': 'Distance between a moving arrival/departure segment and another person\'s modeled assembly endpoint on the same floor <=0.03 figure units. Counts are geometric proximity, not body width, collision, or temporal coincidence.',
        'scope': 'Within-cohort counts copied from source. Cross-cohort arrival checked for consecutive white groups 1->2 through 8->9 and additionally 1->3. Stationary checks cover 1->2, 2->3, 1->3; no timing inferred.',
        'caution': 'B1 rest stand aisles and the single B1-to-B2 stair with three illustrative lanes are distinct physical resources. Same-lane reuse can be safe only when the earlier party and stationary queues have cleared. Floor designation and map scale remain unverified on site.'},
    'structuralFindings': [
        'full-diagonal-plan.py assigns stairLane by lie modulo three, but the allocator constrains distinct ordered feeder sources chiefly for blue columns; white feeder-to-stair lanes can cross at B1 entry.',
        'White 2 uses STAIR as a stationary assembly node for 97 people in both layouts. The three lanes are tracks within one B1-to-B2 stair, not three additional independent stairways; capacity and hold location need field measurement.',
        'Under the current source eligibility/assignment, white 8/9 use only 144M and 145 as feeder sections across both layouts. Requiring three distinct rest-section feeder outlets per three lanes there cannot be inferred from this model; redesign assembly/source constraints or retain a phased merge.',
        'Counts from these geometric tests cannot certify crossing-free operational timing or physical body clearance.'
    ],
    'layouts': {mode: audit(mode, plan) for mode, plan in DATA.items()}}
OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print(OUT)
for name, plan in result['layouts'].items():
    print(name, 'cross-cohort distinct pairs', {k: v['uniquePersonPairs'] for k,v in plan['crossCohortArrivalVsArrival'].items()})
    print(name, 'waiting', {k: {q:v[q]['uniquePersonPairs'] for q in v} for k,v in plan['crossCohortWaitingPointChecks'].items()})
