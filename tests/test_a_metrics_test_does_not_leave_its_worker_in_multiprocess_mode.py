"""A test that sets up multiprocess metrics leaves the next test in its worker able to build the app.

Four of one day's suites had a different `client` test error at setup, each
passing alone: an earlier test in the same xdist worker had switched
`prometheus_client` to multiprocess values and only its environment variable
was put back, so the next app built failed creating its first metric.
"""
from __future__ import annotations

from tests.conftest import metrics_kept_in_this_process


def test_the_value_class_is_put_back_after_a_test_switches_it(tmp_path, monkeypatch):
    from prometheus_client import Histogram, values

    from app.observability.metrics import _prepare_multiprocess_dir

    with metrics_kept_in_this_process():
        monkeypatch.setenv("PROMETHEUS_MULTIPROC_DIR", str(tmp_path / "prom"))
        _prepare_multiprocess_dir()
        assert values.ValueClass is not values.MutexValue
        monkeypatch.delenv("PROMETHEUS_MULTIPROC_DIR")

    Histogram("a_metric_built_after", "built with the variable gone", registry=None)
    assert values.ValueClass is values.MutexValue
