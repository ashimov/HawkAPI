"""Shared test fixtures."""

import pytest

from hawkapi import HawkAPI


@pytest.fixture
def app() -> HawkAPI:
    """Create a fresh HawkAPI instance for testing."""
    return HawkAPI()
