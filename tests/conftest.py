"""Every test gets an empty claims store and audit log, so a developer's own data/claims_store.jsonl
never changes a test result and tests never write to it."""
import pytest

from agent import audit, stock_log, store


@pytest.fixture(autouse=True)
def _isolated_files(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "PATH", tmp_path / "claims_store.jsonl")
    monkeypatch.setattr(audit, "LOG", tmp_path / "audit_log.jsonl")
    monkeypatch.setattr(stock_log, "PATH", tmp_path / "stock_actions.jsonl")
