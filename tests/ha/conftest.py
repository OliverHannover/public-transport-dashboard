"""Expose this checkout to Home Assistant's custom-integration loader."""

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def custom_integrations(enable_custom_integrations, monkeypatch):
    import custom_components

    # HA's test config can import its own custom_components package first.
    component_path = Path(__file__).resolve().parents[2] / "custom_components"
    monkeypatch.setattr(custom_components, "__path__", [str(component_path)])
    yield
