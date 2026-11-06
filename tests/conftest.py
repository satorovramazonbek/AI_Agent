from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def no_real_model(monkeypatch):
    """Testlar hech qachon haqiqiy API'ni chaqirmaydi (.env da kalit bo'lsa ham)."""
    monkeypatch.setattr("jarvis.voice.intents.get_agent", lambda: SimpleNamespace(available=False))
