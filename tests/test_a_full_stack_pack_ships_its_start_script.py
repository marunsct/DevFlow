"""A full-stack pack ships the start script the brief asks for, as its own kept file.

Measured on one run: the FastAPI + page pack shipped no `start.sh`, so a builder wrote one calling a bare `uvicorn`
(not the project's `.venv`), while the suite started the product its own way - the criterion "start.sh starts the
service on PORT with its data under DATA_DIR" rested on a script nothing proved.
"""
from app.stacks import pack_named


def test_each_full_stack_pack_keeps_a_start_script_that_runs_its_own_server():
    for name in ("fullstack-page-fastapi", "fullstack-react-fastapi", "fullstack-react-express"):
        pack = pack_named(name)
        script = pack.files["start.sh"]
        assert script.startswith("#!/bin/sh") and "scripts/serve-acceptance.mjs" in script
        assert "PORT" in script and "DATA_DIR" in script
        assert "start.sh" in pack.kept_files
