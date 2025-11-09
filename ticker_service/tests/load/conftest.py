"""
Pytest configuration for load tests.

Defines custom markers and fixtures for load testing.
"""
import pytest


def pytest_configure(config):
    """Register custom markers"""
    config.addinivalue_line(
        "markers",
        "load: mark test as a load test (deselect with '-m \"not load\"')"
    )
    config.addinivalue_line(
        "markers",
        "slow: mark test as slow (deselect with '-m \"not slow\"')"
    )
