"""An operator pins a run only to a model server the deployment knows; any other address is an administrator's (LR.39).

Found in the launch review: an operator could pin a run to any address - the cloud metadata address, the search
service, a machine on the LAN - and the worker posted there, its replies landing in the run's transcript.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

import pytest
from fastapi import HTTPException

from app.server import runs

OPERATOR = SimpleNamespace(role="operator")
ADMIN = SimpleNamespace(role="admin")


def test_an_unknown_address_is_refused_to_an_operator_and_allowed_to_an_administrator():
    with mock.patch.object(runs, "_a_known_model_address", return_value=False):
        with pytest.raises(HTTPException) as refused:
            runs._the_pin_target(True, "http://169.254.169.254/latest", "m", OPERATOR)
        assert refused.value.status_code == 403
        assert runs._the_pin_target(True, "http://10.0.0.5:8080/v1", "m", ADMIN)[0] == "http://10.0.0.5:8080/v1"


def test_a_known_address_and_a_model_name_alone_are_an_operator_s():
    with mock.patch.object(runs, "_a_known_model_address", return_value=True):
        assert runs._the_pin_target(True, "http://host.docker.internal:1234/v1", "m", OPERATOR)[0]
    assert runs._the_pin_target(True, None, "another-model", OPERATOR) == (None, "another-model")


def test_known_means_configured_or_saved_and_trailing_slashes_do_not_matter():
    settings = SimpleNamespace(openai_base_url="http://host.docker.internal:8888/v1/", judgement_base_url="")
    profiles = [{"values": {"openai_base_url": "http://host.docker.internal:1234/v1"}}]
    with mock.patch("app.models._runtime_settings", return_value=settings), \
            mock.patch("app.server.model_profiles.list_profiles", return_value=profiles):
        assert runs._a_known_model_address("http://host.docker.internal:8888/v1")
        assert runs._a_known_model_address("http://HOST.docker.internal:1234/v1/")
        assert not runs._a_known_model_address("http://169.254.169.254/latest")
