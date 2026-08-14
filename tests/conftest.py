from __future__ import annotations

import pytest

from tests.helpers import write_synthetic_release


@pytest.fixture
def synthetic_release(tmp_path):
    return write_synthetic_release(tmp_path / "synthetic-release")
