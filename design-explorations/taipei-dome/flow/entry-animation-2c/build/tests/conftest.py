import json
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]   # entry-animation-2c/
sys.path.insert(0, str(ROOT / 'build'))        # import plan / routes / check


@pytest.fixture(scope='session')
def root():
    return ROOT


@pytest.fixture(scope='session')
def base():
    return json.loads((ROOT / 'build' / 'base.json').read_text(encoding='utf-8'))
