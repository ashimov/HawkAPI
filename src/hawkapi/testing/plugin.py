"""pytest plugin for HawkAPI — auto-fixtures.

Register via pyproject.toml:
    [project.entry-points.pytest11]
    hawkapi = "hawkapi.testing.plugin"
"""

from __future__ import annotations

from typing import Any

import pytest

from hawkapi.testing.client import TestClient


@pytest.fixture
def hawk_client(app: Any) -> TestClient:
    """Create a TestClient from an `app` fixture.

    The user must provide an `app` fixture that returns a HawkAPI instance.
    """
    return TestClient(app)
