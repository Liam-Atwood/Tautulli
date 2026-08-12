import socket
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'lib'))


@pytest.fixture(autouse=True)
def block_raw_network(monkeypatch, request):
    """Defense in depth if the pytest-socket plugin is not active."""
    if request.node.get_closest_marker('integration'):
        return

    def blocked(*args, **kwargs):
        raise RuntimeError('Outbound network is disabled in foundation tests')

    monkeypatch.setattr(socket, 'create_connection', blocked)
