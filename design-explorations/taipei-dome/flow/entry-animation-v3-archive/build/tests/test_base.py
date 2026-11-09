def test_base_shape(base):
    assert set(base) >= {'meta', 'phases', 'nodes', 'map', 'restSeats', 'files', 'persons', 'others'}
    assert len(base['persons']) == 1609 and len(base['restSeats']) == 1725 and len(base['files']) == 54
    assert base['meta']['speedUnitPerSec'] == 1.1


def test_helpers_present(root):
    """geo.py、collide.py 是版本 2 原檔搬來的（舊資料夾已移除，無法再逐字比對），至少要能 import 且介面不變。"""
    import collide
    import geo
    assert callable(geo.Poly) and callable(geo.pairs) and callable(collide.collisions)
    assert geo.Poly(geo.pairs([0, 0, 1, 0, 1, 1])).L == 2
