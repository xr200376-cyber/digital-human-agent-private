import os

import moonshot_service


def test_missing_moonshot_key_does_not_exit(monkeypatch, tmp_path):
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    monkeypatch.setattr(moonshot_service, "project_root", lambda: tmp_path)

    moonshot_service.load_env()

    assert not os.getenv("MOONSHOT_API_KEY")


def test_build_moonshot_llm_returns_none_without_key(monkeypatch):
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)

    assert moonshot_service.build_moonshot_llm() is None
