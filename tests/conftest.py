"""Shared test fixtures."""

import os

import pytest


@pytest.fixture(autouse=True)
def _set_test_env_vars(monkeypatch):
    """Ensure MAGENE_API_KEY, MAGENE_API_BASE_URL, and IMAGE2_MODEL are set for all tests."""
    monkeypatch.setenv("MAGENE_API_KEY", "sk-integration-test")
    monkeypatch.setenv("MAGENE_API_BASE_URL", "http://integration.test/v1/images/generations")
    monkeypatch.setenv("IMAGE2_MODEL", "openai/gpt-image-2")

