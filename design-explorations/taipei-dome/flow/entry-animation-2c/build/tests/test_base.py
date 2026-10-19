def test_base_shape(base):
    assert set(base) >= {'meta', 'phases', 'nodes', 'map', 'restSeats', 'files', 'persons', 'others'}
    assert len(base['persons']) == 1609 and len(base['restSeats']) == 1725 and len(base['files']) == 54
    assert base['meta']['speedUnitPerSec'] == 1.1


def test_helpers_copied(root):
    assert (root / 'build/geo.py').read_text() == (root.parent / 'entry-animation-v2/build/geo.py').read_text()
    assert (root / 'build/collide.py').read_text() == (root.parent / 'entry-animation-v2/build/collide.py').read_text()
