"""`loop.sh deep-audit run-...` looks each named run up through the store's own reader."""
import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("deep_audit_t", ROOT / "scripts" / "loop" / "deep_audit.py")
deep_audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deep_audit)


class _Store:
    def __init__(self, records):
        self.records = records

    def load(self, run_id):
        return self.records.get(run_id)


def test_named_runs_are_read_from_the_store(monkeypatch):
    record = types.SimpleNamespace(run_id="run-a", updated_at="2026-01-01T00:00:00+00:00")
    store = _Store({"run-a": record})
    fake = types.ModuleType("app.server.run_store")
    fake.RunStore = types.SimpleNamespace(shared=lambda: store)
    monkeypatch.setitem(sys.modules, "app.server.run_store", fake)

    assert deep_audit._runs(["run-a", "run-missing"]) == [record]
