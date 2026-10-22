"""A specification that makes the product unable to start with only `PORT` and `DATA_DIR` goes back to the architect.

Measured on one gate run: the environment contract said the product starts from
`PORT` and `DATA_DIR` alone, the specification said in six sections that
`SECRET_KEY` is "required at startup. Default: None (service fails if missing)",
and the product never started for the suite.
"""
from __future__ import annotations

import re

from pydantic import BaseModel

from app.graph.workflow import _settings_it_cannot_start_without, _the_startup_repair

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


class Spec(BaseModel):
    configuration: list[str] = []
    security_and_privacy: list[str] = []
    error_catalogue: list[str] = []


def test_a_secret_required_at_start_is_found():
    spec = Spec(
        configuration=["SECRET_KEY (str): JWT signing secret, required at startup. Default: None (service fails if missing).",
                       "DATABASE_URL (str): connection string. Default: 'sqlite:///data/app.db' if unset.",
                       "PORT (int): required at startup."],
        security_and_privacy=["The signing secret (`SECRET_KEY`) is read from the environment; the service refuses to start if missing."],
        error_catalogue=["JWT SECRET_KEY environment variable is missing at startup -> Application refuses to start"],
    )

    assert _settings_it_cannot_start_without(spec) == ["SECRET_KEY"]


def test_a_secret_with_a_development_default_is_not():
    spec = Spec(configuration=["SECRET_KEY (str): signing secret. Default: 'dev-only-secret' when unset; set it in production."])

    assert _settings_it_cannot_start_without(spec) == []


def test_the_repair_names_the_setting_and_the_contract():
    told = _the_startup_repair(["SECRET_KEY"])

    assert "`SECRET_KEY`" in told and "`PORT` and `DATA_DIR`" in told and "development default" in told
    assert not BANNED.search(told)
